"""Reminder Service API — registry, log, run-now, config."""
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional

from database import get_db
from utils.auth import get_current_user
from reminders.engine import reminder_engine

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _it_admin_only(user):
    if user.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")


def _can_view(user):
    return user.get("role") in ("it_admin", "hr_admin", "hr_manager", "executive")


@router.get("/config")
async def get_config(request: Request):
    user = await get_current_user(request)
    if not _can_view(user):
        raise HTTPException(status_code=403, detail="No access")
    cfg = await reminder_engine.get_config()
    return {"config": cfg, "can_edit": user.get("role") == "it_admin"}


@router.put("/config")
async def update_config(request: Request):
    user = await get_current_user(request)
    _it_admin_only(user)
    patch = await request.json()
    allowed = {"master_enabled", "daily_run_time"}
    clean = {k: v for k, v in patch.items() if k in allowed}
    cfg = await reminder_engine.update_config(clean)
    return {"config": cfg}


@router.get("/rules")
async def list_rules(request: Request):
    user = await get_current_user(request)
    if not _can_view(user):
        raise HTTPException(status_code=403, detail="No access")
    rules = await reminder_engine.rules_overview()
    return {"rules": rules, "count": len(rules),
            "can_edit": user.get("role") == "it_admin"}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request):
    user = await get_current_user(request)
    _it_admin_only(user)
    body = await request.json()
    cfg = await reminder_engine.get_config()
    overrides = cfg.get("rule_overrides", {}) or {}
    ov = overrides.get(rule_id, {})
    if "enabled" in body:
        ov["enabled"] = bool(body["enabled"])
    if "cron" in body and isinstance(body["cron"], dict):
        ov["cron"] = body["cron"]
    overrides[rule_id] = ov
    await reminder_engine.update_config({"rule_overrides": overrides})
    return {"rule_id": rule_id, "override": ov}


@router.post("/rules/{rule_id}/run-now")
async def run_now(rule_id: str, request: Request):
    user = await get_current_user(request)
    _it_admin_only(user)
    user_label = user.get("email") or user.get("id") or "manual"
    return await reminder_engine.run_rule(rule_id, triggered_by=f"manual:{user_label}")


@router.get("/log")
async def get_log(request: Request,
                  rule_id: Optional[str] = Query(None),
                  status: Optional[str] = Query(None),
                  limit: int = Query(100, ge=1, le=500)):
    user = await get_current_user(request)
    if not _can_view(user):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if rule_id:
        q["rule_id"] = rule_id
    if status:
        q["status"] = status
    rows = await db.reminder_log.find(q).sort("fired_at", -1).to_list(limit)
    for r in rows:
        r.pop("_id", None)
    return {"log": rows, "count": len(rows)}


@router.get("/runs")
async def get_runs(request: Request,
                   rule_id: Optional[str] = Query(None),
                   limit: int = Query(50, ge=1, le=200)):
    user = await get_current_user(request)
    if not _can_view(user):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if rule_id:
        q["rule_id"] = rule_id
    rows = await db.reminder_runs.find(q).sort("started_at", -1).to_list(limit)
    for r in rows:
        r.pop("_id", None)
    return {"runs": rows, "count": len(rows)}


@router.get("/summary")
async def hr_summary(request: Request):
    """HR & Admin summary view — weekly counts per rule, no record drill-down."""
    user = await get_current_user(request)
    if not _can_view(user):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"tenant_id": "solvit", "fired_at": {"$gte": cutoff}}},
        {"$group": {"_id": {"rule_id": "$rule_id", "status": "$status"},
                     "count": {"$sum": 1}}},
    ]
    rows = await db.reminder_log.aggregate(pipeline).to_list(500)
    out = {}
    for r in rows:
        rid = r["_id"]["rule_id"]
        out.setdefault(rid, {})[r["_id"]["status"]] = r["count"]
    return {"window_days": 7, "by_rule": out}
