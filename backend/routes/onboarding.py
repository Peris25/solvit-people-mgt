from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

FTE_ONBOARDING_TASKS = [
    {"task_key": "T01", "title": "Send welcome email with platform credentials", "assigned_role": "system", "day_offset": 0},
    {"task_key": "T02", "title": "IT: Set up workstation and email account", "assigned_role": "line_manager", "day_offset": 0},
    {"task_key": "T03", "title": "IT: Grant system access and tools", "assigned_role": "line_manager", "day_offset": 1},
    {"task_key": "T04", "title": "Share Employee Handbook v2.0", "assigned_role": "hr_admin", "day_offset": 1},
    {"task_key": "T05", "title": "Schedule Week 1 line manager 1:1", "assigned_role": "line_manager", "day_offset": 1},
    {"task_key": "T06", "title": "Complete NSSF registration (if new)", "assigned_role": "hr_admin", "day_offset": 3},
    {"task_key": "T07", "title": "Complete SHA registration", "assigned_role": "hr_admin", "day_offset": 3},
    {"task_key": "T08", "title": "KRA PIN verification and payroll setup", "assigned_role": "hr_admin", "day_offset": 3},
    {"task_key": "T09", "title": "Role KPIs and goals setting (Form 11)", "assigned_role": "line_manager", "day_offset": 5},
    {"task_key": "T10", "title": "Policy acknowledgement: Employee Handbook", "assigned_role": "employee", "day_offset": 5},
    {"task_key": "T11", "title": "Policy acknowledgement: Code of Conduct", "assigned_role": "employee", "day_offset": 5},
    {"task_key": "T12", "title": "Policy acknowledgement: IT Policy", "assigned_role": "employee", "day_offset": 5},
    {"task_key": "T13", "title": "Department tour and team introductions", "assigned_role": "line_manager", "day_offset": 1},
    {"task_key": "T14", "title": "Week 2: Job shadow and practical orientation", "assigned_role": "line_manager", "day_offset": 7},
    {"task_key": "T15", "title": "Week 2: Review KPIs and clarify expectations", "assigned_role": "line_manager", "day_offset": 8},
    {"task_key": "T16", "title": "Week 3: Complete Solvit Values & Culture session", "assigned_role": "hr_admin", "day_offset": 14},
    {"task_key": "T17", "title": "Week 3: Buddy check-in with peer", "assigned_role": "employee", "day_offset": 14},
    {"task_key": "T18", "title": "Week 3: MD Onboarding Meeting (triggers probation)", "assigned_role": "hr_admin", "day_offset": 17},
    {"task_key": "T19", "title": "Submit bank details for payroll", "assigned_role": "employee", "day_offset": 2},
]

