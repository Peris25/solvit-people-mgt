"""General Masters Settings — system-wide configuration module.

Administered primarily by IT Admin. HR Admin and Finance Manager have section-scoped
write access. All changes are logged to settings_audit (field, old_value, new_value,
changed_by, timestamp).

Storage model: a single document per category in `system_settings` collection
(`{category, tenant_id, values}`). On first read of any category, defaults are
auto-seeded.

Cross-module modules read settings via the helper `get_setting(category, key)` —
modules MUST NOT hardcode values that exist here.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/settings/masters", tags=["masters_settings"])

# --- Defaults ---------------------------------------------------------------
DEFAULTS = {
    "organisation": {
        "company_name": "Solvit Limited",
        "company_registration_number": "PVT-XXXX-2018",
        "registered_address": "Nairobi, Kenya",
        "financial_year_start_month": 1,
        "current_budget_cycle": "FY2026",
        "default_currency": "KES",
        "country_of_operation": "Kenya",
        "nssf_employer_pct": 6.0,
        "nhif_rates": [
            {"min_kes": 0,      "max_kes": 5999,    "amount_kes": 150},
            {"min_kes": 6000,   "max_kes": 7999,    "amount_kes": 300},
            {"min_kes": 8000,   "max_kes": 11999,   "amount_kes": 400},
            {"min_kes": 12000,  "max_kes": 14999,   "amount_kes": 500},
            {"min_kes": 15000,  "max_kes": 19999,   "amount_kes": 600},
            {"min_kes": 20000,  "max_kes": 24999,   "amount_kes": 750},
            {"min_kes": 25000,  "max_kes": 29999,   "amount_kes": 850},
            {"min_kes": 30000,  "max_kes": 34999,   "amount_kes": 900},
            {"min_kes": 35000,  "max_kes": 39999,   "amount_kes": 950},
            {"min_kes": 40000,  "max_kes": 44999,   "amount_kes": 1000},
            {"min_kes": 45000,  "max_kes": 49999,   "amount_kes": 1100},
            {"min_kes": 50000,  "max_kes": 59999,   "amount_kes": 1200},
            {"min_kes": 60000,  "max_kes": 69999,   "amount_kes": 1300},
            {"min_kes": 70000,  "max_kes": 79999,   "amount_kes": 1400},
            {"min_kes": 80000,  "max_kes": 89999,   "amount_kes": 1500},
            {"min_kes": 90000,  "max_kes": 99999,   "amount_kes": 1600},
            {"min_kes": 100000, "max_kes": 999999,  "amount_kes": 1700},
        ],
        "paye_brackets": [
            {"min_kes": 0,      "max_kes": 24000,    "rate_pct": 10},
            {"min_kes": 24001,  "max_kes": 32333,    "rate_pct": 25},
            {"min_kes": 32334,  "max_kes": 500000,   "rate_pct": 30},
            {"min_kes": 500001, "max_kes": 800000,   "rate_pct": 32.5},
            {"min_kes": 800001, "max_kes": 99999999, "rate_pct": 35},
        ],
        "working_days_per_week": 5,
        "standard_working_hours_per_day": 8,
        "probation_period_months": 3,
        "notice_period_by_level": [
            {"level": "L1", "days": 14},
            {"level": "L2", "days": 30},
            {"level": "L3", "days": 30},
            {"level": "L4", "days": 60},
            {"level": "L5", "days": 90},
        ],
    },
    "workforce": {
        "departments": [
            {"name": "Operations",                          "active": True},
            {"name": "Commercial & Business Development",   "active": True},
            {"name": "Finance",                             "active": True},
            {"name": "Technology",                          "active": True},
            {"name": "HR & People",                         "active": True},
        ],
        "job_levels": [
            {"level": "L1", "label": "Junior",            "pay_min_kes": 30000,  "pay_max_kes": 60000,  "bonus_eligible": False},
            {"level": "L2", "label": "Specialist",        "pay_min_kes": 60000,  "pay_max_kes": 95000,  "bonus_eligible": True},
            {"level": "L3", "label": "Senior",            "pay_min_kes": 95000,  "pay_max_kes": 145000, "bonus_eligible": True},
            {"level": "L4", "label": "Manager",           "pay_min_kes": 145000, "pay_max_kes": 220000, "bonus_eligible": True},
            {"level": "L5", "label": "Senior Leadership", "pay_min_kes": 220000, "pay_max_kes": 380000, "bonus_eligible": True},
        ],
        "employment_types": ["FTE", "Solver", "Contractor"],
        "fte_headcount_cap_per_dept": {},
        "solver_headcount_cap": None,
    },
    "performance": {
        "mid_year_month":  6,
        "year_end_month": 12,
        "review_process_weeks": 4,
        "peer_reviewers_min": 3,
        "section_weights": {"a_kpi_pct": 50, "b_peer_pct": 30, "c_client_pct": 20},
        "scoring_thresholds": {
            "Exceeded":  {"min": 1.00, "max": 1.49},
            "Met":       {"min": 1.50, "max": 1.99},
            "Below":     {"min": 2.00, "max": 2.49},
            "Forfeited": {"min": 2.50, "max": 5.00},
        },
        "bonus_multipliers": {
            "Exceeded":  {"min_pct": 115, "max_pct": 115},
            "Met":       {"min_pct": 100, "max_pct": 105},
            "Below":     {"min_pct": 0,   "max_pct": 50},
            "Forfeited": {"min_pct": 0,   "max_pct": 0},
        },
        "nine_box": {
            "perf_low_max": 1.99, "perf_solid_max": 2.49,
            "values_low_max": 1.99, "values_solid_max": 2.49,
        },
        "talent_density_target_pct": 85,
        "realignment_trigger_score": 2.0,
        "pip_trigger_score": 2.5,
        "probation_review_frequency_months": 1,
    },
    "budget_compensation": {
        "people_cost_envelope_pct_of_gp": 50,
        "current_gp_actual_kes": 37702972,
        "tier_1": {"revenue_target_kes": 77500000,  "pbt_target_kes":  9500000},
        "tier_2": {"revenue_target_kes": 178300000, "pbt_target_kes": 23600000},
        "salary_review_month": 1,
        "max_salary_increase_pct_without_finance": 0,
        "allocation_finance_approval_threshold_kes": 50000,
    },
    "onboarding": {
        "onboarding_duration_weeks": 3,
        "week_labels": [
            {"week": 1, "label": "Culture & Admin"},
            {"week": 2, "label": "Role Training"},
            {"week": 3, "label": "Consolidation & KPI Introduction"},
        ],
        "md_meeting_at_end_of_week": 3,
        "okr_signoff_days_before_md": 2,
        "pre_arrival_days_before_start": 5,
        "solver_induction_hours": 2,
        "solver_app_activation_window_days": 3,
    },
    "recruitment": {
        "tat_target_days": 30,
        "pipeline_stages": ["Competency Test", "Values Assessment", "Growth Mindset Assessment", "Physical Interview"],
        "interview_panel_by_level": {
            "md_direct_report": ["MD", "HR"],
            "non_md_direct_report": ["HR", "Line Manager"],
        },
        "casting_vote_holder": "HR",
        "offer_expiry_days": 5,
        "auto_reject_email_on_failure": True,
    },
    "alignment_surveys": {
        "cadence": "concurrent_with_review_cycle",
        "pillars": [
            {"name": "Environment",             "questions": 4, "cascade_enabled": True},
            {"name": "Values Alignment",        "questions": 4, "cascade_enabled": True},
            {"name": "Rewards & Recognition",   "questions": 4, "cascade_enabled": True},
        ],
        "likert_scale_points": 5,
        "score_method": "sum_div_max_x_100",
        "anonymous_with_reporting_line_tag": True,
        "solver_survey_enabled": True,
        "min_responses_to_display": 3,
    },
    "retention": {
        "stay_interview_months": [4, 10],
        "amber_alert_score_below": 60,
        "red_alert_score_below": 45,
        "exit_interview_due_days_after_resignation": "last_working_day",
        "attrition_target_pct": 10,
        "regrettable_definition": "Last review 9-box quadrant in [Star, Core Contributor]",
    },
    "recognition": {
        "events_per_year": 4,
        "event_months": [3, 6, 9, 12],
        "long_service_milestones_years": [1, 3, 5, 10],
        "peer_nomination_window_days": 5,
        "project_ownership_eligibility_score": "Exceeded",
    },
    "notifications": {
        "templates": {
            "onboarding_reminder":   {"subject": "Onboarding task due — {{employee_name}}",         "body": "Hi {{employee_name}},\n\nYour {{task_name}} is due on {{due_date}}.\n\n— Solvit People Platform"},
            "review_cycle_open":     {"subject": "{{cycle_label}} review cycle is now open",         "body": "Hi {{employee_name}},\n\nThe {{cycle_label}} performance review cycle is open until {{deadline}}.\n\n— Solvit People Platform"},
            "survey_launch":         {"subject": "Alignment survey now open",                        "body": "Hi {{employee_name}},\n\nPlease complete the {{cycle_label}} alignment survey by {{deadline}}.\n\n— Solvit People Platform"},
            "stay_interview_due":    {"subject": "Stay interview scheduled — {{employee_name}}",     "body": "Hi {{manager_name}},\n\nA stay interview with {{employee_name}} is due on {{due_date}}.\n\n— Solvit People Platform"},
            "flight_risk_alert":     {"subject": "Flight risk alert — {{employee_name}} ({{level}})", "body": "Hi {{manager_name}},\n\n{{employee_name}}'s flight risk has moved to {{level}}. Score: {{score}}.\n\n— Solvit People Platform"},
            "pip_issued":            {"subject": "PIP issued — {{employee_name}}",                   "body": "Hi {{employee_name}},\n\nA Performance Improvement Plan has been issued. Effective: {{effective_date}}.\n\n— Solvit People Platform"},
            "offer_sent":            {"subject": "Offer of employment — {{candidate_name}}",         "body": "Dear {{candidate_name}},\n\nWe are delighted to offer you the role of {{role_title}}. Please respond by {{expiry_date}}.\n\n— Solvit Limited"},
            "form28_gate_confirmed": {"subject": "Form 28 confirmed — {{tier}} active",              "body": "GP Actual confirmed. Tier {{tier}} active. Bonus & salary approvals unlocked.\n\n— Solvit People Platform"},
        },
        "automation_trigger_offsets_days": {
            "send_peer_review_invites":   -7,
            "send_review_cycle_open":      0,
            "send_survey_launch":          0,
            "send_stay_interview_invite": -3,
            "send_pre_arrival_email":     -5,
            "send_offer_expiry_warning":  -2,
        },
        "system_timezone": "Africa/Nairobi",
        "date_format": "DD/MM/YYYY",
        "session_timeout_minutes": 30,
    },
    "lookups": {
        "employment_status":  ["Active", "On Leave", "Probation", "Exited"],
        "contract_type":      ["Permanent", "Fixed Term", "Probation", "Gig"],
        "leave_types":        ["Annual", "Sick", "Maternity", "Paternity", "Compassionate", "Unpaid"],
        "disciplinary_types": ["Verbal Warning", "Written Warning", "Final Warning", "Dismissal"],
        "training_categories":["Technical", "Leadership", "Compliance", "Role-specific"],
        "project_status":     ["Not Started", "In Progress", "Completed", "On Hold"],
        "solver_tiers":       ["Elite", "Active", "At Risk", "Inactive"],
    },
}

# Section-level write access. IT Admin always has write.
WRITE_ACCESS = {
    "organisation":         ["it_admin"],
    "workforce":            ["it_admin"],
    "performance":          ["it_admin", "hr_admin"],
    "budget_compensation":  ["it_admin", "finance"],
    "onboarding":           ["it_admin", "hr_admin"],
    "recruitment":          ["it_admin", "hr_admin"],
    "alignment_surveys":    ["it_admin", "hr_admin"],
    "retention":            ["it_admin", "hr_admin"],
    "recognition":          ["it_admin", "hr_admin"],
    "notifications":        ["it_admin"],
    "lookups":              ["it_admin", "hr_admin"],
}


# --- Internal helpers -------------------------------------------------------
async def _ensure_seeded(db, category: str):
    """Idempotent — insert defaults the first time a category is requested."""
    if category not in DEFAULTS:
        raise HTTPException(status_code=404, detail=f"Unknown settings category '{category}'")
    existing = await db.system_settings.find_one({"tenant_id": "solvit", "category": category})
    if existing:
        return existing
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "category": category,
        "values": DEFAULTS[category],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "system_seed",
    }
    await db.system_settings.insert_one(doc)
    return doc


async def get_setting(category: str, key: str = None, default=None):
    """Programmatic helper used by other modules to read live settings."""
    db = get_db()
    if db is None:
        return default
    doc = await db.system_settings.find_one({"tenant_id": "solvit", "category": category})
    if not doc:
        # Lazy seed
        doc = await _ensure_seeded(db, category)
    values = doc.get("values", {})
    if key is None:
        return values
    return values.get(key, default)


def _has_read_access(role: str) -> bool:
    return role in {"it_admin", "hr_admin", "hr_manager", "finance"}


def _can_write(role: str, category: str) -> bool:
    return role in WRITE_ACCESS.get(category, [])


def _flatten_diff(old: dict, new: dict, prefix: str = "") -> list:
    """Recursive shallow-diff to surface field-level changes for the audit log."""
    changes = []
    keys = set((old or {}).keys()) | set((new or {}).keys())
    for k in keys:
        path = f"{prefix}.{k}" if prefix else k
        ov, nv = (old or {}).get(k), (new or {}).get(k)
        if isinstance(ov, dict) and isinstance(nv, dict):
            changes.extend(_flatten_diff(ov, nv, path))
        elif ov != nv:
            changes.append({"field": path, "old_value": ov, "new_value": nv})
    return changes


# --- Routes ----------------------------------------------------------------
@router.get("")
async def list_categories(request: Request):
    """List all categories + write-access summary for the caller's role."""
    user = await get_current_user(request)
    if not _has_read_access(user["role"]):
        raise HTTPException(status_code=403, detail="No access to Masters Settings")
    return {
        "categories": list(DEFAULTS.keys()),
        "my_role": user["role"],
        "write_access": {c: _can_write(user["role"], c) for c in DEFAULTS.keys()},
    }


