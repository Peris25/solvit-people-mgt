"""Budget Governance Module (M12) — full implementation per spec.

Sections implemented:
- §1 GP Actual: Finance-only field. Until submitted, Envelope/Headroom/Tier locked.
- §2 Envelope = GP Actual × 50% (annual).
- §3 Total Annual People Cost = Σ(Active FTE monthly base × 12). Solvers excluded.
- §4 Headroom = Envelope − Total Annual People Cost (positive=green, negative=red).
- §5 2026 reference baseline pre-loaded.
- §6 Tier Switch — Tier 1 / Tier 2 thresholds, locked until Form 28 confirmed.
- §7 Form 28 — Finance Manager confirmation gate (signature + timestamp).
- §8 Department breakdown — only the 5 confirmed Solvit departments.
- §9 Module access — Finance: full; HR Admin: read; others: none.
- §10 HR Budget Allocation — headroom allocation entries; KES 50k+ requires Finance approval.
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/budget", tags=["budget"])

# §8 The five confirmed Solvit departments (no "Leadership"). Aliases on the right
# map any historical/incorrect labels onto the canonical name.
CANONICAL_DEPARTMENTS = ["Operations", "Commercial & Business Development", "Finance", "Technology", "HR & People"]
DEPARTMENT_ALIASES = {
    "Operations": "Operations",
    "Commercial": "Commercial & Business Development",
    "Commercial & Business Development": "Commercial & Business Development",
    "Business Development": "Commercial & Business Development",
    "Finance": "Finance",
    "Technology": "Technology",
    "Tech": "Technology",
    "HR_People": "HR & People",
    "HR People": "HR & People",
    "HR & People": "HR & People",
    "People": "HR & People",
    "Leadership": "HR & People",  # MD/Executive reassigned to functional dept (HR & People per FRD §8)
    "Valuation": "Operations",     # Valuation rolls into Operations
}

# §5 Reference baseline (2026)
BASELINE_2026 = {
    "period": "2026",
    "actual_gp_kes": 37_702_972,
    "people_cost_envelope_kes": 18_851_486,   # 50% of GP
    "total_annual_people_cost_kes": 18_720_000,
    "headroom_kes": 131_486,
    "status": "Within envelope",
    "is_baseline": True,
}

# §6 Tier thresholds
TIER_THRESHOLDS = {
    "Tier_1": {"min_revenue_kes": 77_500_000,  "min_pbt_kes":  9_500_000},
    "Tier_2": {"min_revenue_kes": 178_300_000, "min_pbt_kes": 23_600_000},
}


def fmt(doc):
    if not doc:
        return None
    if not doc.get("id"):
        doc["id"] = str(doc.get("_id", ""))
    doc.pop("_id", None)
    return doc


def _canonical_dept(raw: str) -> str:
    return DEPARTMENT_ALIASES.get(raw, raw or "Unassigned")


async def _ensure_baseline(db):
    """Insert the 2026 baseline GP record once."""
    existing = await db.gp_records.find_one({"tenant_id": "solvit", "period": "2026"})
    if existing:
        return
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **BASELINE_2026,
        "submitted_by": "system_baseline",
        "submitted_by_name": "System (Pre-loaded baseline)",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "form28_confirmed": False,
        "active_tier": None,
    }
    await db.gp_records.insert_one(doc)


async def _compute_total_people_cost(db) -> dict:
    """§3 Σ Active FTE monthly base × 12. Solvers excluded entirely."""
    employees = await db.employees.find({
        "tenant_id": "solvit",
        "lifecycle_state": "Active",
        "$or": [{"employment_type": {"$ne": "Solver"}}, {"employment_type": {"$exists": False}}],
    }).to_list(500)
    monthly_total = 0
    headcount = 0
    by_dept = {d: {"headcount": 0, "annual_cost_kes": 0} for d in CANONICAL_DEPARTMENTS}
    for e in employees:
        salary = int(e.get("current_salary_kes") or 0)
        monthly_total += salary
        headcount += 1
        dept = _canonical_dept(e.get("department"))
        if dept not in by_dept:
            by_dept[dept] = {"headcount": 0, "annual_cost_kes": 0}
        by_dept[dept]["headcount"] += 1
        by_dept[dept]["annual_cost_kes"] += salary * 12
    return {
        "total_monthly_kes": monthly_total,
        "total_annual_kes": monthly_total * 12,
        "active_fte_headcount": headcount,
        "by_department": by_dept,
    }


@router.get("/envelope")
async def get_envelope(request: Request):
    """§1–§4 Returns envelope, total cost, headroom and gating status."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance", "executive", "it_admin"]:
        raise HTTPException(status_code=403, detail="No access to Budget Governance")
    db = get_db()
    await _ensure_baseline(db)
    # Live setting — envelope % of GP (default 50)
    from routes.masters_settings import get_setting
    envelope_pct = await get_setting("budget_compensation", "people_cost_envelope_pct_of_gp", 50)
    tier_1 = await get_setting("budget_compensation", "tier_1", TIER_THRESHOLDS["Tier_1"])
    tier_2 = await get_setting("budget_compensation", "tier_2", TIER_THRESHOLDS["Tier_2"])
    live_thresholds = {
        "Tier_1": {"min_revenue_kes": tier_1.get("revenue_target_kes"), "min_pbt_kes": tier_1.get("pbt_target_kes")},
        "Tier_2": {"min_revenue_kes": tier_2.get("revenue_target_kes"), "min_pbt_kes": tier_2.get("pbt_target_kes")},
    }
    gp = await db.gp_records.find_one({"tenant_id": "solvit"}, sort=[("submitted_at", -1)])
    cost = await _compute_total_people_cost(db)
    finance_input_received = bool(gp and gp.get("actual_gp_kes"))

    if not finance_input_received:
        return {
            "finance_input_received": False,
            "period": (gp or {}).get("period") or datetime.now(timezone.utc).strftime("%Y"),
            "actual_gp_kes": None,
            "people_cost_envelope_kes": None,
            "envelope_pct_of_gp": envelope_pct,
            "total_annual_people_cost_kes": cost["total_annual_kes"],
            "active_fte_headcount": cost["active_fte_headcount"],
            "headroom_kes": None,
            "headroom_status": "Awaiting Finance Input",
            "tier_status": "Tier Switch locked — Finance input required",
            "active_tier": None,
            "form28_confirmed": False,
            "tier_thresholds": live_thresholds,
        }

    actual_gp = int(gp.get("actual_gp_kes") or 0)
    envelope = int(actual_gp * (envelope_pct / 100.0))
    total_cost = cost["total_annual_kes"]
    headroom = envelope - total_cost
    headroom_status = "Within envelope" if headroom >= 0 else "Over envelope — Finance review required"
    tier_status = "Tier Unconfirmed — Awaiting Finance"
    if gp.get("form28_confirmed") and gp.get("active_tier"):
        tier_status = f"{gp['active_tier'].replace('_', ' ')} Active"

    return {
        "finance_input_received": True,
        "period": gp.get("period"),
        "actual_gp_kes": actual_gp,
        "people_cost_envelope_kes": envelope,
        "envelope_pct_of_gp": envelope_pct,
        "total_annual_people_cost_kes": total_cost,
        "active_fte_headcount": cost["active_fte_headcount"],
        "headroom_kes": headroom,
        "headroom_status": headroom_status,
        "tier_status": tier_status,
        "active_tier": gp.get("active_tier"),
        "form28_confirmed": bool(gp.get("form28_confirmed")),
        "tier_thresholds": live_thresholds,
    }


