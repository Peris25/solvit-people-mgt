from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.employee_access import authorize_employee, scoped_employee_query, find_linked_record, reject_identity_changes
from utils.auth import get_current_user
import uuid
from utils.legacy_security import module_access, audit, projection, HR
from utils.employee_integrity import integrity_write, tenant_of, employee_key, tenant_query

router = APIRouter(prefix="/disciplinary", tags=["disciplinary"])

ALLEGATION_CATEGORIES = ["Misconduct", "Gross Misconduct", "Performance Issue", "Attendance Issue", "Policy Violation"]


class CaseCreate(BaseModel):
    employee_id: str
    employee_name: str
    allegation_category: str
    allegation_details: str
    incident_date: str
    case_type: str = "Disciplinary"  # Disciplinary or Grievance


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_cases(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M14", write=request.method != "GET")
    db = get_db()
    query = await scoped_employee_query(db, user, "M14")
    if status:
        query = {"$and": [query, {"status": status}]}
    if user["role"] == "line_manager":
        query = {"$and": [query, {"status": {"$nin": ["Closed", "Resolved", "Completed"]}}]}
    cases = await db.disciplinary_cases.find(query).sort("created_at", -1).to_list(100)
    await audit(db, user, "disciplinary.cases.viewed", "list")
    return [case_view(c, user) for c in cases]


@router.post("")
async def create_case(case: CaseCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M14", write=request.method != "GET")
    db = get_db()
    target = await authorize_employee(db, user, case.employee_id, "M14", write=True)
    case = case.model_copy(update={"employee_id": employee_key(target), "employee_name": target.get("full_name", "")})
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "case_ref": f"DC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{case_id[:4].upper()}",
        "tenant_id": tenant_of(user),
        **case.model_dump(),
        "status": "Investigation",
        "timeline": [{"event": "Case opened", "date": datetime.now(timezone.utc).isoformat(), "by": user["id"]}],
        "documents": [],
        "hearing_scheduled": None,
        "outcome": None,
        "warning_level": None,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        if await db.disciplinary_cases.find_one({"$and": [tenant_query(tenant_of(user)), {"employee_id": case.employee_id, "incident_date": case.incident_date, "allegation_category": case.allegation_category}]}):
            raise HTTPException(409, "This employee incident is already recorded")
        await audit(db, user, "disciplinary.case.created", doc["id"])
        result = await db.disciplinary_cases.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/{case_id}")
async def get_case(case_id: str, request: Request):
    user = await get_current_user(request)
    module_access(user, "M14", write=request.method != "GET")
    db = get_db()
    c = await find_linked_record(db.disciplinary_cases, case_id, user)
    await authorize_employee(db, user, c.get("employee_id"), "M14")
    if user["role"] == "line_manager" and c.get("status") in ("Closed", "Resolved", "Completed"):
        raise HTTPException(403, "No access to historical cases")
    await audit(db, user, "disciplinary.case.viewed", c["_id"])
    return case_view(c, user)


@router.put("/{case_id}")
async def update_case(case_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M14", write=request.method != "GET")
    db = get_db()
    current = await find_linked_record(db.disciplinary_cases, case_id, user)
    await authorize_employee(db, user, current.get("employee_id"), "M14", write=True)
    body = await request.json()
    allowed = {"status", "investigating_officer", "hearing_scheduled", "outcome", "warning_level", "appeal_filed", "appeal_date", "appeal_outcome"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise HTTPException(422, "Only case workflow fields may be updated; history is immutable")
    if current.get("status") in {"Closed", "Resolved", "Completed"}:
        raise HTTPException(409, "Closed cases require a separately approved correction")
    if body.get("status") and body["status"] not in {"Investigation", "Under Investigation", "Hearing Scheduled", "Outcome Issued", "Closed"}:
        raise HTTPException(422, "Unknown case status")
    if body.get("outcome") and current.get("status") not in {"Hearing Scheduled", "Outcome Issued"}:
        raise HTTPException(409, "Record the hearing before issuing an outcome")
    reject_identity_changes(body, current)
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    timeline = list(current.get("timeline") or [])
    timeline.append({"event": "Case workflow updated", "date": body["updated_at"], "by": user["id"]})
    body["timeline"] = timeline
    async with integrity_write(db):
        fresh = await find_linked_record(db.disciplinary_cases, case_id, user)
        if fresh != current: raise HTTPException(409, "Case changed; refresh before updating")
        await audit(db, user, "disciplinary.case.updated", current["_id"])
        result = await db.disciplinary_cases.find_one_and_update({"_id": current["_id"]}, {"$set": body}, return_document=True)
    return fmt(result)


@router.post("/{case_id}/issue-notice")
async def issue_notice(case_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M14", write=request.method != "GET")
    db = get_db()
    case = await find_linked_record(db.disciplinary_cases, case_id, user)
    await authorize_employee(db, user, case.get("employee_id"), "M14", write=True)
    body = await request.json()
    if not isinstance(body, dict) or set(body) - {"notice_type", "content", "response_deadline"}:
        raise HTTPException(422, "Invalid notice fields")
    if case.get("status") in {"Closed", "Resolved", "Completed"}:
        raise HTTPException(409, "Cannot issue a notice for a closed case")
    if body.get("notice_type", "Show Cause") not in {"Show Cause", "Hearing", "Written Warning", "Final Warning", "Dismissal"}:
        raise HTTPException(422, "Unknown notice type")
    if not isinstance(body.get("content"), str) or not 1 <= len(body["content"].strip()) <= 20000:
        raise HTTPException(422, "Notice content is required and must be bounded")
    if body.get("notice_type") in {"Written Warning", "Final Warning", "Dismissal"} and case.get("status") not in {"Hearing Scheduled", "Outcome Issued"}:
        raise HTTPException(409, "Record the hearing before issuing an outcome")
    notice = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "case_id": case_id,
        "notice_type": body.get("notice_type", "Show Cause"),
        "content": body.get("content"),
        "response_deadline": body.get("response_deadline"),
        "issued_by": user["id"],
        "issued_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        fresh = await find_linked_record(db.disciplinary_cases, case_id, user)
        if fresh != case: raise HTTPException(409, "Case changed; refresh before issuing notice")
        await audit(db, user, "disciplinary.notice.issued", case["_id"])
        await db.case_documents.insert_one(notice)
        await db.disciplinary_cases.update_one({"_id": case["_id"]}, {"$set": {"status": "Notice_Issued"}})
    # Email the employee with the right warning template
    try:
        case = await db.disciplinary_cases.find_one({"_id": case["_id"]})
        if case:
            notice_type = (body.get("notice_type") or "").lower()
            mapping = {
                "show cause": "disciplinary.hearing",
                "hearing": "disciplinary.hearing",
                "written warning": "disciplinary.written",
                "final warning": "disciplinary.final",
                "dismissal": "disciplinary.dismissal",
            }
            template_key = mapping.get(notice_type, "disciplinary.hearing")
            from utils.email_triggers import fire_and_forget
            await fire_and_forget(db, template_key, employee_id=case.get("employee_id"), extra={
                "case_ref": case.get("case_ref"),
                "allegation": case.get("allegation_details", ""),
                "notice_content": body.get("content", ""),
                "response_deadline": body.get("response_deadline", "—"),
            })
    except Exception:
        pass
    return {"message": "Notice issued", "notice_id": notice["id"]}


def case_view(row, user):
    if user.get("role") in HR:
        return fmt(row)
    # Brief privacy rule: managers/subjects get progress, never confidential details.
    return projection(row, {"employee_id", "case_ref", "status", "created_at", "updated_at"})
