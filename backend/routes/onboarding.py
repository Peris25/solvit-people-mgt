from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime, timezone, timedelta, date
from database import get_db
from utils.employee_access import authorize_employee, reference_ids, find_linked_record
from utils.auth import get_current_user
from utils.employee_integrity import tenant_of, tenant_query, integrity_write, employee_key
from utils.solver_access import authorize_solver, solver_aliases, solver_key, solver_access
import uuid

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

FTE_ONBOARDING_TASKS = [
    {"task_key": "T01", "title": "Verify secure account provisioning and welcome pack", "assigned_role": "hr_admin", "day_offset": 0},
    {"task_key": "T02", "title": "IT: Set up workstation and email account", "assigned_role": "it_admin", "day_offset": 0},
    {"task_key": "T03", "title": "IT: Grant system access and tools", "assigned_role": "it_admin", "day_offset": 1},
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
    {"task_key": "C30", "title": "30-day check-in", "assigned_role": "line_manager", "day_offset": 30},
    {"task_key": "C60", "title": "60-day check-in", "assigned_role": "line_manager", "day_offset": 60},
    {"task_key": "C90", "title": "90-day check-in", "assigned_role": "line_manager", "day_offset": 90},
    {"task_key": "ASSETS", "title": "Issue and record company assets", "assigned_role": "it_admin", "day_offset": 0},
    {"task_key": "PAYROLL", "title": "Verify payroll setup", "assigned_role": "finance", "day_offset": 3},
    {"task_key": "DOCS", "title": "Verify required onboarding documents in Document Centre", "assigned_role": "hr_admin", "day_offset": 3},
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
    status: Optional[Literal["Pending", "In_Progress", "Completed"]] = None
    notes: Optional[str] = None
    completed_by: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc.get("id") or doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/employee/{employee_id}")
async def get_employee_onboarding(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, employee_id, "M04")
    from utils.lifecycle_workflows import task_access
    await task_access(db, user, {"entity_id": employee_key(employee)})
    tasks = await db.onboarding_tasks.find({"$and": [tenant_query(tenant_of(user)), {"entity_id": {"$in": reference_ids(employee) + [employee["_id"]]}, "entity_type": "employee"}]}).to_list(50)
    from utils.lifecycle_workflows import project
    return [project(t) for t in tasks]


@router.get("/solver/{solver_id}")
async def get_solver_onboarding(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id)
    query = {"$and": [tenant_query(tenant_of(user)), {"entity_id": {"$in": solver_aliases(record)}, "entity_type": "solver"}]}
    tasks = await db.onboarding_tasks.find(query).to_list(20)
    return [fmt(t) for t in tasks]


async def _create_onboarding_tasks(db, employee_id: str, entity_type: str, entity: dict):
    try:
        start_date = datetime.fromisoformat(entity.get("start_date") or "")
    except (ValueError, TypeError):
        raise HTTPException(409, "HR must confirm an employment start date")
    tasks = []
    for template in FTE_ONBOARDING_TASKS:
        due_date = (start_date + timedelta(days=template["day_offset"])).isoformat()[:10]
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_of(entity),
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
    existing = await db.onboarding_tasks.find({"$and": [tenant_query(tenant_of(entity)), {"entity_id": {"$in": reference_ids(entity) + [entity["_id"]]}, "entity_type": entity_type}]}).to_list(None)
    keys = {row.get("task_key") for row in existing}
    tasks = [task for task in tasks if task["task_key"] not in keys]
    if tasks:
        await db.onboarding_tasks.insert_many(tasks)
    return await db.onboarding_tasks.find({"$and": [tenant_query(tenant_of(entity)), {"entity_id": {"$in": reference_ids(entity) + [entity["_id"]]}, "entity_type": entity_type}]}).to_list(50)


async def _create_solver_induction(db, solver_id: str, solver: dict):
    tasks = []
    for template in SOLVER_INDUCTION_TASKS:
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_of(solver),
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
    from utils.solver_workflows import task_query
    existing = await db.onboarding_tasks.find(task_query(solver)).to_list(None)
    keys = {row.get('task_key') for row in existing}
    tasks = [task for task in tasks if task['task_key'] not in keys]
    if tasks:
        await db.onboarding_tasks.insert_many(tasks)
    return await db.onboarding_tasks.find(task_query(solver)).to_list(None)


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, upd: TaskUpdate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    current = await find_linked_record(db.onboarding_tasks, task_id, user)
    if current.get("entity_type") == "solver":
        record = await authorize_solver(db, user, current.get("entity_id"))
        if current.get('task_key') in {'S01','S02','S03','S04','S05','S06'}:
            raise HTTPException(409, 'Use the evidence-backed Solver verification and activation actions')
        if user.get("role") not in ("hr_admin", "hr_manager"):
            if current.get("assigned_role") != user.get("role"):
                raise HTTPException(403, "This induction task belongs to another role")
        from utils.solver_access import audit_solver
        await audit_solver(db, user, 'solver.induction.task.changed', [record], ['status','notes'])
    elif current.get("entity_type") != "employee":
        if user["role"] not in ("hr_admin", "hr_manager"):
            raise HTTPException(403, "No permission for this induction task")
    else:
        from utils.lifecycle_workflows import task_access
        await task_access(db, user, current, write=True)
    if current.get("entity_type") == "employee":
        from utils.lifecycle_workflows import update_checklist
        async with integrity_write(db):
            return await update_checklist(db, user, db.onboarding_tasks, current, upd.status, upd.notes)
    update_data = {}
    if upd.status:
        update_data["status"] = upd.status
        if upd.status == "Completed":
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            update_data["completed_by"] = user["id"]
    if upd.notes:
        update_data["notes"] = upd.notes
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.onboarding_tasks.find_one_and_update({"$and": [tenant_query(tenant_of(user)), {"_id": current["_id"]}]}, {"$set": update_data}, return_document=True)
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
        {"$and": [tenant_query(tenant_of(user)), {"lifecycle_state": {"$in": ["Onboarding", "Probation"]}}]}
    ).to_list(100)
    # Get solvers in registering state
    solvers = await db.solvers.find({"$and": [tenant_query(tenant_of(user)), {"lifecycle_state": "Registering"}]}).to_list(100)
    result = []
    for emp in employees:
        from utils.lifecycle_workflows import task_access
        try:
            await task_access(db, user, {"entity_id": employee_key(emp)})
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        tasks = await db.onboarding_tasks.find({"$and": [tenant_query(tenant_of(user)), {"entity_id": {"$in": reference_ids(emp)}, "entity_type": "employee"}]}).to_list(50)
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
