from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user, require_roles, format_doc
import uuid

router = APIRouter(prefix="/employees", tags=["employees"])

LIFECYCLE_STATES = ["Candidate", "Onboarding", "Probation", "Active", "On_Leave", "PIP", "Realignment", "Exiting", "Exited"]
DEPARTMENTS = ["Operations", "Commercial", "Finance", "Technology", "HR_People", "Valuation"]
ROLE_LEVELS = ["L1", "L2", "L3", "L4", "L5", "B1a", "B1b"]


class EmployeeCreate(BaseModel):
    full_name: str
    preferred_name: Optional[str] = None
    work_email: str
    personal_email: Optional[str] = None
    phone_number: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    department: str
    role_title: str
    role_level: str
    current_salary_kes: Optional[int] = None
    line_manager_id: Optional[str] = None
    start_date: str
    employment_type: str = "Full_Time"
    lifecycle_state: Optional[str] = "Onboarding"
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    phone_number: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    department: Optional[str] = None
    role_title: Optional[str] = None
    role_level: Optional[str] = None
    current_salary_kes: Optional[int] = None
    line_manager_id: Optional[str] = None
    employment_type: Optional[str] = None
    lifecycle_state: Optional[str] = None
    profile_photo_url: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_employees(request: Request, lifecycle_state: Optional[str] = None, department: Optional[str] = None, search: Optional[str] = None, include_exited: bool = False):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if lifecycle_state:
        query["lifecycle_state"] = lifecycle_state
    elif not include_exited:
        query["lifecycle_state"] = {"$ne": "Exited"}
    if department:
        query["department"] = department
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"work_email": {"$regex": search, "$options": "i"}},
            {"role_title": {"$regex": search, "$options": "i"}}
        ]
    if user["role"] == "employee":
        query["work_email"] = user["email"]
    elif user["role"] == "solver":
        return []
    elif user["role"] == "line_manager":
        query["line_manager_id"] = user.get("employee_id", user["id"])
    elif user["role"] == "finance":
        # Finance only sees compensation data
        pass
    employees = await db.employees.find(query).sort("full_name", 1).to_list(500)
    return [fmt(e) for e in employees]


@router.get("/kanban")
async def get_kanban(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    employees = await db.employees.find({"tenant_id": "solvit"}).sort("full_name", 1).to_list(500)
    kanban = {"Onboarding": [], "Active": [], "Exiting": [], "Exited": []}
    for emp in employees:
        formatted = fmt(emp)
        state = emp.get("lifecycle_state", "Active")
        if state in ["Candidate", "Onboarding", "Probation"]:
            kanban["Onboarding"].append(formatted)
        elif state in ["Active", "PIP", "Realignment", "On_Leave"]:
            kanban["Active"].append(formatted)
        elif state == "Exiting":
            kanban["Exiting"].append(formatted)
        elif state == "Exited":
            kanban["Exited"].append(formatted)
    return kanban


@router.get("/stats")
async def get_stats(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    pipeline = [{"$match": {"tenant_id": "solvit"}}, {"$group": {"_id": "$lifecycle_state", "count": {"$sum": 1}}}]
    results = await db.employees.aggregate(pipeline).to_list(20)
    stats = {r["_id"]: r["count"] for r in results}
    total = sum(stats.values())
    solver_count = await db.solvers.count_documents({"tenant_id": "solvit", "lifecycle_state": "Active"})
    open_tasks = await db.tasks.count_documents({"tenant_id": "solvit", "status": {"$in": ["Pending", "In_Progress"]}})
    return {
        "total_fte": total,
        "active": stats.get("Active", 0),
        "onboarding": stats.get("Onboarding", 0) + stats.get("Probation", 0),
        "exiting": stats.get("Exiting", 0),
        "pip": stats.get("PIP", 0),
        "active_solvers": solver_count,
        "open_tasks": open_tasks,
        "by_state": stats
    }


@router.post("")
async def create_employee(emp: EmployeeCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    existing = await db.employees.find_one({"work_email": emp.work_email.lower(), "tenant_id": "solvit"})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    from dateutil.relativedelta import relativedelta
    start_dt = datetime.fromisoformat(emp.start_date) if emp.start_date else datetime.now(timezone.utc)
    probation_end = (start_dt + relativedelta(months=3)).isoformat()[:10]

    emp_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **emp.model_dump(),
        "work_email": emp.work_email.lower(),
        "lifecycle_state": emp.lifecycle_state or "Onboarding",
        "probation_end_date": probation_end,
        "flight_risk_score": None,
        "flight_risk_level": None,
        "project_ownership_eligible": False,
        "last_performance_score": None,
        "last_review_date": None,
        "profile_photo_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.employees.insert_one(emp_doc)
    emp_doc["_id"] = str(result.inserted_id)
    emp_doc["id"] = str(result.inserted_id)

    # Fire automation event
    from automation.engine import automation_engine
    await automation_engine.fire_event("employee_created", {"employee_id": emp_doc["id"], "employee": emp_doc})

    # Log audit
    await db.audit_log.insert_one({
        "tenant_id": "solvit",
        "action": "employee_created",
        "entity": "employee",
        "entity_id": emp_doc["id"],
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return emp_doc


@router.get("/{employee_id}")
async def get_employee(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        emp = await db.employees.find_one({"_id": ObjectId(employee_id)})
    except Exception:
        emp = await db.employees.find_one({"id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if user["role"] == "employee" and emp.get("work_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return fmt(emp)


@router.put("/{employee_id}")
async def update_employee(employee_id: str, upd: EmployeeUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    update_data = {k: v for k, v in upd.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.employees.find_one_and_update(
            {"_id": ObjectId(employee_id)},
            {"$set": update_data},
            return_document=True
        )
    except Exception:
        result = await db.employees.find_one_and_update(
            {"id": employee_id},
            {"$set": update_data},
            return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.audit_log.insert_one({
        "tenant_id": "solvit",
        "action": "employee_updated",
        "entity": "employee",
        "entity_id": employee_id,
        "changes": update_data,
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return fmt(result)


@router.post("/{employee_id}/transition")
async def transition_state(employee_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    new_state = body.get("lifecycle_state")
    if new_state not in LIFECYCLE_STATES:
        raise HTTPException(status_code=400, detail="Invalid lifecycle state")
    db = get_db()
    try:
        emp = await db.employees.find_one_and_update(
            {"_id": ObjectId(employee_id)},
            {"$set": {"lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
    except Exception:
        emp = await db.employees.find_one_and_update(
            {"id": employee_id},
            {"$set": {"lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    from automation.engine import automation_engine
    await automation_engine.fire_event("lifecycle_state_changed", {
        "employee_id": employee_id,
        "new_state": new_state,
        "old_state": emp.get("lifecycle_state")
    })

    if new_state == "Exiting":
        await automation_engine.fire_event("employee_exiting", {"employee_id": employee_id})

    await db.audit_log.insert_one({
        "tenant_id": "solvit",
        "action": "lifecycle_transition",
        "entity": "employee",
        "entity_id": employee_id,
        "from_state": emp.get("lifecycle_state"),
        "to_state": new_state,
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return fmt(emp)
