from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
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
    query = {"tenant_id": "solvit"}
    if user["role"] == "employee":
        query["employee_id"] = user.get("employee_id", user["id"])
    projects = await db.projects.find(query).sort("created_at", -1).to_list(100)
    return [fmt(p) for p in projects]


@router.post("")
async def create_project(proj: ProjectCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
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
    body = await request.json()
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    from bson import ObjectId
    try:
        result = await db.projects.find_one_and_update(
            {"_id": ObjectId(project_id)}, {"$set": body}, return_document=True
        )
    except Exception:
        result = await db.projects.find_one_and_update(
            {"id": project_id}, {"$set": body}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return fmt(result)