@router.get("/all")
async def get_all_settings(request: Request):
    """Single-shot fetch of every category — used by other frontend pages
    to apply lookup-table values without N requests."""
    user = await get_current_user(request)
    db = get_db()
    out = {}
    for cat in DEFAULTS.keys():
        # Public categories that any authenticated user can read for lookups.
        # Restrict admin-sensitive categories to roles with read access.
        if cat in ("notifications", "organisation") and not _has_read_access(user["role"]):
            continue
        doc = await _ensure_seeded(db, cat)
        out[cat] = doc["values"]
    return out


@router.get("/{category}")
async def get_category(category: str, request: Request):
    user = await get_current_user(request)
    if not _has_read_access(user["role"]):
        raise HTTPException(status_code=403, detail="No access to Masters Settings")
    db = get_db()
    doc = await _ensure_seeded(db, category)
    return {
        "category": category,
        "values": doc["values"],
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
        "can_write": _can_write(user["role"], category),
    }


@router.put("/{category}")
async def update_category(category: str, request: Request):
    user = await get_current_user(request)
    if category not in DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown category")
    if not _can_write(user["role"], category):
        raise HTTPException(status_code=403, detail=f"You cannot edit '{category}'")
    db = get_db()
    doc = await _ensure_seeded(db, category)
    body = await request.json()
    new_values = body.get("values")
    if not isinstance(new_values, dict):
        raise HTTPException(status_code=400, detail="`values` must be an object")

    # Diff for audit log
    diffs = _flatten_diff(doc["values"], new_values)
    now = datetime.now(timezone.utc).isoformat()

    await db.system_settings.update_one(
        {"_id": doc["_id"]},
        {"$set": {"values": new_values, "updated_at": now, "updated_by": user["id"]}}
    )

    if diffs:
        await db.settings_audit.insert_many([{
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "category": category,
            "field": d["field"],
            "old_value": d["old_value"],
            "new_value": d["new_value"],
            "changed_by": user["id"],
            "changed_by_name": user.get("full_name") or user.get("email"),
            "changed_by_role": user.get("role"),
            "timestamp": now,
        } for d in diffs])

    return {"category": category, "values": new_values, "changes": diffs, "updated_at": now}


