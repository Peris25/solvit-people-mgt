"""Reminder Rules registry — single source of truth for all 40 rules.

Each rule is a dict with:
  - id, name, group, schedule_human, cron_kwargs (passed to APScheduler),
  - template_key (Notification Service template fired per match),
  - recipients (list of role keys: "employee", "line_manager", "hr_admin",
    "it_admin", "finance", "solvers_manager", "executive"),
  - dedup_scope (string label, e.g. "milestone", "cycle", "weekly", "daily"),
  - condition (async fn(db, today) -> list[dict] where each dict carries the
    target_id + any merge-tag context for the email template),
  - dedup_key (callable(target) -> str — combined with rule_id forms the
    dedup key in reminder_log).

Condition functions are defensive: if the underlying collection or field
isn't populated yet, they return [] rather than crashing.
"""
from datetime import datetime, timedelta, timezone, date
from typing import Callable

# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

def _today_eat() -> date:
    """Current calendar date in Africa/Nairobi (UTC+3, no DST)."""
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def _parse_iso_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except Exception:
        return None


def _emp_ctx(emp):
    return {
        "employee_id": emp.get("id"),
        "employee_name": emp.get("full_name"),
        "employee_first_name": (emp.get("full_name") or "").split(" ")[0],
        "line_manager_id": emp.get("line_manager_id"),
    }


# ────────────────────────────────────────────────────────────────────────
# GROUP 1: ONBOARDING
# ────────────────────────────────────────────────────────────────────────

async def _onboard_offset(db, today, days):
    """All Onboarding employees whose start_date is `today - days` (so day-N
    of their tenure is today). Positive `days` looks back; use negative to
    look forward (pre-arrival)."""
    target = today - timedelta(days=days)
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Onboarding", "Probation"]},
                                      "start_date": {"$regex": f"^{target.isoformat()}"}}):
        out.append({**_emp_ctx(e), "milestone_days": days})
    return out


async def cond_onboard_pre_arrival(db, today):
    # start_date = today + 3 days
    target = today + timedelta(days=3)
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Onboarding", "Candidate"]},
                                      "start_date": {"$regex": f"^{target.isoformat()}"}}):
        out.append({**_emp_ctx(e),
                    "start_date": e.get("start_date"),
                    "office_address": "Solvit Limited, Nairobi",
                    "manager_name": ""})  # filled by trigger
    return out


async def _checkin_due(db, today, days, form_key):
    """Day-N onboarding check-in: start_date was (today - (days-2)). The spec
    fires 2 days BEFORE the milestone so the manager has time to act."""
    return await _onboard_offset(db, today, days - 2)


async def cond_onboard_30(db, today):
    items = await _checkin_due(db, today, 30, "checkin_30")
    # Filter out those whose check-in has been submitted
    out = []
    for c in items:
        existing = await db.onboarding_checkins.find_one({"employee_id": c["employee_id"],
                                                          "milestone": 30})
        if not existing:
            out.append({**c, "due_date": (today + timedelta(days=2)).isoformat()})
    return out


async def cond_onboard_60(db, today):
    items = await _checkin_due(db, today, 60, "checkin_60")
    out = []
    for c in items:
        existing = await db.onboarding_checkins.find_one({"employee_id": c["employee_id"],
                                                          "milestone": 60})
        if not existing:
            out.append({**c, "due_date": (today + timedelta(days=2)).isoformat()})
    return out


async def cond_onboard_90(db, today):
    items = await _checkin_due(db, today, 90, "checkin_90")
    out = []
    for c in items:
        existing = await db.onboarding_checkins.find_one({"employee_id": c["employee_id"],
                                                          "milestone": 90})
        if not existing:
            out.append({**c, "due_date": (today + timedelta(days=2)).isoformat()})
    return out


async def cond_onboard_overdue(db, today):
    """Any onboarding check-in >7 days past due with no submission."""
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Onboarding", "Probation"]}}):
        sd = _parse_iso_date(e.get("start_date"))
        if not sd:
            continue
        tenure = (today - sd).days
        for milestone in (30, 60, 90):
            if tenure > milestone + 7:
                ck = await db.onboarding_checkins.find_one({"employee_id": e.get("id"),
                                                            "milestone": milestone})
                if not ck:
                    out.append({**_emp_ctx(e),
                                "milestone": milestone,
                                "days_overdue": tenure - milestone})
                    break  # one alert per employee per run
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 2: PROBATION
# ────────────────────────────────────────────────────────────────────────

async def _probation_due(db, today, offset_days):
    target = today + timedelta(days=offset_days)
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Probation", "Onboarding"]},
                                      "probation_end_date": {"$regex": f"^{target.isoformat()}"}}):
        if e.get("probation_outcome"):
            continue
        out.append({**_emp_ctx(e),
                    "probation_end_date": e.get("probation_end_date")})
    return out


async def cond_prob_7day(db, today):
    return await _probation_due(db, today, 7)


async def cond_prob_due_today(db, today):
    return await _probation_due(db, today, 0)


