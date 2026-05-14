"""Reminder Engine — schedules and executes reminder rules.

Responsibilities:
  • Register one APScheduler cron job per rule (timezone Africa/Nairobi)
  • Honour the master enable/disable toggle + per-rule enabled toggle
    (both stored in masters_settings → reminder_service)
  • For each run: evaluate condition → dedup against reminder_log →
    fire event via email_triggers.fire_and_forget → log every fire/skip
  • Persist a per-run summary to reminder_runs

The Reminder Service NEVER sends email directly — it always goes through
the Notification Service (utils/email_triggers.fire_and_forget).
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .rules import RULES, get_rule, get_dedup_key, _today_eat

logger = logging.getLogger(__name__)

TENANT = "solvit"
SETTINGS_DOC_ID = "reminder_service"
DEFAULT_CONFIG = {
    "master_enabled": True,
    "daily_run_time": "08:00",
    "timezone": "Africa/Nairobi",
    "rule_overrides": {},  # {rule_id: {"enabled": bool, "cron": {...}}}
}


class ReminderEngine:
    def __init__(self):
        self.db = None
        self.scheduler: AsyncIOScheduler | None = None
        self._started = False

    # ────────────────────── lifecycle ──────────────────────
    async def start(self, db):
        self.db = db
        if self._started:
            return
        await self._ensure_config()
        await self._ensure_indexes()
        self.scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")
        await self._register_jobs()
        self.scheduler.start()
        self._started = True
        logger.info("✅ Reminder Engine started — %d rules registered", len(RULES))

    async def shutdown(self):
        if self.scheduler:
            self.scheduler.shutdown(wait=False)

    async def _ensure_indexes(self):
        await self.db.reminder_log.create_index([("rule_id", 1), ("dedup_key", 1)], unique=True)
        await self.db.reminder_log.create_index([("rule_id", 1), ("fired_at", -1)])
        await self.db.reminder_runs.create_index([("rule_id", 1), ("started_at", -1)])

    async def _ensure_config(self):
        existing = await self.db.masters_settings.find_one({"_id": SETTINGS_DOC_ID})
        if not existing:
            await self.db.masters_settings.insert_one({"_id": SETTINGS_DOC_ID, **DEFAULT_CONFIG})

    async def get_config(self) -> dict:
        doc = await self.db.masters_settings.find_one({"_id": SETTINGS_DOC_ID}) or {}
        return {**DEFAULT_CONFIG, **{k: v for k, v in doc.items() if k != "_id"}}

    async def update_config(self, patch: dict) -> dict:
        await self.db.masters_settings.update_one({"_id": SETTINGS_DOC_ID},
                                                  {"$set": patch}, upsert=True)
        # Re-register jobs so schedule changes take effect
        if self.scheduler:
            for job in list(self.scheduler.get_jobs()):
                self.scheduler.remove_job(job.id)
            await self._register_jobs()
        return await self.get_config()

    # ────────────────────── scheduling ─────────────────────
    async def _register_jobs(self):
        cfg = await self.get_config()
        overrides = cfg.get("rule_overrides", {}) or {}
        if not cfg.get("master_enabled", True):
            logger.info("Reminder Service is globally paused — no jobs registered.")
            return
        # Allow override of the default daily hour from config (e.g. "07:30")
        try:
            h, m = (cfg.get("daily_run_time") or "08:00").split(":")
            default_h, default_m = int(h), int(m)
        except Exception:
            default_h, default_m = 8, 0
        for rule in RULES:
            ov = overrides.get(rule["id"], {})
            if ov.get("enabled") is False:
                continue
            cron = {**rule["cron"], **(ov.get("cron") or {})}
            # If rule has only hour/minute (i.e. a vanilla daily rule), apply the
            # configured daily run time so the global setting actually steers it.
            if set(cron.keys()) <= {"hour", "minute"}:
                cron = {"hour": default_h, "minute": default_m}
            self.scheduler.add_job(
                self._run_rule_job, "cron",
                kwargs={"rule_id": rule["id"]},
                id=f"rem_{rule['id']}",
                replace_existing=True,
                **cron,
            )

    async def _run_rule_job(self, rule_id: str):
        try:
            await self.run_rule(rule_id)
        except Exception as e:
            logger.exception("Reminder rule %s failed: %s", rule_id, e)

    # ────────────────────── execution ──────────────────────
    async def run_rule(self, rule_id: str, triggered_by: str = "scheduled") -> dict:
        rule = get_rule(rule_id)
        if not rule:
            raise ValueError(f"Unknown rule: {rule_id}")
        run_id = str(uuid.uuid4())
        started = datetime.now(timezone.utc).isoformat()
        today = _today_eat()
        fired = 0
        skipped = 0
        failed = 0
        error_msg = None
        try:
            targets = await rule["condition"](self.db, today)
        except Exception as e:
            logger.exception("Reminder condition for %s raised: %s", rule_id, e)
            await self.db.reminder_runs.insert_one({
                "id": run_id, "tenant_id": TENANT, "rule_id": rule_id, "rule_name": rule["name"],
                "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                "evaluated": 0, "fired": 0, "skipped": 0, "failed": 0,
                "status": "Failed", "error": str(e), "triggered_by": triggered_by,
            })
            return {"run_id": run_id, "status": "Failed", "error": str(e)}

        for tgt in targets:
            dedup_key = str(get_dedup_key(rule, tgt, today))
            already = await self.db.reminder_log.find_one(
                {"rule_id": rule_id, "dedup_key": dedup_key})
            if already:
                skipped += 1
                continue
            ok = await self._fire(rule, tgt)
            entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": TENANT,
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "target_id": tgt.get("employee_id") or tgt.get("event_id")
                              or tgt.get("candidate_id") or tgt.get("interview_id")
                              or tgt.get("task_id") or tgt.get("leave_request_id")
                              or tgt.get("quarter") or "—",
                "dedup_key": dedup_key,
                "context": tgt,
                "fired_at": datetime.now(timezone.utc).isoformat(),
                "status": "Fired" if ok else "Failed",
                "triggered_by": triggered_by,
            }
            try:
                await self.db.reminder_log.insert_one(entry)
            except Exception:
                # Unique-index race — treat as skipped (someone else fired it).
                skipped += 1
                continue
            if ok:
                fired += 1
            else:
                failed += 1

        finished = datetime.now(timezone.utc).isoformat()
        status = "Failed" if failed and not fired else ("Partial" if failed else "Completed")
        await self.db.reminder_runs.insert_one({
            "id": run_id, "tenant_id": TENANT, "rule_id": rule_id, "rule_name": rule["name"],
            "started_at": started, "finished_at": finished,
            "evaluated": len(targets), "fired": fired, "skipped": skipped, "failed": failed,
            "status": status, "error": error_msg, "triggered_by": triggered_by,
        })
        logger.info("Rule %s: evaluated=%d fired=%d skipped=%d failed=%d",
                    rule_id, len(targets), fired, skipped, failed)
        return {"run_id": run_id, "rule_id": rule_id,
                "evaluated": len(targets), "fired": fired,
                "skipped": skipped, "failed": failed, "status": status}

    async def _fire(self, rule: dict, target: dict) -> bool:
        """Resolve recipients and fire the event into the Notification Service."""
        from utils.email_triggers import fire_and_forget
        template_key = rule["template_key"]
        # Build extra context — pass everything from target as merge tags
        extra = {k: v for k, v in target.items() if isinstance(v, (str, int, float, bool))}
        recipients = rule.get("recipients") or ["employee"]
        any_ok = False
        for role in recipients:
            try:
                if role == "employee":
                    if target.get("employee_id"):
                        await fire_and_forget(self.db, template_key,
                                              employee_id=target["employee_id"],
                                              extra=extra)
                        any_ok = True
                elif role == "line_manager":
                    lm_id = target.get("line_manager_id")
                    if not lm_id and target.get("employee_id"):
                        emp = await self.db.employees.find_one({"id": target["employee_id"]})
                        lm_id = (emp or {}).get("line_manager_id")
                    if lm_id:
                        lm = await self.db.employees.find_one({"id": lm_id}) or {}
                        if lm.get("work_email"):
                            await fire_and_forget(self.db, template_key,
                                                  employee_id=target.get("employee_id"),
                                                  to_override=lm["work_email"],
                                                  extra=extra)
                            any_ok = True
                else:
                    # Role lookup — pick the user record for the role.
                    user = await self.db.users.find_one({"tenant_id": TENANT, "role": role})
                    if user and user.get("email"):
                        await fire_and_forget(self.db, template_key,
                                              employee_id=target.get("employee_id"),
                                              to_override=user["email"],
                                              extra=extra)
                        any_ok = True
            except Exception as e:
                logger.warning("Reminder _fire(%s, role=%s) failed: %s", template_key, role, e)
        return any_ok

    # ────────────────────── observability ──────────────────
    async def rules_overview(self) -> list[dict]:
        cfg = await self.get_config()
        overrides = cfg.get("rule_overrides", {}) or {}
        out = []
        for rule in RULES:
            ov = overrides.get(rule["id"], {})
            enabled = bool(cfg.get("master_enabled", True)) and ov.get("enabled", True)
            last = await self.db.reminder_runs.find_one(
                {"rule_id": rule["id"]}, sort=[("started_at", -1)])
            job = (self.scheduler.get_job(f"rem_{rule['id']}")
                   if self.scheduler else None)
            next_run = job.next_run_time.isoformat() if (job and job.next_run_time) else None
            out.append({
                "id": rule["id"],
                "name": rule["name"],
                "group": rule["group"],
                "schedule_human": rule["schedule_human"],
                "template_key": rule["template_key"],
                "recipients": rule["recipients"],
                "dedup_scope": rule["dedup_scope"],
                "enabled": enabled,
                "last_run_at": (last or {}).get("started_at"),
                "last_status": (last or {}).get("status"),
                "last_evaluated": (last or {}).get("evaluated", 0),
                "last_fired": (last or {}).get("fired", 0),
                "last_skipped": (last or {}).get("skipped", 0),
                "next_run_at": next_run,
            })
        return out


reminder_engine = ReminderEngine()
