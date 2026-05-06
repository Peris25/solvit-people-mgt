from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/budget", tags=["budget"])


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/envelope")
async def get_people_cost_envelope(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    latest = await db.gp_records.find_one({"tenant_id": "solvit"}, sort=[("period", -1)])
    if not latest:
        return {
            "period": datetime.now(timezone.utc).strftime("%Y-H1"),
            "actual_gp_kes": 0,
            "people_cost_envelope_kes": 0,
            "total_people_cost_kes": 0,
            "headroom_kes": 0,
            "utilization_pct": 0
        }
    return fmt(latest)


@router.post("/gp-record")
async def record_gp(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["finance"]:
        raise HTTPException(status_code=403, detail="Only Finance can record GP")
    db = get_db()
    body = await request.json()
    gp = body.get("actual_gp_kes", 0)
    envelope = gp * 0.5  # 50% GP = People Cost Envelope

    # Calculate total people cost
    employees = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}).to_list(200)
    monthly_cost = sum(e.get("current_salary_kes", 0) or 0 for e in employees)
    period = body.get("period", datetime.now(timezone.utc).strftime("%Y-H1"))

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "period": period,
        "actual_gp_kes": gp,
        "people_cost_envelope_kes": envelope,
        "total_people_cost_kes": monthly_cost,
        "headroom_kes": max(0, envelope - monthly_cost),
        "utilization_pct": round((monthly_cost / envelope * 100) if envelope > 0 else 0, 1),
        "recorded_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.gp_records.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/summary")
async def get_budget_summary(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()

    # Total monthly salary cost
    employees = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": {"$in": ["Active", "Probation", "PIP"]}}).to_list(200)
    total_salary = sum(e.get("current_salary_kes", 0) or 0 for e in employees)
    headcount = len(employees)

    # By department
    dept_costs = {}
    for emp in employees:
        dept = emp.get("department", "Unknown")
        dept_costs[dept] = dept_costs.get(dept, 0) + (emp.get("current_salary_kes", 0) or 0)

    # By level
    level_costs = {}
    for emp in employees:
        level = emp.get("role_level", "Unknown")
        level_costs[level] = level_costs.get(level, 0) + (emp.get("current_salary_kes", 0) or 0)

    return {
        "total_monthly_salary_kes": total_salary,
        "headcount": headcount,
        "average_salary_kes": round(total_salary / headcount if headcount > 0 else 0),
        "by_department": dept_costs,
        "by_level": level_costs
    }