@router.post("/{category}/reset")
async def reset_category_to_defaults(category: str, request: Request):
    """IT Admin-only: revert a category to defaults. Useful for recovery."""
    user = await get_current_user(request)
    if user["role"] != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    if category not in DEFAULTS:
        raise HTTPException(status_code=404, detail="Unknown category")
    db = get_db()
    doc = await _ensure_seeded(db, category)
    diffs = _flatten_diff(doc["values"], DEFAULTS[category])
    now = datetime.now(timezone.utc).isoformat()
    await db.system_settings.update_one(
        {"_id": doc["_id"]},
        {"$set": {"values": DEFAULTS[category], "updated_at": now, "updated_by": user["id"]}}
    )
    if diffs:
        await db.settings_audit.insert_many([{
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "category": category,
            "field": d["field"],
            "old_value": d["old_value"],
            "new_value": d["new_value"],
            "changed_by": user["id"],
            "changed_by_name": user.get("full_name") or user.get("email"),
            "changed_by_role": user.get("role"),
            "action": "reset_to_default",
            "timestamp": now,
        } for d in diffs])
    return {"category": category, "values": DEFAULTS[category], "changes": diffs, "reset": True}


@router.get("/audit/log")
async def get_audit_log(request: Request, category: str | None = None, limit: int = 200):
    """IT Admin and HR Admin can view the audit trail."""
    user = await get_current_user(request)
    if user["role"] not in ("it_admin", "hr_admin"):
        raise HTTPException(status_code=403, detail="Audit log restricted to IT Admin and HR Admin")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if category:
        q["category"] = category
    rows = await db.settings_audit.find(q).sort("timestamp", -1).to_list(min(limit, 500))
    for r in rows:
        r["id"] = r.get("id") or str(r.get("_id", ""))
        r.pop("_id", None)
    return rows
