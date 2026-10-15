from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from database import get_db
from utils.employee_integrity import user_employee_aliases, employee_key, integrity_write, tenant_of, tenant_query
from utils.employee_access import authorize_employee, scoped_employee_query, reference_ids, find_linked_record, saved_manager, reject_identity_changes
from utils.auth import get_current_user
import uuid
from pathlib import Path
import os

router = APIRouter(prefix="/leave", tags=["leave"])

# Default entitlements + descriptions per Kenyan Employment Act 2007.
# Active leave-type list pulled live from Masters Settings (lookups.leave_types).
LEAVE_TYPE_DETAILS = {
    "Annual":        {"days_entitlement": 21, "description": "Kenyan Employment Act 2007 — 21 working days"},
    "Sick":          {"days_entitlement": 30, "description": "30 days full pay + 15 days half pay"},
    "Maternity":     {"days_entitlement": 90, "description": "3 months paid maternity leave"},
    "Paternity":     {"days_entitlement": 14, "description": "2 weeks paternity leave"},
    "Compassionate": {"days_entitlement": 14, "description": "Handbook v2: 14 working days per calendar year; additional unpaid days require HR exception"},
    "Unpaid":        {"days_entitlement": 0,  "description": "Unpaid leave — entitlement at HR discretion"},
}


async def _active_leave_types() -> dict:
    """Build the active leave-type dict by intersecting the Masters Settings
    `lookups.leave_types` list with the entitlement details."""
    from routes.masters_settings import get_setting
    active = await get_setting("lookups", "leave_types", list(LEAVE_TYPE_DETAILS.keys())) or list(LEAVE_TYPE_DETAILS.keys())
    return {t: LEAVE_TYPE_DETAILS.get(t, {"days_entitlement": 0, "description": ""}) for t in active}


# Backwards-compatible export used by other modules.
LEAVE_TYPES = LEAVE_TYPE_DETAILS


class LeaveRequest(BaseModel):
    employee_id: str
    leave_type: str
    start_date: str
    end_date: str
    handover_contact: Optional[str] = None
    handover_contact_id: Optional[str] = None
    line_manager_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=8000)
    supporting_document_id: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    birth_date: Optional[str] = None
    family_relationship: Optional[str] = None
    emergency_sick: bool = False
    early_maternity_advice: bool = False
    request_token: Optional[str] = Field(None, max_length=128)


def fmt(doc):
    if not doc:
        return None
    # Preserve the UUID `id` field set on insert. Only fall back to the Mongo
    # ObjectId string when no UUID id is stored (legacy records).
    if not doc.get("id"):
        doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


def calculate_working_days(start: str, end: str) -> float:
    from utils.leave_policy import working_units
    return working_units(start, end)


@router.get("/types")
async def get_leave_types(request: Request):
    await get_current_user(request)
    return await _active_leave_types()


@router.get("")
async def list_leave_requests(request: Request, employee_id: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = await scoped_employee_query(db, user, "M18", employee_id)
    if status:
        query = {"$and": [query, {"status": status}]}
    requests = await db.leave_requests.find(query).sort("created_at", -1).to_list(200)
    from utils.leave_workflow import view
    return [await view(db, user, row) for row in requests]


@router.post("")
async def create_leave_request(lr: LeaveRequest, request: Request):
    from utils.leave_workflow import create
    user = await get_current_user(request)
    if lr.leave_type not in await _active_leave_types():
        raise HTTPException(422, "This leave category is not currently available; contact HR")
    async def balance_loader(employee_id):
        return await get_leave_balances(employee_id, request)
    return await create(get_db(), user, lr.model_dump(), balance_loader)


@router.post("/preview")
async def preview_leave(lr: LeaveRequest, request: Request, request_id: Optional[str] = None):
    from utils.leave_policy import preview
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, lr.employee_id, "M18")
    existing = await find_linked_record(db.leave_requests, request_id, user) if request_id else None
    if existing:
        target = await authorize_employee(db, user, existing.get("employee_id"), "M18")
        if target["_id"] != employee["_id"]:
            raise HTTPException(403, "Preview reference belongs to another employee")
    return await preview(db, employee, lr.model_dump(), enforce=False, exclude=existing["_id"] if existing else None)