async def cond_prob_overdue(db, today):
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Probation", "Onboarding"]}}):
        if e.get("probation_outcome"):
            continue
        pe = _parse_iso_date(e.get("probation_end_date"))
        if pe and pe < today:
            out.append({**_emp_ctx(e),
                        "probation_end_date": e.get("probation_end_date"),
                        "days_overdue": (today - pe).days})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 3: PERFORMANCE
# ────────────────────────────────────────────────────────────────────────

async def _active_cycle(db):
    return await db.performance_cycles.find_one({"tenant_id": "solvit", "status": "Active"})


async def cond_perf_self_3day(db, today):
    cyc = await _active_cycle(db)
    if not cyc:
        return []
    due = _parse_iso_date(cyc.get("self_review_due_date"))
    if not due or (due - today).days != 3:
        return []
    submitted_ids = {r["employee_id"] async for r in db.performance_reviews.find(
        {"cycle_id": cyc.get("id"), "self_review_submitted": True})}
    out = []
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}):
        if e.get("id") in submitted_ids:
            continue
        out.append({**_emp_ctx(e),
                    "cycle_id": cyc.get("id"),
                    "deadline": cyc.get("self_review_due_date")})
    return out


async def cond_perf_self_overdue(db, today):
    cyc = await _active_cycle(db)
    if not cyc:
        return []
    due = _parse_iso_date(cyc.get("self_review_due_date"))
    if not due or due >= today:
        return []
    submitted_ids = {r["employee_id"] async for r in db.performance_reviews.find(
        {"cycle_id": cyc.get("id"), "self_review_submitted": True})}
    out = []
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}):
        if e.get("id") in submitted_ids:
            continue
        out.append({**_emp_ctx(e),
                    "cycle_id": cyc.get("id"),
                    "days_overdue": (today - due).days})
    return out


async def cond_perf_mgr_3day(db, today):
    cyc = await _active_cycle(db)
    if not cyc:
        return []
    due = _parse_iso_date(cyc.get("manager_review_due_date"))
    if not due or (due - today).days != 3:
        return []
    out = []
    async for r in db.performance_reviews.find({"cycle_id": cyc.get("id"),
                                                 "manager_review_submitted": {"$ne": True}}):
        emp = await db.employees.find_one({"id": r.get("employee_id")}) or {}
        out.append({"employee_id": r.get("employee_id"),
                    "employee_name": emp.get("full_name"),
                    "line_manager_id": emp.get("line_manager_id"),
                    "deadline": cyc.get("manager_review_due_date")})
    return out


async def cond_perf_mgr_overdue(db, today):
    cyc = await _active_cycle(db)
    if not cyc:
        return []
    due = _parse_iso_date(cyc.get("manager_review_due_date"))
    if not due or due >= today:
        return []
    out = []
    async for r in db.performance_reviews.find({"cycle_id": cyc.get("id"),
                                                 "manager_review_submitted": {"$ne": True}}):
        emp = await db.employees.find_one({"id": r.get("employee_id")}) or {}
        out.append({"employee_id": r.get("employee_id"),
                    "employee_name": emp.get("full_name"),
                    "line_manager_id": emp.get("line_manager_id"),
                    "days_overdue": (today - due).days})
    return out


async def cond_perf_pip_checkin(db, today):
    out = []
    async for p in db.pips.find({"tenant_id": "solvit", "status": "Active"}):
        next_dt = _parse_iso_date(p.get("next_checkin_date"))
        if next_dt and next_dt == today:
            emp = await db.employees.find_one({"id": p.get("employee_id")}) or {}
            out.append({"employee_id": p.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "line_manager_id": emp.get("line_manager_id"),
                        "pip_id": p.get("id"),
                        "checkin_date": p.get("next_checkin_date")})
    return out


async def cond_perf_pip_ending(db, today):
    out = []
    async for p in db.pips.find({"tenant_id": "solvit", "status": "Active",
                                  "pip_outcome": {"$in": [None, ""]}}):
        end = _parse_iso_date(p.get("pip_end_date"))
        if end and (end - today).days == 7:
            emp = await db.employees.find_one({"id": p.get("employee_id")}) or {}
            out.append({"employee_id": p.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "line_manager_id": emp.get("line_manager_id"),
                        "pip_id": p.get("id"),
                        "pip_end_date": p.get("pip_end_date")})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 4: SURVEYS
# ────────────────────────────────────────────────────────────────────────

async def _open_surveys(db, audience):
    out = []
    async for s in db.survey_cycles.find({"tenant_id": "solvit", "status": "Open",
                                          "audience": audience}):
        out.append(s)
    return out


