from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/compensation", tags=["compensation"])


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/pay-bands")
async def get_pay_bands(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    bands = await db.pay_bands.find({"tenant_id": "solvit"}).sort("band", 1).to_list(20)
    return [fmt(b) for b in bands]


@router.put("/pay-bands/{band_id}")
async def update_pay_band(band_id: str, request: Request):
    """HR Admin (or HR Manager) can edit pay band min/mid/max and roles."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can edit pay bands")
    db = get_db()
    body = await request.json()
    allowed = {"min_kes", "mid_kes", "max_kes", "roles", "note"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = user["id"]
    try:
        result = await db.pay_bands.find_one_and_update(
            {"_id": ObjectId(band_id)}, {"$set": update}, return_document=True
        )
    except Exception:
        result = await db.pay_bands.find_one_and_update(
            {"id": band_id}, {"$set": update}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Pay band not found")
    # Audit
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "pay_band.update",
        "entity": f"pay_band:{band_id}",
        "performed_by": user["id"],
        "metadata": update,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return fmt(result)


@router.get("/pay-bands/alerts")
async def get_pay_band_alerts(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    alerts = await db.pay_band_alerts.find({"tenant_id": "solvit", "status": "Active"}).to_list(50)
    return [fmt(a) for a in alerts]


@router.get("/salary-review")
async def get_salary_reviews(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    reviews = await db.salary_reviews.find({"tenant_id": "solvit"}).sort("created_at", -1).to_list(100)
    return [fmt(r) for r in reviews]


@router.post("/salary-review")
async def create_salary_review(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **body,
        "status": "Pending_Finance_Approval",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.salary_reviews.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the employee with the salary review outcome (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        emp_id = body.get("employee_id")
        if emp_id:
            await fire_and_forget(db, "comp.salary_review", employee_id=emp_id, extra={
                "new_salary_kes": body.get("new_salary_kes"),
                "old_salary_kes": body.get("old_salary_kes"),
                "increment_pct": body.get("increment_pct"),
                "effective_date": body.get("effective_date"),
                "rationale": body.get("rationale", ""),
            })
    except Exception:
        pass
    return doc


@router.get("/bonus/calculator")
async def get_bonus_calculator(request: Request, tier: str = "Tier1"):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    # Get active employees with performance scores
    employees = await db.employees.find({
        "tenant_id": "solvit",
        "lifecycle_state": "Active",
        "last_performance_score": {"$ne": None}
    }).to_list(100)

    tier_rates = {
        "Tier1": {"Exceeded": 0.15, "Met": 0.08, "Below": 0.0},
        "Tier2": {"Exceeded": 0.20, "Met": 0.12, "Below": 0.0}
    }
    rates = tier_rates.get(tier, tier_rates["Tier1"])

    bonuses = []
    for emp in employees:
        score = emp.get("last_performance_score", 2.0)
        if score <= 1.49:
            rating = "Exceeded"
        elif score <= 1.99:
            rating = "Met"
        else:
            rating = "Below"
        salary = emp.get("current_salary_kes", 0) or 0
        rate = rates.get(rating, 0)
        bonus_amount = int(salary * rate)
        bonuses.append({
            "employee_id": str(emp.get("id", str(emp["_id"]))),
            "name": emp.get("full_name"),
            "role": emp.get("role_title"),
            "department": emp.get("department"),
            "salary": salary,
            "performance_score": score,
            "rating": rating,
            "bonus_rate": rate,
            "bonus_amount_kes": bonus_amount,
            "tier": tier
        })
    total = sum(b["bonus_amount_kes"] for b in bonuses)
    return {"tier": tier, "employees": bonuses, "total_bonus_kes": total}


@router.get("/gp-gate")
async def get_gp_gate(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    gate = await db.gp_gate.find_one({"tenant_id": "solvit"}, sort=[("created_at", -1)])
    if not gate:
        return {"gate_open": False, "message": "No GP gate decision recorded"}
    return fmt(gate)


@router.post("/gp-gate")
async def set_gp_gate(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["finance"]:
        raise HTTPException(status_code=403, detail="Only Finance can update GP gate")
    db = get_db()
    body = await request.json()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **body,
        "confirmed_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.gp_gate.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc
