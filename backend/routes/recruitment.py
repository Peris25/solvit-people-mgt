from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/recruitment", tags=["recruitment"])

PIPELINE_STAGES = ["Stage 1: Competency Test", "Stage 2: Values Assessment", "Stage 3: Growth Mindset",
                   "Stage 4: Physical Interview", "Offer Made", "Offer Accepted", "Rejected", "Withdrawn"]


class CandidateCreate(BaseModel):
    full_name: str
    email: str
    phone_number: Optional[str] = None
    position_applied: str
    department: str
    role_level: str
    source: Optional[str] = None
    candidate_type: str = "FTE"  # FTE or Solver


class CandidateUpdate(BaseModel):
    stage: Optional[str] = None
    stage_score: Optional[float] = None
    stage_notes: Optional[str] = None
    outcome: Optional[str] = None
    interviewer_id: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_candidates(request: Request, stage: Optional[str] = None, candidate_type: Optional[str] = None):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    query = {"tenant_id": "solvit"}
    if stage:
        query["current_stage"] = stage
    if candidate_type:
        query["candidate_type"] = candidate_type
    candidates = await db.candidates.find(query).sort("created_at", -1).to_list(200)
    return [fmt(c) for c in candidates]


@router.post("")
async def create_candidate(candidate: CandidateCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **candidate.model_dump(),
        "current_stage": PIPELINE_STAGES[0],
        "stage_scores": {},
        "stage_notes": {},
        "status": "Active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.candidates.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the candidate confirming application received (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        cand_email = doc.get("email")
        if cand_email:
            await fire_and_forget(db, "recruitment.application_received",
                                  to_override=cand_email,
                                  extra={
                                      "candidate_name": doc.get("full_name"),
                                      "position": doc.get("position_applied_for") or doc.get("role_title"),
                                  })
    except Exception:
        pass
    return doc


@router.get("/pipeline")
async def get_pipeline(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    pipeline_agg = [
        {"$match": {"tenant_id": "solvit", "status": "Active"}},
        {"$group": {"_id": "$current_stage", "candidates": {"$push": "$$ROOT"}, "count": {"$sum": 1}}}
    ]
    results = await db.candidates.aggregate(pipeline_agg).to_list(20)
    pipeline_view = {}
    for stage in PIPELINE_STAGES:
        pipeline_view[stage] = {"candidates": [], "count": 0}
    for r in results:
        stage = r["_id"]
        pipeline_view[stage] = {
            "candidates": [fmt(c) for c in r["candidates"]],
            "count": r["count"]
        }
    return pipeline_view


@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        c = await db.candidates.find_one({"_id": ObjectId(candidate_id)})
    except Exception:
        c = await db.candidates.find_one({"id": candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return fmt(c)


@router.put("/{candidate_id}")
async def update_candidate(candidate_id: str, upd: CandidateUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    update_data = {}
    if upd.stage:
        update_data["current_stage"] = upd.stage
    if upd.outcome:
        update_data["status"] = upd.outcome
    if upd.stage_notes:
        update_data[f"stage_notes.{upd.stage or 'current'}"] = upd.stage_notes
    if upd.stage_score is not None:
        update_data[f"stage_scores.{upd.stage or 'current'}"] = upd.stage_score
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.candidates.find_one_and_update(
            {"_id": ObjectId(candidate_id)}, {"$set": update_data}, return_document=True
        )
    except Exception:
        result = await db.candidates.find_one_and_update(
            {"id": candidate_id}, {"$set": update_data}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")
    # Email the candidate based on new stage / outcome (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        cand_email = result.get("email")
        if cand_email:
            stage_map = {
                "Competency_Test": "recruitment.invite_competency",
                "Values_Assessment": "recruitment.invite_values",
                "Growth_Mindset": "recruitment.invite_growth",
                "Physical_Interview": "recruitment.invite_interview",
                "Offered": "recruitment.offer",
                "Offer_Made": "recruitment.offer",
            }
            tpl = stage_map.get(update_data.get("current_stage"))
            # Status transitions override stage (e.g. Rejected)
            if (upd.outcome or update_data.get("status")) == "Rejected":
                tpl = "recruitment.regret"
            if tpl:
                await fire_and_forget(db, tpl, to_override=cand_email, extra={
                    "candidate_name": result.get("full_name"),
                    "position": result.get("position_applied_for") or result.get("role_title"),
                    "stage": update_data.get("current_stage"),
                })
    except Exception:
        pass
    return fmt(result)


@router.post("/{candidate_id}/convert-to-employee")
async def convert_to_employee(candidate_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    try:
        c = await db.candidates.find_one({"_id": ObjectId(candidate_id)})
    except Exception:
        c = await db.candidates.find_one({"id": candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    body = await request.json()
    emp_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "full_name": c["full_name"],
        "work_email": c["email"],
        "phone_number": c.get("phone_number"),
        "department": c["department"],
        "role_title": c["position_applied"],
        "role_level": c.get("role_level", "L1"),
        "start_date": body.get("start_date", datetime.now(timezone.utc).isoformat()[:10]),
        "current_salary_kes": body.get("salary", None),
        "lifecycle_state": "Onboarding",
        "employment_type": "Full_Time",
        "project_ownership_eligible": False,
        "flight_risk_score": None,
        "flight_risk_level": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.employees.insert_one(emp_doc)
    emp_doc["_id"] = str(result.inserted_id)
    await db.candidates.update_one({"_id": c["_id"]}, {"$set": {"status": "Converted", "employee_id": emp_doc["id"]}})
    from automation.engine import automation_engine
    await automation_engine.fire_event("employee_created", {"employee_id": emp_doc["id"], "employee": emp_doc})
    return emp_doc