@router.put("/{request_id}/decision")
async def leave_decision(request_id: str, request: Request):
    from utils.leave_workflow import decide
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("reason", ""), str) or len(body.get("reason", "")) > 4000:
        raise HTTPException(422, "A valid decision and text reason are required")
    async def balance_loader(employee_id):
        return await get_leave_balances(employee_id, request)
    return await decide(get_db(), user, request_id, body, balance_loader)


@router.put("/{request_id}/cancel")
async def cancel_leave(request_id: str, request: Request):
    from utils.leave_workflow import cancel
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("reason", ""), str) or len(body.get("reason", "")) > 4000:
        raise HTTPException(422, "A valid withdrawal reason is required")
    return await cancel(get_db(), user, request_id, body.get("reason", ""))


@router.post("/evidence")
async def upload_leave_evidence(request: Request, file: UploadFile = File(...), document_type: str = Form(...), employee_id: Optional[str] = Form(None)):
    user = await get_current_user(request)
    db = get_db()
    target = employee_id or user.get("employee_id")
    employee = await authorize_employee(db, user, target, "M18", write=True)
    if employee_key(employee) != user.get("employee_id") and user.get("role") not in ("hr_admin", "hr_manager"):
        raise HTTPException(403, "Only HR may provide a document for another employee")
    if document_type not in ("medical_certificate", "maternity_confirmation", "birth_notification"):
        raise HTTPException(422, "Unsupported leave document type")
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(422, "Supporting documents must be non-empty and at most 5 MB")
    extension = ".pdf" if content.startswith(b"%PDF-") else ".png" if content.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg" if content.startswith(b"\xff\xd8\xff") else None
    if not extension:
        raise HTTPException(422, "Upload a PDF, PNG or JPEG supporting document")
    key = str(uuid.uuid4())
    root = Path(os.environ.get("LEAVE_EVIDENCE_ROOT", str(Path(__file__).resolve().parents[1] / "private_uploads" / "leave"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / (key + extension)).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(422, "Invalid document path")
    try:
        with path.open("xb") as destination:
            destination.write(content)
    except OSError:
        raise HTTPException(503, "Private document storage is unavailable")
    try:
        await db.leave_evidence.insert_one({"id": key, "tenant_id": tenant_of(user), "employee_id": employee_key(employee),
                                           "document_type": document_type, "storage_name": path.name, "size_bytes": len(content),
                                           "uploaded_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat()})
    except Exception:
        path.unlink(missing_ok=True)  # Only this newly created, checked file.
        raise HTTPException(503, "The supporting document could not be saved")
    return {"id": key, "document_type": document_type, "size_bytes": len(content)}


@router.put("/{request_id}/supporting-info")
async def supplement_leave(request_id: str, request: Request):
    from utils.leave_workflow import supplement
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "Supporting information must be an object")
    for key, value in body.items():
        if key in {"emergency_sick", "early_maternity_advice"} and not isinstance(value, bool):
            raise HTTPException(422, "Leave flags must be booleans")
        if key not in {"emergency_sick", "early_maternity_advice"} and (not isinstance(value, str) or len(value) > 8000):
            raise HTTPException(422, "Supporting information must contain valid text")
    return await supplement(get_db(), user, request_id, body)


@router.get("/evidence/{document_id}")
async def download_leave_evidence(document_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    row = await find_linked_record(db.leave_evidence, document_id, user)
    employee = await authorize_employee(db, user, row.get("employee_id"), "M18")
    if employee_key(employee) != user.get("employee_id") and user.get("role") not in ("hr_admin", "hr_manager"):
        raise HTTPException(403, "Medical/birth documents are restricted to the employee and HR")
    root = Path(os.environ.get("LEAVE_EVIDENCE_ROOT", str(Path(__file__).resolve().parents[1] / "private_uploads" / "leave"))).resolve()
    path = (root / str(row.get("storage_name", ""))).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Supporting document unavailable")
    return FileResponse(path, filename="leave-evidence" + path.suffix, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/balances/{employee_id}")
async def get_leave_balances(employee_id: str, request: Request):
    from utils.leave_balances import balances
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, employee_id, "M18")
    return await balances(db, employee)


@router.get("/rollover/{employee_id}")
async def get_rollover_balance(employee_id: str, request: Request):
    """Display preserved carry-forward without applying automatic forfeiture."""
    user = await get_current_user(request)
    db = get_db()
    emp = await authorize_employee(db, user, employee_id, "M18")
    # rollover record schema: { tenant_id, employee_id, year, carried_forward, used, status }
    records = await db.leave_rollover.find({"$and": [tenant_query(tenant_of(user)), {
        "employee_id": {"$in": [*reference_ids(emp), emp["_id"]]}, "year": datetime.now(timezone.utc).year}]}).to_list(2)
    if len(records) > 1:
        raise HTTPException(409, "Duplicate carry-forward records require HR reconciliation")
    rec = records[0] if records else None
    from routes.masters_settings import get_setting
    deadline = await get_setting("retention", "rollover_leave_deadline_month_day", "03-31") or "03-31"
    now = datetime.now(timezone.utc)
    md = f"{now.month:02d}-{now.day:02d}"
    deadline_passed = md > deadline
    if not rec:
        return {
            "year": now.year, "carried_forward": 0, "used": 0, "remaining": 0,
            "deadline": deadline, "deadline_passed": deadline_passed,
            "banner": "No carry-forward record is available. HR and manager confirmation is required before using carry-forward leave.",
        }
    used = rec.get("used", 0)
    cf = rec.get("carried_forward", 0)
    from utils.leave_balances import numeric
    if not numeric(used) or not numeric(cf):
        raise HTTPException(409, "Rollover figures require HR reconciliation")
    return {
        "year": rec.get("year"),
        "carried_forward": cf,
        "used": used,
        "remaining": max(0, cf - used),
        "deadline": deadline,
        "deadline_passed": deadline_passed,
        "banner": "Recorded carry-forward is preserved. Any planning deadline or forfeiture requires HR and manager confirmation; no automatic forfeiture is applied.",
    }


@router.get("/calendar")
async def leave_calendar(request: Request, year: Optional[int] = None, month: Optional[int] = None):
    """Fix 4e — leave calendar. HR Admin sees all; line manager sees own direct reports' dept."""
    user = await get_current_user(request)
    db = get_db()
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month
    if not 1 <= month <= 12 or not 1900 <= year <= 2200:
        raise HTTPException(422, "A valid calendar month and year are required")
    start = f"{year:04d}-{month:02d}-01"
    # Compute month end
    if month == 12:
        next_m = f"{year+1:04d}-01-01"
    else:
        next_m = f"{year:04d}-{month+1:02d}-01"

    query = {"status": {"$in": ["Approved", "Pending", "Pending_Manager", "Pending_HR"]},
             "start_date": {"$lt": next_m}, "end_date": {"$gte": start}}
    query = {"$and": [query, await scoped_employee_query(db, user, "M18")]}
    rows = await db.leave_requests.find(query).to_list(500)
    # Enrich with employee
    out = []
    for r in rows:
        try:
            emp = await authorize_employee(db, user, r.get("employee_id"), "M18")
        except HTTPException:
            continue
        out.append({
            "id": str(r.get("id", r.get("_id", ""))),
            "employee_id": r.get("employee_id"),
            "employee_name": emp.get("full_name", ""),
            "department": emp.get("department", ""),
            "leave_type": r.get("leave_type"),
            "start_date": r.get("start_date"),
            "end_date": r.get("end_date"),
            "working_days": r.get("working_days"),
            "status": r.get("status"),
        })
    return {"year": year, "month": month, "events": out}