@router.get("/summary")
async def get_summary(request: Request):
    """§8 Department breakdown + headcount + average salary."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance", "executive", "it_admin"]:
        raise HTTPException(status_code=403, detail="No access to Budget Governance")
    db = get_db()
    cost = await _compute_total_people_cost(db)
    gp = await db.gp_records.find_one({"tenant_id": "solvit"}, sort=[("submitted_at", -1)])
    from routes.masters_settings import get_setting
    envelope_pct = await get_setting("budget_compensation", "people_cost_envelope_pct_of_gp", 50)
    envelope = int((gp or {}).get("actual_gp_kes", 0) * (envelope_pct / 100.0)) if gp and gp.get("actual_gp_kes") else None

    by_dept = []
    for dept_name, info in cost["by_department"].items():
        annual = info["annual_cost_kes"]
        pct_of_envelope = round(annual / envelope * 100, 1) if envelope else None
        by_dept.append({
            "department": dept_name,
            "headcount": info["headcount"],
            "annual_cost_kes": annual,
            "pct_of_envelope": pct_of_envelope,
        })
    by_dept.sort(key=lambda x: -x["annual_cost_kes"])
    return {
        "total_monthly_salary_kes": cost["total_monthly_kes"],
        "total_annual_people_cost_kes": cost["total_annual_kes"],
        "active_fte_headcount": cost["active_fte_headcount"],
        "average_salary_kes": (cost["total_monthly_kes"] // cost["active_fte_headcount"]) if cost["active_fte_headcount"] else 0,
        "envelope_kes": envelope,
        "by_department": by_dept,
        "departments_canonical": CANONICAL_DEPARTMENTS,
    }


@router.post("/gp-record")
async def record_gp(request: Request):
    """§1 Finance-only: submit / update GP Actual for the current cycle."""
    user = await get_current_user(request)
    if user["role"] != "finance":
        raise HTTPException(status_code=403, detail="GP Actual is a Finance-only field.")
    db = get_db()
    body = await request.json()
    period = body.get("period") or datetime.now(timezone.utc).strftime("%Y")
    gp = int(body.get("actual_gp_kes") or 0)
    if gp <= 0:
        raise HTTPException(status_code=400, detail="actual_gp_kes must be > 0")

    cost = await _compute_total_people_cost(db)
    from routes.masters_settings import get_setting
    envelope_pct = await get_setting("budget_compensation", "people_cost_envelope_pct_of_gp", 50)
    envelope = int(gp * (envelope_pct / 100.0))
    headroom = envelope - cost["total_annual_kes"]

    existing = await db.gp_records.find_one({"tenant_id": "solvit", "period": period})
    update = {
        "actual_gp_kes": gp,
        "people_cost_envelope_kes": envelope,
        "total_annual_people_cost_kes": cost["total_annual_kes"],
        "headroom_kes": headroom,
        "status": "Within envelope" if headroom >= 0 else "Over envelope — Finance review required",
        "submitted_by": user["id"],
        "submitted_by_name": user.get("full_name") or user.get("email"),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "is_baseline": False,
    }
    if existing:
        await db.gp_records.update_one({"_id": existing["_id"]}, {"$set": update})
        return fmt({**existing, **update})
    doc = {"id": str(uuid.uuid4()), "tenant_id": "solvit", "period": period,
           "form28_confirmed": False, "active_tier": None, **update}
    await db.gp_records.insert_one(doc)
    return fmt(doc)


@router.post("/form-28")
async def submit_form28(request: Request):
    """§7 Form 28 — Finance Manager confirms GP Actual + active Tier.
    Unlocks bonus + salary increase approvals downstream."""
    user = await get_current_user(request)
    if user["role"] != "finance":
        raise HTTPException(status_code=403, detail="Form 28 is signed by Finance Manager only.")
    db = get_db()
    body = await request.json()
    active_tier = body.get("active_tier")
    if active_tier not in ["Tier_1", "Tier_2"]:
        raise HTTPException(status_code=400, detail="active_tier must be 'Tier_1' or 'Tier_2'")
    period = body.get("period") or datetime.now(timezone.utc).strftime("%Y")
    gp = await db.gp_records.find_one({"tenant_id": "solvit", "period": period})
    if not gp or not gp.get("actual_gp_kes"):
        raise HTTPException(status_code=400, detail="Submit GP Actual first before Form 28")

    confirmation = {
        "form28_confirmed": True,
        "active_tier": active_tier,
        "form28_signed_by": user["id"],
        "form28_signed_by_name": user.get("full_name") or user.get("email"),
        "form28_signed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.gp_records.update_one({"_id": gp["_id"]}, {"$set": confirmation})

    # Audit
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "form28.submit",
        "entity": f"gp_record:{period}",
        "performed_by": user["id"],
        "metadata": {**confirmation, "period": period},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Notification — bonus / salary approvals are now unlocked
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "recipient_role": "hr_admin",
        "category": "Budget",
        "title": f"Form 28 confirmed — {active_tier.replace('_', ' ')} active",
        "message": "GP Actual confirmed and active Tier set. Bonus & salary increase approvals unlocked.",
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return fmt({**gp, **confirmation})


# §10 HR Budget Allocation — Headroom Administration
@router.get("/allocations")
async def list_allocations(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    allocs = await db.budget_allocations.find({"tenant_id": "solvit"}).sort("created_at", -1).to_list(200)
    return [fmt(a) for a in allocs]


@router.get("/allocations/summary")
async def allocations_summary(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance", "it_admin"]:
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    gp = await db.gp_records.find_one({"tenant_id": "solvit"}, sort=[("submitted_at", -1)])
    if not (gp and gp.get("actual_gp_kes")):
        return {"unlocked": False, "headroom_kes": 0, "allocated_kes": 0, "remaining_kes": 0}
    cost = await _compute_total_people_cost(db)
    from routes.masters_settings import get_setting
    envelope_pct = await get_setting("budget_compensation", "people_cost_envelope_pct_of_gp", 50)
    headroom = int(gp["actual_gp_kes"] * (envelope_pct / 100.0)) - cost["total_annual_kes"]
    allocs = await db.budget_allocations.find({
        "tenant_id": "solvit",
        "status": {"$in": ["Approved", "Spent"]},
    }).to_list(500)
    # For Spent rows, count actual spent (variance returns to unallocated pool).
    # For Approved rows still committed, count the full allocated amount.
    allocated = 0
    for a in allocs:
        if a.get("status") == "Spent" and a.get("spent_amount_kes") is not None:
            allocated += int(a.get("spent_amount_kes") or 0)
        else:
            allocated += int(a.get("amount_kes") or 0)
    return {
        "unlocked": True,
        "headroom_kes": headroom,
        "allocated_kes": allocated,
        "remaining_kes": max(0, headroom - allocated),
        "form28_confirmed": bool(gp.get("form28_confirmed")),
    }


@router.post("/allocations")
async def create_allocation(request: Request):
    """HR Admin creates an allocation against confirmed headroom.
    Allocations > KES 50k require Finance approval (Pending_Finance status)."""
    user = await get_current_user(request)
    if user["role"] != "hr_admin":
        raise HTTPException(status_code=403, detail="HR Admin only")
    db = get_db()
    body = await request.json()
    amount = int(body.get("amount_kes") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_kes must be positive")

    # Block overage
    summary = await allocations_summary(request)
    if amount > summary["remaining_kes"]:
        raise HTTPException(status_code=400, detail=f"Amount exceeds remaining unallocated headroom (KES {summary['remaining_kes']:,})")

    # Finance approval threshold pulled from Masters Settings (default 50,000)
    from routes.masters_settings import get_setting
    finance_threshold = await get_setting("budget_compensation", "allocation_finance_approval_threshold_kes", 50_000)
    needs_finance = amount >= finance_threshold
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "initiative_name": body.get("initiative_name", "").strip() or "Untitled initiative",
        "budget_cycle": body.get("budget_cycle") or datetime.now(timezone.utc).strftime("%Y"),
        "amount_kes": amount,
        "linked_module": body.get("linked_module", "General HR"),
        "status": "Pending_Finance" if needs_finance else "Approved",
        "notes": body.get("notes", ""),
        "spent_amount_kes": None,
        "variance_kes": None,
        "created_by": user["id"],
        "created_by_name": user.get("full_name") or user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": None if needs_finance else user["id"],
        "approved_at": None if needs_finance else datetime.now(timezone.utc).isoformat(),
    }
    await db.budget_allocations.insert_one(doc)
    return fmt(doc)


@router.put("/allocations/{alloc_id}")
async def update_allocation(alloc_id: str, request: Request):
    """HR Admin can edit Planned/Approved (e.g. amend amount, mark Spent).
    Finance can flip Pending_Finance → Approved.
    On Spent, variance returns to unallocated pool automatically."""
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    try:
        alloc = await db.budget_allocations.find_one({"_id": ObjectId(alloc_id)})
    except Exception:
        alloc = await db.budget_allocations.find_one({"id": alloc_id})
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}

    # Finance approval flip
    if "status" in body and body["status"] == "Approved" and alloc.get("status") == "Pending_Finance":
        if user["role"] != "finance":
            raise HTTPException(status_code=403, detail="Only Finance can approve allocations ≥ KES 50,000")
        update["status"] = "Approved"
        update["approved_by"] = user["id"]
        update["approved_at"] = datetime.now(timezone.utc).isoformat()
    # HR Admin marks Spent
    elif body.get("status") == "Spent":
        if user["role"] != "hr_admin":
            raise HTTPException(status_code=403, detail="HR Admin only")
        spent = int(body.get("spent_amount_kes") or 0)
        if spent < 0:
            raise HTTPException(status_code=400, detail="spent_amount_kes must be ≥ 0")
        update["status"] = "Spent"
        update["spent_amount_kes"] = spent
        update["variance_kes"] = int(alloc.get("amount_kes", 0)) - spent
        update["spent_at"] = datetime.now(timezone.utc).isoformat()
    # HR Admin amends amount/notes/initiative_name on a Planned/Pending entry
    else:
        if user["role"] != "hr_admin":
            raise HTTPException(status_code=403, detail="HR Admin only")
        for k in ["initiative_name", "amount_kes", "linked_module", "notes"]:
            if k in body:
                update[k] = body[k]

    try:
        result = await db.budget_allocations.find_one_and_update(
            {"_id": alloc["_id"]}, {"$set": update}, return_document=True
        )
    except Exception:
        result = await db.budget_allocations.find_one_and_update(
            {"id": alloc_id}, {"$set": update}, return_document=True
        )
    return fmt(result)


@router.delete("/allocations/{alloc_id}")
async def delete_allocation(alloc_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] != "hr_admin":
        raise HTTPException(status_code=403, detail="HR Admin only")
    db = get_db()
    try:
        await db.budget_allocations.delete_one({"_id": ObjectId(alloc_id)})
    except Exception:
        await db.budget_allocations.delete_one({"id": alloc_id})
    return {"deleted": True}