async def _survey_close_offset(db, today, days, audience):
    out = []
    for cycle in await _open_surveys(db, audience):
        close = _parse_iso_date(cycle.get("close_date"))
        if not close or (close - today).days != days:
            continue
        submitted = {r["respondent_id"] async for r in db.survey_responses.find(
            {"cycle_id": cycle.get("id")})}
        if audience == "employees":
            async for e in db.employees.find({"tenant_id": "solvit",
                                               "lifecycle_state": {"$in": ["Active", "Probation"]}}):
                if e.get("id") in submitted:
                    continue
                out.append({**_emp_ctx(e),
                            "cycle_id": cycle.get("id"),
                            "cycle_label": cycle.get("name") or cycle.get("id"),
                            "close_date": cycle.get("close_date")})
        else:  # solvers
            async for s in db.solvers.find({"tenant_id": "solvit", "lifecycle_state": "Active"}):
                if s.get("id") in submitted:
                    continue
                out.append({"employee_id": s.get("id"),
                            "solver_name": s.get("full_name"),
                            "cycle_id": cycle.get("id"),
                            "close_date": cycle.get("close_date")})
    return out


async def cond_survey_3day(db, today):
    return await _survey_close_offset(db, today, 3, "employees")


async def cond_survey_final_day(db, today):
    return await _survey_close_offset(db, today, 0, "employees")


async def cond_solver_survey_3day(db, today):
    return await _survey_close_offset(db, today, 3, "solvers")


# ────────────────────────────────────────────────────────────────────────
# GROUP 5: LEAVE
# ────────────────────────────────────────────────────────────────────────

async def cond_leave_balance_low(db, today):
    out = []
    async for b in db.leave_balances.find({"tenant_id": "solvit",
                                           "annual_remaining_days": {"$lt": 3}}):
        year_end = _parse_iso_date(b.get("leave_year_end"))
        if year_end and (year_end - today).days > 60:
            emp = await db.employees.find_one({"id": b.get("employee_id")}) or {}
            out.append({"employee_id": b.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "remaining_days": b.get("annual_remaining_days")})
    return out


async def cond_leave_year_end(db, today):
    out = []
    async for b in db.leave_balances.find({"tenant_id": "solvit"}):
        year_end = _parse_iso_date(b.get("leave_year_end"))
        if year_end and (year_end - today).days == 30 and (b.get("annual_remaining_days") or 0) > 0:
            emp = await db.employees.find_one({"id": b.get("employee_id")}) or {}
            out.append({"employee_id": b.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "remaining_balance": b.get("annual_remaining_days"),
                        "leave_year_end_date": b.get("leave_year_end")})
    return out


async def cond_leave_approval_pending(db, today):
    out = []
    cutoff = (today - timedelta(days=2)).isoformat()
    async for r in db.leave_requests.find({"tenant_id": "solvit", "status": "Pending",
                                            "created_at": {"$lt": cutoff}}):
        emp = await db.employees.find_one({"id": r.get("employee_id")}) or {}
        days_pending = 0
        try:
            days_pending = (today - _parse_iso_date(r.get("created_at"))).days
        except Exception:
            pass
        out.append({"employee_id": r.get("employee_id"),
                    "employee_name": emp.get("full_name"),
                    "line_manager_id": emp.get("line_manager_id") or r.get("line_manager_id"),
                    "leave_request_id": r.get("id"),
                    "leave_type": r.get("leave_type"),
                    "days_pending": days_pending})
    return out


async def cond_leave_return(db, today):
    out = []
    target = today.isoformat()
    async for r in db.leave_requests.find({"tenant_id": "solvit", "status": "Approved",
                                            "end_date": {"$regex": f"^{target}"}}):
        emp = await db.employees.find_one({"id": r.get("employee_id")}) or {}
        out.append({"employee_id": r.get("employee_id"),
                    "employee_name": emp.get("full_name"),
                    "line_manager_id": emp.get("line_manager_id") or r.get("line_manager_id"),
                    "leave_request_id": r.get("id"),
                    "leave_type": r.get("leave_type")})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 6: RECOGNITION & MILESTONES
# ────────────────────────────────────────────────────────────────────────

_ANNIV_MILESTONES = [730, 1095, 1825, 2555]  # 2 / 3 / 5 / 7 years in days
_ANNIV_LABELS = {730: "2", 1095: "3", 1825: "5", 2555: "7"}


async def cond_long_service(db, today):
    out = []
    async for e in db.employees.find({"tenant_id": "solvit",
                                      "lifecycle_state": {"$in": ["Active", "Probation", "On_Leave"]}}):
        sd = _parse_iso_date(e.get("start_date"))
        if not sd:
            continue
        days = (today - sd).days
        if days in _ANNIV_MILESTONES:
            out.append({**_emp_ctx(e),
                        "years": _ANNIV_LABELS[days],
                        "milestone_years": _ANNIV_LABELS[days]})
    return out


async def cond_recog_event_14day(db, today):
    target = today + timedelta(days=14)
    out = []
    async for ev in db.recognition_events.find({"tenant_id": "solvit",
                                                 "event_date": {"$regex": f"^{target.isoformat()}"}}):
        owners = ev.get("assigned_owners") or []
        if owners:
            continue  # spec: only if no actions assigned
        out.append({"employee_id": None,  # event-scoped, no employee
                    "event_id": ev.get("id"),
                    "event_name": ev.get("name"),
                    "event_date": ev.get("event_date")})
    return out


