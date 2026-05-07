from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/leave", tags=["leave"])

# Default entitlements + descriptions per Kenyan Employment Act 2007.
# Active leave-type list pulled live from Masters Settings (lookups.leave_types).
LEAVE_TYPE_DETAILS = {
    "Annual":        {"days_entitlement": 21, "description": "Kenyan Employment Act 2007 — 21 working days"},
    "Sick":          {"days_entitlement": 30, "description": "30 days full pay + 15 days half pay"},
    "Maternity":     {"days_entitlement": 90, "description": "3 months paid maternity leave"},
    "Paternity":     {"days_entitlement": 14, "description": "2 weeks paternity leave"},
    "Compassionate": {"days_entitlement": 5,  "description": "Compassionate leave"},
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
    notes: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


def calculate_working_days(start: str, end: str) -> int:
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        days = 0
        current = start_dt
        while current <= end_dt:
            if current.weekday() < 5:  # Mon-Fri
                days += 1
            current += timedelta(days=1)
        return max(days, 1)
    except Exception:
        return 1


@router.get("/types")
async def get_leave_types(request: Request):
    return await _active_leave_types()


@router.get("")
async def list_leave_requests(request: Request, employee_id: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if employee_id:
        query["employee_id"] = employee_id
    if status:
        query["status"] = status
    if user["role"] == "employee":
        query["employee_id"] = user.get("employee_id", user["id"])
    elif user["role"] == "line_manager":
        direct_reports = await db.employees.find({"line_manager_id": user.get("employee_id", user["id"])}).to_list(100)
        ids = [str(e.get("id", str(e["_id"]))) for e in direct_reports]
        query["employee_id"] = {"$in": ids}
    requests = await db.leave_requests.find(query).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in requests]


@router.post("")
async def create_leave_request(lr: LeaveRequest, request: Request):
    user = await get_current_user(request)
    db = get_db()
    working_days = calculate_working_days(lr.start_date, lr.end_date)

    # Check for high-activity period flag (Jan, Jul-Dec)
    try:
        start_month = int(lr.start_date.split("-")[1])
        flag_hr = lr.leave_type == "Annual" and working_days > 5 and start_month in [1, 7, 8, 9, 10, 11, 12]
    except Exception:
        flag_hr = False

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **lr.model_dump(),
        "working_days": working_days,
        "status": "Pending_Manager",
        "flag_hr_attention": flag_hr,
        "employee_signature": None,
        "manager_decision": None,
        "manager_reason": None,
        "manager_decided_at": None,
        "hr_confirmed": False,
        "return_confirmed": False,
        "submitted_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.leave_requests.insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    from automation.engine import automation_engine
    await automation_engine.fire_event("leave_request_submitted", {
        "leave_request_id": doc["id"],
        "employee_id": lr.employee_id,
        "days": working_days,
        "start_month": start_month if 'start_month' in locals() else 0,
        "leave_type": lr.leave_type,
        "flag_hr": flag_hr
    })
    return doc


@router.put("/{request_id}/decision")
async def leave_decision(request_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if user["role"] in ["line_manager", "hr_admin", "hr_manager"]:
        update["manager_decision"] = body.get("decision")
        update["manager_reason"] = body.get("reason", "")
        update["manager_decided_at"] = datetime.now(timezone.utc).isoformat()
        if body.get("decision") == "Approve":
            update["status"] = "Approved"
        elif body.get("decision") == "Reject":
            update["status"] = "Rejected"
        else:
            update["status"] = "Discussion_Requested"

    try:
        result = await db.leave_requests.find_one_and_update(
            {"_id": ObjectId(request_id)}, {"$set": update}, return_document=True
        )
    except Exception:
        result = await db.leave_requests.find_one_and_update(
            {"id": request_id}, {"$set": update}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Leave request not found")

    if update.get("status") == "Approved":
        from automation.engine import automation_engine
        await automation_engine.fire_event("leave_approved", {"employee_id": result.get("employee_id"), "start_date": result.get("start_date")})

    return fmt(result)


@router.get("/balances/{employee_id}")
async def get_leave_balances(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    # Calculate used leave per type
    used = {}
    current_year = datetime.now(timezone.utc).year
    requests = await db.leave_requests.find({
        "employee_id": employee_id,
        "tenant_id": "solvit",
        "status": "Approved",
        "start_date": {"$regex": f"^{current_year}"}
    }).to_list(100)
    for r in requests:
        lt = r.get("leave_type", "Annual")
        used[lt] = used.get(lt, 0) + r.get("working_days", 0)

    balances = {}
    types = await _active_leave_types()
    for leave_type, info in types.items():
        entitlement = info["days_entitlement"]
        used_days = used.get(leave_type, 0)
        balances[leave_type] = {
            "entitlement": entitlement,
            "used": used_days,
            "remaining": max(0, entitlement - used_days),
            "description": info["description"]
        }
    return balances
