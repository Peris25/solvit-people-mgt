from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/lnd", tags=["lnd"])


class IDPCreate(BaseModel):
    employee_id: str
    career_aspiration: Optional[str] = None
    goals: Optional[List[dict]] = []


class TrainingRequest(BaseModel):
    employee_id: str
    training_name: str
    provider: str
    delivery_method: str
    cost_kes: Optional[float] = 0
    duration_days: Optional[int] = 1
    link_to_idp_goal: Optional[str] = None
    business_justification: str
    proposed_start_date: Optional[str] = None
    proposed_end_date: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/idp/{employee_id}")
async def get_idp(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    idp = await db.idps.find_one({"employee_id": employee_id, "tenant_id": "solvit"})
    if not idp:
        return {"employee_id": employee_id, "goals": [], "career_aspiration": None}
    return fmt(idp)


@router.post("/idp")
async def create_or_update_idp(idp: IDPCreate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    existing = await db.idps.find_one({"employee_id": idp.employee_id, "tenant_id": "solvit"})
    if existing:
        result = await db.idps.find_one_and_update(
            {"employee_id": idp.employee_id, "tenant_id": "solvit"},
            {"$set": {**idp.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
        return fmt(result)
    doc = {"id": str(uuid.uuid4()), "tenant_id": "solvit", **idp.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    result = await db.idps.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/training")
async def list_training_requests(request: Request, employee_id: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if employee_id:
        query["employee_id"] = employee_id
    if status:
        query["status"] = status
    if user["role"] == "employee":
        query["employee_id"] = user.get("employee_id", user["id"])
    requests = await db.training_requests.find(query).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in requests]


@router.post("/training")
async def create_training_request(tr: TrainingRequest, request: Request):
    user = await get_current_user(request)
    db = get_db()
    status = "Pending_Manager_Approval"
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **tr.model_dump(),
        "status": status,
        "submitted_by": user["id"],
        "employee_signature": None,
        "manager_decision": None,
        "manager_reason": None,
        "hr_decision": None,
        "requires_hr_approval": (tr.cost_kes or 0) > 5000 or (tr.duration_days or 1) > 2,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.training_requests.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.put("/training/{request_id}/decision")
async def training_decision(request_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if user["role"] == "line_manager":
        update["manager_decision"] = body.get("decision")
        update["manager_reason"] = body.get("reason")
        if body.get("decision") == "Approve":
            update["status"] = "Approved" if not body.get("requires_hr_approval") else "Pending_HR_Approval"
        else:
            update["status"] = "Rejected"
    elif user["role"] in ["hr_admin", "hr_manager"]:
        update["hr_decision"] = body.get("decision")
        update["status"] = "Approved" if body.get("decision") == "Approve" else "Rejected"
    try:
        result = await db.training_requests.find_one_and_update(
            {"_id": ObjectId(request_id)}, {"$set": update}, return_document=True
        )
    except Exception:
        result = await db.training_requests.find_one_and_update(
            {"id": request_id}, {"$set": update}, return_document=True
        )
    return fmt(result)


@router.get("/skills-matrix/{employee_id}")
async def get_skills_matrix(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    matrix = await db.skills_matrix.find_one({"employee_id": employee_id, "tenant_id": "solvit"})
    if not matrix:
        return {"employee_id": employee_id, "skills": []}
    return fmt(matrix)


@router.post("/skills-matrix/{employee_id}")
async def update_skills_matrix(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    result = await db.skills_matrix.find_one_and_update(
        {"employee_id": employee_id, "tenant_id": "solvit"},
        {"$set": {"skills": body.get("skills", []), "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
        return_document=True
    )
    return fmt(result) if result else {"employee_id": employee_id}
