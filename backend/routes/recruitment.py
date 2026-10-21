from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid
from utils.employee_integrity import integrity_write, insert_employee, find_employee, normalize_email, email_matches, tenant_of, tenant_query
from utils.legacy_security import recruitment_scope, candidate_record, candidate_view, audit

router = APIRouter(prefix="/recruitment", tags=["recruitment"])

PIPELINE_STAGES = ["Stage 1: Competency Test", "Stage 2: Values Assessment", "Stage 3: Growth Mindset",
                   "Stage 4: Physical Interview", "Offer Made", "Offer Accepted", "Rejected", "Withdrawn"]


STAGE_ALIASES = dict(zip(["Competency_Test", "Values_Assessment", "Growth_Mindset", "Physical_Interview", "Offered", "Offer_Accepted"], PIPELINE_STAGES[:6]))
STAGE_ALIASES["Offer_Made"] = "Offer Made"


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
    query = await recruitment_scope(db, user)
    if stage:
        query["current_stage"] = stage
    if candidate_type:
        query["candidate_type"] = candidate_type
    candidates = await db.candidates.find(query).sort("created_at", -1).to_list(200)
    return [candidate_view(c, user) for c in candidates]


@router.post("")
async def create_candidate(candidate: CandidateCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    await recruitment_scope(db, user, write=True)
    candidate = candidate.model_copy(update={"email": normalize_email(candidate.email)})
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **candidate.model_dump(),
        "current_stage": PIPELINE_STAGES[0],
        "stage_scores": {},
        "stage_notes": {},
        "status": "Active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        if await email_matches(db.candidates, "email", candidate.email, tenant_of(user)):
            raise HTTPException(409, "A candidate with this email already exists; review the existing record")
        await audit(db, user, "recruitment.candidate.created", doc["id"])
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
    scope = await recruitment_scope(db, user)
    # Keep closed and legacy-stage records reachable without rewriting them.
    candidates = await db.candidates.find(scope).sort("created_at", -1).to_list(None)
    pipeline_view = {stage: {"candidates": [], "count": 0} for stage in PIPELINE_STAGES}
    for candidate in candidates:
        saved = candidate.get("current_stage")
        stage = STAGE_ALIASES.get(saved, saved) if isinstance(saved, str) and saved.strip() else "Unclassified"
        bucket = pipeline_view.setdefault(stage, {"candidates": [], "count": 0})
        bucket["count"] += 1
        if user["role"] != "executive":
            bucket["candidates"].append(candidate_view(candidate, user))
    return pipeline_view


@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    c = await candidate_record(db, user, candidate_id)
    return candidate_view(c, user)


@router.put("/{candidate_id}")
async def update_candidate(candidate_id: str, upd: CandidateUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    if upd.stage in STAGE_ALIASES:
        upd = upd.model_copy(update={"stage": STAGE_ALIASES[upd.stage]})
    current = await candidate_record(db, user, candidate_id, write=True)
    if upd.stage and upd.stage not in PIPELINE_STAGES:
        raise HTTPException(422, "Unknown recruitment stage")
    if upd.outcome and upd.outcome not in {"Active", "Rejected", "Withdrawn"}:
        raise HTTPException(422, "Employee conversion must use the authorized conversion workflow")
    if current.get("status") in {"Converted", "Rejected", "Withdrawn"}:
        raise HTTPException(409, "Closed candidate history cannot be changed")
    if upd.stage and upd.stage not in {current.get("current_stage"), "Rejected", "Withdrawn"}:
        previous = STAGE_ALIASES.get(current.get("current_stage"), current.get("current_stage"))
        if previous not in PIPELINE_STAGES or PIPELINE_STAGES.index(upd.stage) != PIPELINE_STAGES.index(previous) + 1:
            raise HTTPException(409, "Recruitment stages must progress in order")
    if upd.stage_score is not None and not 0 <= upd.stage_score <= 100:
        raise HTTPException(422, "Stage score must be between 0 and 100")
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
    async with integrity_write(db):
        latest = await candidate_record(db, user, candidate_id, write=True)
        if latest != current:
            raise HTTPException(409, "Candidate changed; refresh before updating")
        await audit(db, user, "recruitment.candidate.updated", current["_id"])
        result = await db.candidates.find_one_and_update({"_id": current["_id"]}, {"$set": update_data}, return_document=True)
    # Email the candidate based on new stage / outcome (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        cand_email = result.get("email")
        if cand_email:
            stage_map = {
                "Stage 1: Competency Test": "recruitment.invite_competency",
                "Stage 2: Values Assessment": "recruitment.invite_values",
                "Stage 3: Growth Mindset": "recruitment.invite_growth",
                "Stage 4: Physical Interview": "recruitment.invite_interview",
                "Offer Made": "recruitment.offer",
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
    return candidate_view(result, user)


@router.post("/{candidate_id}/convert-to-employee")
async def convert_to_employee(candidate_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    c = await candidate_record(db, user, candidate_id, write=True)
    body = await request.json()
    if not isinstance(body, dict) or set(body) - {"line_manager_id", "start_date", "salary"}:
        raise HTTPException(422, "Invalid conversion fields")
    emp_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "full_name": c["full_name"],
        "work_email": c["email"],
        "line_manager_id": body.get("line_manager_id"),
        "source_candidate_id": str(c["_id"]),
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
    async with integrity_write(db):
        # Re-read inside the lock: repeated/concurrent conversion is idempotent.
        c = await db.candidates.find_one({"_id": c["_id"]})
        if c.get("employee_id"):
            existing = await find_employee(db, c["employee_id"], tenant_of(user))
            if not existing:
                raise HTTPException(409, "Converted candidate link needs an integrity review.")
            existing.pop("_id", None)
            return existing
        if STAGE_ALIASES.get(c.get("current_stage"), c.get("current_stage")) != "Offer Accepted" or c.get("status") != "Active":
            raise HTTPException(409, "Only accepted active offers can be converted")
        prior = await db.employees.find_one({"tenant_id": tenant_of(user), "source_candidate_id": str(c["_id"])})
        if prior:
            # Recover a previous successful insert if the candidate update failed.
            emp_doc = prior
        else:
            emp_doc = await insert_employee(db, emp_doc)
        await audit(db, user, "recruitment.candidate.converted", c["_id"])
        await db.candidates.update_one({"_id": c["_id"]}, {"$set": {"status": "Converted", "employee_id": emp_doc["id"]}})
    emp_doc.pop("_id", None)
    from automation.engine import automation_engine
    await automation_engine.fire_event("employee_created", {"employee_id": emp_doc["id"], "employee": emp_doc})
    return emp_doc