SOLVER_INDUCTION_TASKS = [
    {"task_key": "S01", "title": "Complete Contact & Statutory Info Form (Form 01)", "assigned_role": "solver", "day_offset": 0},
    {"task_key": "S02", "title": "Watch Solvit Solver Induction Video", "assigned_role": "solver", "day_offset": 0},
    {"task_key": "S03", "title": "Complete Motor Vehicle Assessment Quiz (Form 02)", "assigned_role": "solver", "day_offset": 1},
    {"task_key": "S04", "title": "Complete Solvers Code Comprehension Quiz (Form 03)", "assigned_role": "solver", "day_offset": 1},
    {"task_key": "S05", "title": "Review and sign Solver Agreement", "assigned_role": "solver", "day_offset": 2},
    {"task_key": "S06", "title": "Solvers Manager: Review and activate Solver", "assigned_role": "line_manager", "day_offset": 3},
]


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    completed_by: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/employee/{employee_id}")
async def get_employee_onboarding(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    tasks = await db.onboarding_tasks.find({"entity_id": employee_id, "entity_type": "employee"}).to_list(50)
    if not tasks:
        # Check if we should create them
        try:
            emp = await db.employees.find_one({"_id": ObjectId(employee_id)})
        except Exception:
            emp = await db.employees.find_one({"id": employee_id})
        if emp and emp.get("lifecycle_state") in ["Onboarding", "Probation"]:
            tasks = await _create_onboarding_tasks(db, employee_id, "employee", emp)
    return [fmt(t) for t in tasks]


@router.get("/solver/{solver_id}")
async def get_solver_onboarding(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    tasks = await db.onboarding_tasks.find({"entity_id": solver_id, "entity_type": "solver"}).to_list(20)
    if not tasks:
        try:
            s = await db.solvers.find_one({"_id": ObjectId(solver_id)})
        except Exception:
            s = await db.solvers.find_one({"id": solver_id})
        if s:
            tasks = await _create_solver_induction(db, solver_id, s)
    return [fmt(t) for t in tasks]


async def _create_onboarding_tasks(db, employee_id: str, entity_type: str, entity: dict):
    from dateutil.relativedelta import relativedelta
    start_date_str = entity.get("start_date", datetime.now(timezone.utc).isoformat()[:10])
    start_date = datetime.fromisoformat(start_date_str)
    tasks = []
    for template in FTE_ONBOARDING_TASKS:
        due_date = (start_date + timezone.utc.fromutc(start_date).replace(tzinfo=timezone.utc) if False else start_date).isoformat()[:10]
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "entity_id": employee_id,
            "entity_type": entity_type,
            "task_key": template["task_key"],
            "title": template["title"],
            "assigned_role": template["assigned_role"],
            "status": "Pending",
            "due_date": due_date,
            "notes": None,
            "completed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        tasks.append(task)
    if tasks:
        await db.onboarding_tasks.insert_many(tasks)
    return await db.onboarding_tasks.find({"entity_id": employee_id, "entity_type": entity_type}).to_list(50)


async def _create_solver_induction(db, solver_id: str, solver: dict):
    tasks = []
    for template in SOLVER_INDUCTION_TASKS:
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "entity_id": solver_id,
            "entity_type": "solver",
            "task_key": template["task_key"],
            "title": template["title"],
            "assigned_role": template["assigned_role"],
            "status": "Pending",
            "due_date": None,
            "notes": None,
            "completed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        tasks.append(task)
    if tasks:
        await db.onboarding_tasks.insert_many(tasks)
    return await db.onboarding_tasks.find({"entity_id": solver_id, "entity_type": "solver"}).to_list(20)


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, upd: TaskUpdate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    update_data = {}
    if upd.status:
        update_data["status"] = upd.status
        if upd.status == "Completed":
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            update_data["completed_by"] = user["id"]
    if upd.notes:
        update_data["notes"] = upd.notes
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.onboarding_tasks.find_one_and_update(
            {"_id": ObjectId(task_id)}, {"$set": update_data}, return_document=True
        )
    except Exception:
        result = await db.onboarding_tasks.find_one_and_update(
            {"id": task_id}, {"$set": update_data}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return fmt(result)


@router.get("/all")
async def get_all_onboarding(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    # Get employees in onboarding/probation
    employees = await db.employees.find(
        {"tenant_id": "solvit", "lifecycle_state": {"$in": ["Onboarding", "Probation"]}}
    ).to_list(100)
    # Get solvers in registering state
    solvers = await db.solvers.find({"tenant_id": "solvit", "lifecycle_state": "Registering"}).to_list(100)
    result = []
    for emp in employees:
        tasks = await db.onboarding_tasks.find({"entity_id": str(emp.get("id", str(emp["_id"]))), "entity_type": "employee"}).to_list(50)
        total = len(tasks)
        completed = sum(1 for t in tasks if t.get("status") == "Completed")
        overdue = sum(1 for t in tasks if t.get("status") == "Pending" and t.get("due_date") and t["due_date"] < datetime.now(timezone.utc).isoformat()[:10])
        result.append({
            "id": str(emp["_id"]),
            "entity_type": "employee",
            "name": emp.get("full_name", ""),
            "role": emp.get("role_title", ""),
            "department": emp.get("department", ""),
            "lifecycle_state": emp.get("lifecycle_state"),
            "start_date": emp.get("start_date"),
            "tasks_total": total,
            "tasks_completed": completed,
            "tasks_overdue": overdue,
            "progress_pct": round((completed / total * 100) if total > 0 else 0)
        })
    return result