async def cond_recog_event_3day(db, today):
    target = today + timedelta(days=3)
    out = []
    async for ev in db.recognition_events.find({"tenant_id": "solvit",
                                                 "event_date": {"$regex": f"^{target.isoformat()}"}}):
        out.append({"event_id": ev.get("id"),
                    "event_name": ev.get("name"),
                    "event_date": ev.get("event_date")})
    return out


async def cond_solver_award_open(db, today):
    # Fired on quarter open. Quarter is encoded in dedup key.
    q = (today.month - 1) // 3 + 1
    return [{"quarter": f"Q{q} {today.year}",
             "year": today.year,
             "quarter_num": q}]


async def cond_solver_award_deadline(db, today):
    # 7 days before quarter end
    quarter_end_month = ((today.month - 1) // 3 + 1) * 3
    # last day of that month
    if quarter_end_month == 12:
        q_end = date(today.year, 12, 31)
    else:
        q_end = date(today.year, quarter_end_month + 1, 1) - timedelta(days=1)
    if (q_end - today).days != 7:
        return []
    q = (today.month - 1) // 3 + 1
    # Check if nominations exist already
    existing = await db.solver_awards.count_documents({"tenant_id": "solvit",
                                                       "quarter": f"Q{q}",
                                                       "year": today.year})
    if existing > 0:
        return []
    return [{"quarter": f"Q{q} {today.year}", "deadline": q_end.isoformat()}]


# ────────────────────────────────────────────────────────────────────────
# GROUP 7: POLICY
# ────────────────────────────────────────────────────────────────────────

async def cond_policy_3day(db, today):
    target = today + timedelta(days=3)
    out = []
    async for ack in db.policy_acknowledgements_due.find({"tenant_id": "solvit",
                                                          "due_date": {"$regex": f"^{target.isoformat()}"},
                                                          "signed_at": None}):
        emp = await db.employees.find_one({"id": ack.get("employee_id")}) or {}
        out.append({"employee_id": ack.get("employee_id"),
                    "employee_name": emp.get("full_name"),
                    "policy_title": ack.get("policy_title"),
                    "policy_version": ack.get("policy_version"),
                    "deadline": ack.get("due_date"),
                    "policy_name": ack.get("policy_title")})
    return out


async def cond_policy_overdue(db, today):
    out = []
    async for ack in db.policy_acknowledgements_due.find({"tenant_id": "solvit",
                                                          "signed_at": None}):
        due = _parse_iso_date(ack.get("due_date"))
        if due and due < today:
            emp = await db.employees.find_one({"id": ack.get("employee_id")}) or {}
            out.append({"employee_id": ack.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "policy_name": ack.get("policy_title"),
                        "days_overdue": (today - due).days})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 8: RETENTION
# ────────────────────────────────────────────────────────────────────────

_STAY_MILESTONES = [365, 730, 1095]


async def cond_stay_interview_due(db, today):
    out = []
    six_months_ago = (today - timedelta(days=180)).isoformat()
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}):
        sd = _parse_iso_date(e.get("start_date"))
        if not sd or (today - sd).days not in _STAY_MILESTONES:
            continue
        recent = await db.stay_interviews.find_one({"employee_id": e.get("id"),
                                                    "created_at": {"$gte": six_months_ago}})
        if recent:
            continue
        out.append({**_emp_ctx(e),
                    "tenure_years": str((today - sd).days // 365)})
    return out


async def cond_stay_interview_overdue(db, today):
    out = []
    async for si in db.stay_interviews.find({"tenant_id": "solvit", "status": "Scheduled"}):
        sched = _parse_iso_date(si.get("scheduled_date"))
        if sched and sched < today:
            emp = await db.employees.find_one({"id": si.get("employee_id")}) or {}
            out.append({"employee_id": si.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "interview_id": si.get("id"),
                        "scheduled_date": si.get("scheduled_date")})
    return out


async def cond_flight_risk_scan(db, today):
    """Re-compute flight risk; flag upward tier changes since last scan."""
    out = []
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}):
        try:
            from routes.retention import calculate_flight_risk
            risk = calculate_flight_risk(e)
        except Exception:
            continue
        old = e.get("flight_risk_level")
        new = risk.get("level")
        rank = {"Low": 0, "Elevated": 1, "Moderate": 1, "High": 2, "Critical": 3}
        if rank.get(new, 0) > rank.get(old, 0):
            await db.employees.update_one({"_id": e["_id"]},
                                          {"$set": {"flight_risk_score": risk["score"],
                                                    "flight_risk_level": new}})
            out.append({**_emp_ctx(e),
                        "risk_tier": new,
                        "old_tier": old or "Low",
                        "flag_date": today.isoformat()})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 9: EXIT
# ────────────────────────────────────────────────────────────────────────

async def cond_exit_task_overdue(db, today):
    out = []
    async for t in db.tasks.find({"tenant_id": "solvit",
                                   "category": "Exit",
                                   "status": {"$in": ["Pending", "In_Progress"]}}):
        due = _parse_iso_date(t.get("due_date"))
        if due and due < today:
            emp = await db.employees.find_one({"id": t.get("employee_id")}) or {}
            out.append({"task_id": t.get("id"),
                        "employee_id": t.get("employee_id"),
                        "employee_name": emp.get("full_name"),
                        "assigned_role": t.get("assigned_role") or "hr_admin",
                        "last_working_date": emp.get("last_working_date") or emp.get("exit_date"),
                        "days_overdue": (today - due).days})
    return out


async def cond_exit_final_week(db, today):
    target = today + timedelta(days=5)
    out = []
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Exiting"}):
        lwd = _parse_iso_date(e.get("last_working_date") or e.get("exit_date"))
        if not lwd or lwd != target:
            continue
        pending = await db.tasks.count_documents({"employee_id": e.get("id"),
                                                  "category": "Exit",
                                                  "status": {"$ne": "Completed"}})
        if pending == 0:
            continue
        out.append({**_emp_ctx(e),
                    "last_working_date": e.get("last_working_date") or e.get("exit_date"),
                    "pending_tasks": pending})
    return out


async def cond_exit_conf_ack_chase(db, today):
    out = []
    async for e in db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Exiting"}):
        lwd = _parse_iso_date(e.get("last_working_date") or e.get("exit_date"))
        if not lwd or (lwd - today).days > 5 or (lwd - today).days < 0:
            continue
        signed = await db.case_documents.find_one({"employee_id": e.get("id"),
                                                   "document_type": "confidentiality_ack",
                                                   "signed_at": {"$ne": None}})
        if signed:
            continue
        out.append({**_emp_ctx(e),
                    "last_working_date": e.get("last_working_date") or e.get("exit_date"),
                    "days_remaining": (lwd - today).days})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 10: RECRUITMENT
# ────────────────────────────────────────────────────────────────────────

async def cond_candidate_stale(db, today):
    cutoff = (today - timedelta(days=7)).isoformat()
    out = []
    async for c in db.candidates.find({"tenant_id": "solvit",
                                        "stage_status": "Awaiting_Action",
                                        "stage_entered_date": {"$lt": cutoff}}):
        days_in_stage = 0
        try:
            days_in_stage = (today - _parse_iso_date(c.get("stage_entered_date"))).days
        except Exception:
            pass
        out.append({"candidate_id": c.get("id"),
                    "candidate_name": c.get("full_name"),
                    "role_applied_for": c.get("role_applied_for"),
                    "current_stage": c.get("current_stage"),
                    "days_in_stage": days_in_stage})
    return out


async def cond_offer_expiring(db, today):
    target = today + timedelta(days=2)
    out = []
    async for c in db.candidates.find({"tenant_id": "solvit",
                                        "offer_status": "Pending",
                                        "offer_expiry_date": {"$regex": f"^{target.isoformat()}"}}):
        out.append({"candidate_id": c.get("id"),
                    "candidate_name": c.get("full_name"),
                    "role_applied_for": c.get("role_applied_for"),
                    "offer_expiry_date": c.get("offer_expiry_date")})
    return out


# ────────────────────────────────────────────────────────────────────────
# GROUP 11: SYSTEM / HR CALENDAR
# ────────────────────────────────────────────────────────────────────────

async def cond_hrcal_14day(db, today):
    target = today + timedelta(days=14)
    out = []
    async for ev in db.hr_calendar.find({"tenant_id": "solvit",
                                          "event_date": {"$regex": f"^{target.isoformat()}"}}):
        owners = ev.get("assigned_owners") or []
        if owners:
            continue
        out.append({"event_id": ev.get("id"),
                    "event_name": ev.get("name") or ev.get("title"),
                    "event_date": ev.get("event_date")})
    return out


async def cond_hrcal_3day(db, today):
    target = today + timedelta(days=3)
    out = []
    async for ev in db.hr_calendar.find({"tenant_id": "solvit",
                                          "event_date": {"$regex": f"^{target.isoformat()}"}}):
        out.append({"event_id": ev.get("id"),
                    "event_name": ev.get("name") or ev.get("title"),
                    "event_date": ev.get("event_date")})
    return out


async def cond_hrcal_overdue(db, today):
    yesterday = (today - timedelta(days=1)).isoformat()
    out = []
    async for ev in db.hr_calendar.find({"tenant_id": "solvit",
                                          "status": {"$ne": "Completed"},
                                          "event_date": {"$regex": f"^{yesterday}"}}):
        out.append({"event_id": ev.get("id"),
                    "event_name": ev.get("name") or ev.get("title"),
                    "event_date": ev.get("event_date")})
    return out


async def cond_perf_cycle_due(db, today):
    """Fires on the configured 'review cycle open' date if no cycle is open for the year."""
    open_cycle = await db.performance_cycles.find_one({"tenant_id": "solvit",
                                                       "cycle_year": today.year,
                                                       "status": {"$in": ["Active", "Open"]}})
    if open_cycle:
        return []
    return [{"year": today.year, "cycle_year": today.year}]


async def cond_survey_cycle_due(db, today):
    open_cycle = await db.survey_cycles.find_one({"tenant_id": "solvit",
                                                  "cycle_year": today.year,
                                                  "status": "Open"})
    if open_cycle:
        return []
    return [{"year": today.year, "cycle_year": today.year}]


# ────────────────────────────────────────────────────────────────────────
# RULES REGISTRY
# ────────────────────────────────────────────────────────────────────────

def _dedup_per_target_milestone(t):
    return f"{t.get('employee_id') or t.get('event_id') or t.get('candidate_id') or t.get('quarter') or 'x'}"


def _dedup_per_target_cycle(t):
    return f"{t.get('employee_id') or t.get('event_id')}:{t.get('cycle_id') or ''}"


def _dedup_weekly(t, today):
    iso = today.isocalendar()
    return f"{t.get('employee_id') or t.get('event_id') or 'x'}:W{iso[0]}-{iso[1]:02d}"


def _dedup_every_n_days(t, today, n=2):
    bucket = today.toordinal() // n
    return f"{t.get('employee_id') or t.get('leave_request_id') or t.get('task_id') or 'x'}:B{bucket}"


def _dedup_daily(t, today):
    return f"{t.get('employee_id') or 'x'}:{today.isoformat()}"


def _dedup_per_year(t):
    return f"Y{t.get('year') or ''}"


def _dedup_per_quarter(t):
    return f"{t.get('quarter') or ''}"


def _dedup_per_leave_record(t):
    return f"{t.get('leave_request_id') or ''}"


RULES = [
    # ── Group 1: Onboarding ────────────────────────────────────────────
    {"id": "REM-ONBOARD-01", "name": "Pre-Arrival Notification", "group": "Onboarding",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "onboarding.pre_arrival", "recipients": ["employee"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_onboard_pre_arrival},
    {"id": "REM-ONBOARD-02", "name": "30-Day Check-In Due", "group": "Onboarding",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "onboarding.checkin_30", "recipients": ["line_manager", "hr_admin"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_onboard_30},
    {"id": "REM-ONBOARD-03", "name": "60-Day Check-In Due", "group": "Onboarding",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "onboarding.checkin_60", "recipients": ["line_manager", "hr_admin"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_onboard_60},
    {"id": "REM-ONBOARD-04", "name": "90-Day Review / Probation Due", "group": "Onboarding",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "onboarding.checkin_90", "recipients": ["line_manager", "hr_admin"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_onboard_90},
    {"id": "REM-ONBOARD-05", "name": "Overdue Onboarding Check-In Escalation", "group": "Onboarding",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "reminder.onboard_overdue", "recipients": ["hr_admin", "line_manager"],
     "dedup_scope": "weekly", "dedup_key": _dedup_weekly,
     "condition": cond_onboard_overdue},

    # ── Group 2: Probation ─────────────────────────────────────────────
    {"id": "REM-PROB-01", "name": "Probation Review Approaching (7-Day Notice)", "group": "Probation",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.prob_7day", "recipients": ["hr_admin", "line_manager"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_prob_7day},
    {"id": "REM-PROB-02", "name": "Probation Review Due Today", "group": "Probation",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.prob_due", "recipients": ["hr_admin", "line_manager"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_prob_due_today},
    {"id": "REM-PROB-03", "name": "Probation Review Overdue Escalation", "group": "Probation",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "reminder.prob_overdue", "recipients": ["hr_admin"],
     "dedup_scope": "weekly", "dedup_key": _dedup_weekly,
     "condition": cond_prob_overdue},

    # ── Group 3: Performance ───────────────────────────────────────────
    {"id": "REM-PERF-01", "name": "Self-Review Due — 3-Day Reminder", "group": "Performance",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "performance.self_reminder", "recipients": ["employee"],
     "dedup_scope": "cycle", "dedup_key": _dedup_per_target_cycle,
     "condition": cond_perf_self_3day},
    {"id": "REM-PERF-02", "name": "Self-Review Overdue", "group": "Performance",
     "schedule_human": "Every 3 days at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.perf_self_overdue", "recipients": ["employee", "hr_admin"],
     "dedup_scope": "every_3_days", "dedup_key": lambda t, today=None: _dedup_every_n_days(t, today or _today_eat(), 3),
     "condition": cond_perf_self_overdue},
    {"id": "REM-PERF-03", "name": "Manager Review Due — 3-Day Reminder", "group": "Performance",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "performance.manager_reminder", "recipients": ["line_manager"],
     "dedup_scope": "cycle", "dedup_key": _dedup_per_target_cycle,
     "condition": cond_perf_mgr_3day},
    {"id": "REM-PERF-04", "name": "Manager Review Overdue", "group": "Performance",
     "schedule_human": "Every 3 days at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.perf_mgr_overdue", "recipients": ["line_manager", "hr_admin"],
     "dedup_scope": "every_3_days", "dedup_key": lambda t, today=None: _dedup_every_n_days(t, today or _today_eat(), 3),
     "condition": cond_perf_mgr_overdue},
    {"id": "REM-PERF-05", "name": "PIP Weekly Check-In Reminder", "group": "Performance",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "performance.pip_checkin", "recipients": ["line_manager", "hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('pip_id')}:{t.get('checkin_date')}",
     "condition": cond_perf_pip_checkin},
    {"id": "REM-PERF-06", "name": "PIP End Date Approaching", "group": "Performance",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.pip_ending", "recipients": ["hr_admin", "line_manager"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('pip_id')}:end",
     "condition": cond_perf_pip_ending},

    # ── Group 4: Surveys ───────────────────────────────────────────────
    {"id": "REM-SURVEY-01", "name": "Survey Close — 3-Day Reminder", "group": "Surveys",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "survey.reminder", "recipients": ["employee"],
     "dedup_scope": "cycle", "dedup_key": _dedup_per_target_cycle,
     "condition": cond_survey_3day},
    {"id": "REM-SURVEY-02", "name": "Survey Close — Final Day Reminder", "group": "Surveys",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.survey_final_day", "recipients": ["employee"],
     "dedup_scope": "cycle", "dedup_key": _dedup_per_target_cycle,
     "condition": cond_survey_final_day},
    {"id": "REM-SURVEY-03", "name": "Solver Survey Close — 3-Day Reminder", "group": "Surveys",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.solver_survey_3day", "recipients": ["employee"],
     "dedup_scope": "cycle", "dedup_key": _dedup_per_target_cycle,
     "condition": cond_solver_survey_3day},

    # ── Group 5: Leave ─────────────────────────────────────────────────
    {"id": "REM-LEAVE-01", "name": "Leave Balance Low Alert", "group": "Leave",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "leave.balance_low", "recipients": ["employee", "hr_admin"],
     "dedup_scope": "weekly", "dedup_key": _dedup_weekly,
     "condition": cond_leave_balance_low},
    {"id": "REM-LEAVE-02", "name": "Leave Year End — Unused Leave Alert", "group": "Leave",
     "schedule_human": "Daily at 08:00 EAT (last 30 days of year)", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.leave_year_end", "recipients": ["employee", "hr_admin"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_leave_year_end},
    {"id": "REM-LEAVE-03", "name": "Pending Leave Request — Approver Reminder", "group": "Leave",
     "schedule_human": "Every 2 days at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.leave_approval", "recipients": ["line_manager"],
     "dedup_scope": "every_2_days", "dedup_key": lambda t, today=None: _dedup_every_n_days(t, today or _today_eat(), 2),
     "condition": cond_leave_approval_pending},
    {"id": "REM-LEAVE-04", "name": "Employee Return from Leave — Manager Alert", "group": "Leave",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.leave_return", "recipients": ["line_manager"],
     "dedup_scope": "per_record", "dedup_key": _dedup_per_leave_record,
     "condition": cond_leave_return},

    # ── Group 6: Recognition ───────────────────────────────────────────
    {"id": "REM-RECOG-01", "name": "Long-Service Anniversary Alert", "group": "Recognition",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "recognition.long_service", "recipients": ["employee", "hr_admin", "line_manager"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('employee_id')}:{t.get('milestone_years')}y",
     "condition": cond_long_service},
    {"id": "REM-RECOG-02", "name": "Recognition Calendar Event Approaching (14-Day)", "group": "Recognition",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.recog_event_14day", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('event_id')}:14",
     "condition": cond_recog_event_14day},
    {"id": "REM-RECOG-03", "name": "Recognition Event — 3-Day Reminder", "group": "Recognition",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.recog_event_3day", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('event_id')}:3",
     "condition": cond_recog_event_3day},
    {"id": "REM-RECOG-04", "name": "Solver Quarterly Award — Cycle Opening", "group": "Recognition",
     "schedule_human": "1st of each quarter at 08:00 EAT",
     "cron": {"month": "1,4,7,10", "day": 1, "hour": 8, "minute": 0},
     "template_key": "reminder.solver_award_open", "recipients": ["hr_admin"],
     "dedup_scope": "per_quarter", "dedup_key": _dedup_per_quarter,
     "condition": cond_solver_award_open},
    {"id": "REM-RECOG-05", "name": "Solver Quarterly Award — Deadline Reminder", "group": "Recognition",
     "schedule_human": "Daily at 08:00 EAT (last 7 days of quarter)", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.solver_award_deadline", "recipients": ["hr_admin"],
     "dedup_scope": "per_quarter", "dedup_key": _dedup_per_quarter,
     "condition": cond_solver_award_deadline},

    # ── Group 7: Policy ────────────────────────────────────────────────
    {"id": "REM-POLICY-01", "name": "Policy Acknowledgement — 3-Day Reminder", "group": "Policy",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "policy.ack_request", "recipients": ["employee"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('employee_id')}:{t.get('policy_title')}:{t.get('policy_version')}",
     "condition": cond_policy_3day},
    {"id": "REM-POLICY-02", "name": "Policy Acknowledgement Overdue", "group": "Policy",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "policy.ack_overdue", "recipients": ["employee", "hr_admin"],
     "dedup_scope": "weekly", "dedup_key": _dedup_weekly,
     "condition": cond_policy_overdue},

    # ── Group 8: Retention ─────────────────────────────────────────────
    {"id": "REM-RETAIN-01", "name": "Stay Interview Trigger — Tenure Milestone", "group": "Retention",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.stay_interview_due", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('employee_id')}:{t.get('tenure_years')}y",
     "condition": cond_stay_interview_due},
    {"id": "REM-RETAIN-02", "name": "Stay Interview Overdue After Scheduling", "group": "Retention",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.stay_interview_overdue", "recipients": ["hr_admin"],
     "dedup_scope": "per_record", "dedup_key": lambda t: f"{t.get('interview_id')}",
     "condition": cond_stay_interview_overdue},
    {"id": "REM-RETAIN-03", "name": "Flight Risk Review — Weekly Scan", "group": "Retention",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "retention.flight_risk_alert", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('employee_id')}:{t.get('risk_tier')}",
     "condition": cond_flight_risk_scan},

    # ── Group 9: Exit ──────────────────────────────────────────────────
    {"id": "REM-EXIT-01", "name": "Exit Clearance Task Overdue", "group": "Exit",
     "schedule_human": "Every 2 days at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.exit_task_overdue", "recipients": ["hr_admin"],
     "dedup_scope": "every_2_days", "dedup_key": lambda t, today=None: _dedup_every_n_days(t, today or _today_eat(), 2),
     "condition": cond_exit_task_overdue},
    {"id": "REM-EXIT-02", "name": "Last Working Day Approaching — Final Week Alert", "group": "Exit",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.exit_final_week", "recipients": ["hr_admin", "line_manager", "it_admin", "finance"],
     "dedup_scope": "milestone", "dedup_key": _dedup_per_target_milestone,
     "condition": cond_exit_final_week},
    {"id": "REM-EXIT-03", "name": "Confidentiality Acknowledgement Not Signed — Chase", "group": "Exit",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.exit_conf_ack_chase", "recipients": ["employee", "hr_admin"],
     "dedup_scope": "daily", "dedup_key": _dedup_daily,
     "condition": cond_exit_conf_ack_chase},

    # ── Group 10: Recruitment ──────────────────────────────────────────
    {"id": "REM-RECR-01", "name": "Candidate Stale in Pipeline", "group": "Recruitment",
     "schedule_human": "Weekly Mon 08:00 EAT", "cron": {"day_of_week": "mon", "hour": 8, "minute": 0},
     "template_key": "reminder.candidate_stale", "recipients": ["hr_admin"],
     "dedup_scope": "weekly", "dedup_key": lambda t, today=None: f"{t.get('candidate_id')}:W{(today or _today_eat()).isocalendar()[1]:02d}",
     "condition": cond_candidate_stale},
    {"id": "REM-RECR-02", "name": "Offer Expiry Approaching", "group": "Recruitment",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.offer_expiring", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('candidate_id')}:offer",
     "condition": cond_offer_expiring},

    # ── Group 11: System / HR Calendar ─────────────────────────────────
    {"id": "REM-SYS-01", "name": "HR Calendar Event Approaching — 14-Day Notice", "group": "System",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.hrcal_14day", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('event_id')}:14",
     "condition": cond_hrcal_14day},
    {"id": "REM-SYS-02", "name": "HR Calendar Event Approaching — 3-Day Notice", "group": "System",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.hrcal_3day", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('event_id')}:3",
     "condition": cond_hrcal_3day},
    {"id": "REM-SYS-03", "name": "Overdue HR Calendar Event", "group": "System",
     "schedule_human": "Daily at 08:00 EAT", "cron": {"hour": 8, "minute": 0},
     "template_key": "reminder.hrcal_overdue", "recipients": ["hr_admin"],
     "dedup_scope": "milestone", "dedup_key": lambda t: f"{t.get('event_id')}:overdue",
     "condition": cond_hrcal_overdue},
    {"id": "REM-SYS-04", "name": "Performance Review Cycle — Annual Opening Reminder", "group": "System",
     "schedule_human": "1 March 08:00 EAT (configurable)",
     "cron": {"month": 3, "day": 1, "hour": 8, "minute": 0},
     "template_key": "reminder.perf_cycle_due", "recipients": ["hr_admin"],
     "dedup_scope": "per_year", "dedup_key": _dedup_per_year,
     "condition": cond_perf_cycle_due},
    {"id": "REM-SYS-05", "name": "Alignment Survey Cycle — Annual Opening Reminder", "group": "System",
     "schedule_human": "15 March 08:00 EAT (configurable)",
     "cron": {"month": 3, "day": 15, "hour": 8, "minute": 0},
     "template_key": "reminder.survey_cycle_due", "recipients": ["hr_admin"],
     "dedup_scope": "per_year", "dedup_key": _dedup_per_year,
     "condition": cond_survey_cycle_due},
]


def get_rule(rule_id: str):
    for r in RULES:
        if r["id"] == rule_id:
            return r
    return None


def get_dedup_key(rule, target, today):
    """Resolve the dedup key, supporting fns that need `today` for time-bucketed scopes."""
    fn = rule.get("dedup_key")
    if not fn:
        return target.get("employee_id") or "x"
    try:
        return fn(target, today)
    except TypeError:
        return fn(target)
