from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from utils.employee_access import authorize_employee, scoped_employee_query, find_linked_record, reject_identity_changes
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    employee_id: str
    employee_name: str
    project_name: str
    project_objective: str
    success_criteria: str
    milestones: Optional[List[dict]] = []
    support_resources: Optional[str] = None
    reward_on_completion: Optional[str] = None
    expected_completion_date: str
    eligibility_score_cycle: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_projects(request: Request):
    user = await get_current_user(request)
    db = get_db()
    query = await scoped_employee_query(db, user, "M09")
    projects = await db.projects.find(query).sort("created_at", -1).to_list(100)
    return [fmt(p) for p in projects]


@router.post("")
async def create_project(proj: ProjectCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    await authorize_employee(db, user, proj.employee_id, "M09", write=True)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **proj.model_dump(),
        "status": "Assigned",
        "hr_signature": None,
        "manager_signature": None,
        "employee_signature": None,
        "progress_notes": [],
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.projects.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the assigned employee
    try:
        from utils.email_triggers import fire_and_forget
        await fire_and_forget(db, "lnd.project_assigned", employee_id=proj.employee_id, extra={
            "project_name": proj.project_name,
            "project_objective": proj.project_objective,
            "expected_completion_date": proj.expected_completion_date,
            "reward_on_completion": proj.reward_on_completion or "—",
        })
    except Exception:
        pass
    return doc


@router.get("/eligible")
async def get_eligible_employees(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    employees = await db.employees.find({
        "tenant_id": "solvit",
        "project_ownership_eligible": True,
        "lifecycle_state": "Active"
    }).to_list(50)
    return [fmt(e) for e in employees]


@router.put("/{project_id}")
async def update_project(project_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    current = await find_linked_record(db.projects, project_id, user)
    await authorize_employee(db, user, current.get("employee_id"), "M09", write=True)
    body = await request.json()
    reject_identity_changes(body, current)
    allowed = {"project_name", "project_objective", "success_criteria", "milestones", "support_resources", "reward_on_completion", "expected_completion_date", "status", "progress_notes"}
    update = {k: v for k, v in body.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.projects.find_one_and_update({"_id": current["_id"]}, {"$set": update}, return_document=True)
    if not result:
        raise HTTPException(404, "Project not found")
    # On status → Completed, fire the project completion + reward email
    try:
        if body.get("status") == "Completed":
            from utils.email_triggers import fire_and_forget
            await fire_and_forget(db, "lnd.project_completed",
                                  employee_id=result.get("employee_id"),
                                  extra={
                                      "project_name": result.get("project_name"),
                                      "reward_on_completion": result.get("reward_on_completion") or "—",
                                  })
    except Exception:
        pass
    return fmt(result)
