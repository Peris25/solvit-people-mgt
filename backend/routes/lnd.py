from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.employee_integrity import user_employee_aliases, employee_key, integrity_write
from utils.employee_access import authorize_employee, scoped_employee_query, reference_ids, find_linked_record, saved_manager, reject_identity_changes
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/lnd", tags=["lnd"])


class IDPCreate(BaseModel):
    employee_id: str
    career_aspiration: Optional[str] = None
    next_role_target: Optional[str] = None
    long_term_goal: Optional[str] = None
    skills_to_develop: Optional[List[str]] = []
    actions: Optional[List[dict]] = []  # [{action, owner, due_date, status}]
    training_required: Optional[str] = None
    mentor_request: Optional[str] = None
    stretch_assignments: Optional[str] = None
    goals: Optional[List[dict]] = []  # legacy


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
    employee = await authorize_employee(db, user, employee_id, "M08", write=False)
    idp = await db.idps.find_one({"employee_id": {"$in": reference_ids(employee)}, "tenant_id": "solvit"})
    if not idp:
        return {"employee_id": employee_id, "goals": [], "career_aspiration": None}
    return fmt(idp)


@router.post("/idp")
async def create_or_update_idp(idp: IDPCreate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, idp.employee_id, "M08", write=True)
    idp = idp.model_copy(update={"employee_id": employee_key(employee)})
    existing = await db.idps.find_one({"employee_id": {"$in": reference_ids(employee)}, "tenant_id": "solvit"})
    if existing:
        result = await db.idps.find_one_and_update(
            {"_id": existing["_id"], "tenant_id": "solvit"},
            {"$set": {**idp.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
        return fmt(result)
    doc = {"id": str(uuid.uuid4()), "tenant_id": "solvit", **idp.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    result = await db.idps.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.post("/training/bulk-assign")
async def bulk_assign_training(request: Request):
    """Assign the same training to multiple employees at once. HR Admin / Manager only."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    employee_ids = body.get("employee_ids", [])
    training_name = body.get("training_name")
    provider = body.get("provider", "Internal")
    delivery_method = body.get("delivery_method", "Internal")
    cost_kes = float(body.get("cost_kes", 0))
    duration_days = int(body.get("duration_days", 1))
    business_justification = body.get("business_justification") or "Bulk-assigned training (mandatory)"
    if not employee_ids or not training_name:
        raise HTTPException(status_code=400, detail="employee_ids and training_name required")
    db = get_db()
    # Validate the WHOLE batch before any write or notification.
    selected = [await authorize_employee(db, user, ref, "M08", write=True) for ref in dict.fromkeys(employee_ids)]
    employee_ids = [employee_key(employee) for employee in selected]
    docs = []
    for emp_id in employee_ids:
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "employee_id": emp_id,
            "line_manager_id": await saved_manager(db, user, next(e for e in selected if employee_key(e) == emp_id)),
            "training_name": training_name,
            "provider": provider,
            "delivery_method": delivery_method,
            "cost_kes": cost_kes,
            "duration_days": duration_days,
            "business_justification": business_justification,
            "status": "Pending_Manager_Approval",
            "assigned_by": user["id"],
            "is_bulk_assignment": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    if docs:
        async with integrity_write(db):
            for doc in docs:
                employee = await authorize_employee(db, user, doc["employee_id"], "M08", write=True)
                doc["line_manager_id"] = await saved_manager(db, user, employee)
            await db.training_requests.insert_many(docs)
    # Email each assigned employee — best-effort, paced through send_email throttle.
    try:
        from utils.email_triggers import fire_and_forget
        for emp_id in employee_ids:
            await fire_and_forget(db, "lnd.training_assigned",
                                  employee_id=emp_id, extra={
                                      "training_name": training_name,
                                      "provider": provider,
                                      "delivery_method": delivery_method,
                                  })
    except Exception:
        pass
    return {"status": "success", "created": len(docs), "training_name": training_name}


@router.get("/training")
async def list_training_requests(request: Request, employee_id: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = await scoped_employee_query(db, user, "M08", employee_id)
    if status:
        query = {"$and": [query, {"status": status}]}
    requests = await db.training_requests.find(query).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in requests]


@router.post("/training")
async def create_training_request(tr: TrainingRequest, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, tr.employee_id, "M08", write=True)
    tr = tr.model_copy(update={"employee_id": employee_key(employee)})
    manager_id = await saved_manager(db, user, employee)
    status = "Pending_Manager_Approval"
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **tr.model_dump(),
        "line_manager_id": manager_id,
        "status": status,
        "submitted_by": user["id"],
        "employee_signature": None,
        "manager_decision": None,
        "manager_reason": None,
        "hr_decision": None,
        "requires_hr_approval": (tr.cost_kes or 0) > 5000 or (tr.duration_days or 1) > 2,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        employee = await authorize_employee(db, user, tr.employee_id, "M08", write=True)
        doc["line_manager_id"] = await saved_manager(db, user, employee)
        result = await db.training_requests.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the employee — training assignment confirmation
    try:
        from utils.email_triggers import fire_and_forget
        await fire_and_forget(db, "lnd.training_assigned",
                              employee_id=tr.employee_id, extra={
                                  "training_name": tr.training_name,
                                  "provider": tr.provider,
                                  "delivery_method": tr.delivery_method,
                                  "start_date": tr.proposed_start_date,
                                  "end_date": tr.proposed_end_date,
                                  "cost_kes": tr.cost_kes,
                              })
    except Exception:
        pass
    return doc


@router.put("/training/{request_id}/decision")
async def training_decision(request_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    if body.get("decision") not in ("Approve", "Reject"):
        raise HTTPException(422, "Invalid training decision")
    async with integrity_write(db):
        current = await find_linked_record(db.training_requests, request_id, user)
        await authorize_employee(db, user, current.get("employee_id"), "M08", approve=True)
        reject_identity_changes(body, current)
        update = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if user["role"] in ("hr_admin", "hr_manager"):
            update["hr_decision"] = body["decision"]
            update["status"] = "Approved" if body["decision"] == "Approve" else "Rejected"
        else:
            update["manager_decision"] = body["decision"]
            update["manager_reason"] = body.get("reason")
            requires_hr = bool(current.get("requires_hr_approval")) or (current.get("cost_kes") or 0) > 5000 or (current.get("duration_days") or 1) > 2
            update["status"] = ("Pending_HR_Approval" if requires_hr else "Approved") if body["decision"] == "Approve" else "Rejected"
        result = await db.training_requests.find_one_and_update(
            {"_id": current["_id"]}, {"$set": update}, return_document=True
        )
    return fmt(result)


@router.get("/skills-matrix/{employee_id}")
async def get_skills_matrix(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, employee_id, "M08", write=False)
    matrix = await db.skills_matrix.find_one({"employee_id": {"$in": reference_ids(employee)}, "tenant_id": "solvit"})
    if not matrix:
        return {"employee_id": employee_id, "skills": []}
    return fmt(matrix)


@router.post("/skills-matrix/{employee_id}")
async def update_skills_matrix(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, employee_id, "M08", write=True)
    body = await request.json()
    current = await db.skills_matrix.find_one({"employee_id": {"$in": reference_ids(employee)}, "tenant_id": "solvit"})
    query = {"_id": current["_id"]} if current else {"employee_id": employee_key(employee), "tenant_id": "solvit"}
    result = await db.skills_matrix.find_one_and_update(query,
        {"$set": {"skills": body.get("skills", []), "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True, return_document=True)
    return fmt(result) if result else {"employee_id": employee_id}
