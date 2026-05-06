from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/retention", tags=["retention"])

FLIGHT_RISK_SIGNALS = {
    "alignment_score": {"weight": 30, "description": "Alignment Survey score"},
    "performance_trajectory": {"weight": 25, "description": "Performance trend"},
    "salary_position": {"weight": 25, "description": "Position in pay band"},
    "tenure_milestone": {"weight": 20, "description": "Tenure risk milestone"}
}


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


def calculate_flight_risk(employee: dict, alignment_score: float = None, performance_score: float = None) -> dict:
    score = 0
    # Alignment score contribution (30 pts max — lower alignment = higher risk)
    if alignment_score is not None:
        alignment_risk = max(0, 30 - int(alignment_score * 0.3))
        score += alignment_risk

    # Performance trajectory (25 pts)
    perf = performance_score or employee.get("last_performance_score")
    if perf:
        if perf >= 2.5:
            score += 25  # Forfeited = highest risk
        elif perf >= 2.0:
            score += 15  # Below = high risk
        elif perf <= 1.5:
            score += 5   # Exceeded = low risk

    # Salary position (25 pts max)
    salary = employee.get("current_salary_kes", 0)
    role_level = employee.get("role_level", "L1")
    # Simplified: if salary is low, risk is higher
    score += 10  # Default medium risk

    # Tenure milestone (20 pts)
    start_date = employee.get("start_date")
    if start_date:
        try:
            tenure_years = (datetime.now(timezone.utc) - datetime.fromisoformat(start_date)).days / 365.25
            if 1.5 <= tenure_years <= 2.5 or 4.5 <= tenure_years <= 5.5:
                score += 20  # Peak resignation risk milestones
            elif tenure_years < 0.5:
                score += 15
        except Exception:
            pass

    # Determine risk level
    if score <= 20:
        level = "Low"
    elif score <= 45:
        level = "Elevated"
    elif score <= 70:
        level = "High"
    else:
        level = "Critical"

    return {"score": min(score, 105), "level": level}


@router.get("")
async def list_flight_risks(request: Request, risk_level: Optional[str] = None):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    query = {"tenant_id": "solvit", "lifecycle_state": {"$in": ["Active", "PIP", "Realignment"]}}
    if risk_level:
        query["flight_risk_level"] = risk_level
    employees = await db.employees.find(query).sort("flight_risk_score", -1).to_list(200)
    return [fmt(e) for e in employees]


@router.post("/calculate/{employee_id}")
async def calculate_risk(employee_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    try:
        emp = await db.employees.find_one({"_id": ObjectId(employee_id)})
    except Exception:
        emp = await db.employees.find_one({"id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    risk = calculate_flight_risk(emp)
    old_level = emp.get("flight_risk_level")

    await db.employees.update_one(
        {"_id": emp["_id"]},
        {"$set": {"flight_risk_score": risk["score"], "flight_risk_level": risk["level"], "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Fire automation events if level changed
    if old_level != risk["level"]:
        from automation.engine import automation_engine
        await automation_engine.fire_event(f"flight_risk_{risk['level'].lower()}", {"employee_id": employee_id})

    return {**risk, "employee_id": employee_id}


@router.get("/stay-interviews")
async def list_stay_interviews(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    interviews = await db.stay_interviews.find({"tenant_id": "solvit"}).sort("created_at", -1).to_list(100)
    return [fmt(i) for i in interviews]


@router.post("/stay-interviews")
async def create_stay_interview(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **body,
        "status": body.get("status") or "Scheduled",
        "conducted_by": user["id"],
        "conducted_by_name": user.get("full_name") or user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.stay_interviews.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.put("/stay-interviews/{interview_id}")
async def update_stay_interview(interview_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    # Whitelist allowed fields to prevent injection of tenant_id, conducted_by, _id, etc.
    allowed = {"status", "scheduled_date", "trigger_reason", "what_makes_stay",
               "what_might_leave", "energising", "frustrating", "career_path_clear",
               "manager_support_rating", "growth_actions", "agreed_actions",
               "follow_up_date", "completed_at", "notes", "employee_name"}
    update = {k: v for k, v in body.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_db()
    try:
        result = await db.stay_interviews.find_one_and_update(
            {"_id": ObjectId(interview_id)}, {"$set": update}, return_document=True
        )
    except Exception:
        result = await db.stay_interviews.find_one_and_update(
            {"id": interview_id}, {"$set": update}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Stay interview not found")
    return fmt(result)


@router.get("/exit-insights")
async def get_exit_insights(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    interviews = await db.exit_interviews.find({"tenant_id": "solvit"}).sort("exit_date", -1).to_list(100)
    return [fmt(i) for i in interviews]


@router.get("/risk-summary")
async def get_risk_summary(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    pipeline = [
        {"$match": {"tenant_id": "solvit", "lifecycle_state": {"$in": ["Active", "PIP", "Realignment"]}}},
        {"$group": {"_id": "$flight_risk_level", "count": {"$sum": 1}}}
    ]
    results = await db.employees.aggregate(pipeline).to_list(10)
    risk_summary = {"Low": 0, "Elevated": 0, "High": 0, "Critical": 0, "Unknown": 0}
    for r in results:
        level = r["_id"] or "Unknown"
        risk_summary[level] = r["count"]
    return risk_summary
