from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

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
    db = get_db()
    query = {"tenant_id": "solvit"}
    if status:
        query["status"] = status
    if user["role"] == "line_manager":
        # Only see cases for their direct reports
        pass
    cases = await db.disciplinary_cases.find(query).sort("created_at", -1).to_list(100)
    return [fmt(c) for c in cases]


@router.post("")
async def create_case(case: CaseCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "case_ref": f"DC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{case_id[:4].upper()}",
        "tenant_id": "solvit",
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
    result = await db.disciplinary_cases.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/{case_id}")
async def get_case(case_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        c = await db.disciplinary_cases.find_one({"_id": ObjectId(case_id)})
    except Exception:
        c = await db.disciplinary_cases.find_one({"id": case_id})
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")
    return fmt(c)


@router.put("/{case_id}")
async def update_case(case_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    if body.get("status"):
        body.setdefault("timeline", [])
        # Add timeline event
        event = {"event": f"Status changed to {body['status']}", "date": datetime.now(timezone.utc).isoformat(), "by": user["id"]}
        await db.disciplinary_cases.update_one({"id": case_id}, {"$push": {"timeline": event}})

    try:
        result = await db.disciplinary_cases.find_one_and_update(
            {"_id": ObjectId(case_id)}, {"$set": body}, return_document=True
        )
    except Exception:
        result = await db.disciplinary_cases.find_one_and_update(
            {"id": case_id}, {"$set": body}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Case not found")
    return fmt(result)


@router.post("/{case_id}/issue-notice")
async def issue_notice(case_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    notice = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "case_id": case_id,
        "notice_type": body.get("notice_type", "Show Cause"),
        "content": body.get("content"),
        "response_deadline": body.get("response_deadline"),
        "issued_by": user["id"],
        "issued_at": datetime.now(timezone.utc).isoformat()
    }
    await db.case_documents.insert_one(notice)
    await db.disciplinary_cases.update_one({"id": case_id}, {"$set": {"status": "Notice_Issued"}})
    # Email the employee with the right warning template
    try:
        case = await db.disciplinary_cases.find_one({"id": case_id})
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
