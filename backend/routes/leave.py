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
    "Compassionate": {"days_entitlement": 14, "description": "Compassionate leave — 14 days per event"},
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
    notes: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    # Preserve the UUID `id` field set on insert. Only fall back to the Mongo
    # ObjectId string when no UUID id is stored (legacy records).
    if not doc.get("id"):
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
        # Resolve the LM's own employees.id (not users.id) for accurate scoping.
        me = await db.employees.find_one({"tenant_id": "solvit", "work_email": (user.get("email") or "").lower()})
        my_emp_id = (me.get("id") or str(me.get("_id"))) if me else None
        direct_reports = await db.employees.find({"line_manager_id": my_emp_id}).to_list(200) if my_emp_id else []
        ids = [str(e.get("id", str(e["_id"]))) for e in direct_reports]
        # Include the LM's own leave requests too
        if my_emp_id:
            ids.append(my_emp_id)
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

    # ── Email notifications ──────────────────────────────────────────────────
    # 1) Confirmation to the requesting employee (leave.received)
    # 2) Approval request to the line manager (leave.pending_lm)
    # Both are best-effort: if SMTP isn't configured the leave still saves.
    try:
        from utils.email_service import send_email
        emp = await db.employees.find_one({"id": lr.employee_id}) or {}
        emp_email = emp.get("work_email")
        emp_name = emp.get("full_name", "")
        ctx_base = {
            "employee_name": emp_name,
            "leave_type": lr.leave_type,
            "start_date": lr.start_date,
            "end_date": lr.end_date,
            "days": working_days,
        }
        if emp_email:
            await send_email(db, to=emp_email, template_key="leave.received", context=ctx_base)
        # Resolve line manager email (lr.line_manager_id is canonical employees.id)
        lm_id = lr.line_manager_id or emp.get("line_manager_id")
        if lm_id:
            lm = await db.employees.find_one({"id": lm_id}) or {}
            if lm.get("work_email"):
                await send_email(
                    db,
                    to=lm["work_email"],
                    template_key="leave.pending_lm",
                    context={**ctx_base, "manager_name": lm.get("full_name", "")},
                )
    except Exception as e:
        # Never let email failure block the API response.
        import logging
        logging.getLogger(__name__).warning("Leave-submit email side-effect failed: %s", e)

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

    # Fix 4d — auto-notify employee on approve/reject
    if update.get("status") in ("Approved", "Rejected"):
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "recipient_id": result.get("employee_id"),
            "category": "Leave",
            "title": f"Leave {update['status']}",
            "message": f"{result.get('leave_type','Annual')} leave ({result.get('start_date')} → {result.get('end_date')}) {update['status'].lower()} by {user.get('full_name') or user.get('email')}. {('Reason: ' + update.get('manager_reason','')) if update['status']=='Rejected' else ''}".strip(),
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Email the employee with the decision (best-effort)
        try:
            from utils.email_service import send_email
            emp = await db.employees.find_one({"id": result.get("employee_id")}) or {}
            if emp.get("work_email"):
                tpl_key = "leave.approved" if update["status"] == "Approved" else "leave.rejected"
                ctx = {
                    "employee_name": emp.get("full_name", ""),
                    "leave_type": result.get("leave_type", "Annual"),
                    "start_date": result.get("start_date"),
                    "end_date": result.get("end_date"),
                    "reason": update.get("manager_reason") or "—",
                }
                await send_email(db, to=emp["work_email"], template_key=tpl_key, context=ctx)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Leave-decision email side-effect failed: %s", e)

    if update.get("status") == "Approved":
        from automation.engine import automation_engine
        await automation_engine.fire_event("leave_approved", {"employee_id": result.get("employee_id"), "start_date": result.get("start_date")})

    return fmt(result)


@router.get("/balances/{employee_id}")
async def get_leave_balances(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    # Fetch employee for service-month based accrual (Fix 3a)
    emp = await db.employees.find_one({"id": employee_id}) or await db.employees.find_one({"_id": ObjectId(employee_id) if ObjectId.is_valid(employee_id) else None})

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

    # Compute completed months of service in current leave year (Jan-current month)
    now = datetime.now(timezone.utc)
    completed_months_in_year = max(0, now.month - 1)  # Jan = 0 completed months
    if emp and emp.get("start_date"):
        try:
            sd = datetime.fromisoformat(emp["start_date"])
            if sd.year == now.year:
                completed_months_in_year = max(0, now.month - sd.month - (0 if now.day >= sd.day else 1))
        except Exception:
            pass
    accrued_annual = round(completed_months_in_year * 1.75, 2)

    balances = {}
    types = await _active_leave_types()
    for leave_type, info in types.items():
        entitlement = info["days_entitlement"]
        used_days = used.get(leave_type, 0)
        entry = {
            "entitlement": entitlement,
            "used": used_days,
            "remaining": max(0, entitlement - used_days),
            "description": info["description"]
        }
        if leave_type == "Annual":
            # Fix 3a — show accrued working figure alongside annual entitlement
            entry["accrued_kenyan_act"] = accrued_annual
            entry["completed_months_in_year"] = completed_months_in_year
            entry["remaining"] = round(max(0, accrued_annual - used_days), 2)
            entry["balance_label"] = "Accrued Balance"
        balances[leave_type] = entry

    # Top-level convenience keys
    annual_days_remaining = balances.get("Annual", {}).get("remaining", 0)
    sick_days_remaining = balances.get("Sick", {}).get("remaining", 0)
    return {**balances, "annual_days_remaining": annual_days_remaining, "sick_days_remaining": sick_days_remaining,
            "accrued_annual": accrued_annual}


@router.get("/rollover/{employee_id}")
async def get_rollover_balance(employee_id: str, request: Request):
    """Fix 3b — rollover balance display. Banner if non-zero with 31 March deadline."""
    user = await get_current_user(request)
    db = get_db()
    # rollover record schema: { tenant_id, employee_id, year, carried_forward, used, status }
    rec = await db.leave_rollover.find_one({"tenant_id": "solvit", "employee_id": employee_id, "year": datetime.now(timezone.utc).year})
    from routes.masters_settings import get_setting
    deadline = await get_setting("retention", "rollover_leave_deadline_month_day", "03-31") or "03-31"
    now = datetime.now(timezone.utc)
    md = f"{now.month:02d}-{now.day:02d}"
    deadline_passed = md > deadline
    if not rec:
        return {
            "year": now.year, "carried_forward": 0, "used": 0, "remaining": 0,
            "deadline": deadline, "deadline_passed": deadline_passed,
            "banner": f"No carry-forward leave from {now.year - 1}. Rollover deadline is {deadline.replace('-', '/')}.",
        }
    used = int(rec.get("used", 0))
    cf = int(rec.get("carried_forward", 0))
    return {
        "year": rec.get("year"),
        "carried_forward": cf,
        "used": used,
        "remaining": max(0, cf - used),
        "deadline": deadline,
        "deadline_passed": deadline_passed,
        "banner": f"Unutilised rollover leave must be taken by {deadline.replace('-', '/')}. Days not taken by this date will be forfeited.",
    }


@router.get("/calendar")
async def leave_calendar(request: Request, year: Optional[int] = None, month: Optional[int] = None):
    """Fix 4e — leave calendar. HR Admin sees all; line manager sees own direct reports' dept."""
    user = await get_current_user(request)
    db = get_db()
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month
    start = f"{year:04d}-{month:02d}-01"
    # Compute month end
    if month == 12:
        next_m = f"{year+1:04d}-01-01"
    else:
        next_m = f"{year:04d}-{month+1:02d}-01"

    query = {"tenant_id": "solvit", "status": {"$in": ["Approved", "Pending"]},
             "start_date": {"$lt": next_m}, "end_date": {"$gte": start}}
    rows = await db.leave_requests.find(query).to_list(500)
    # Enrich with employee
    emp_ids = list({r.get("employee_id") for r in rows if r.get("employee_id")})
    emps = {}
    async for e in db.employees.find({"id": {"$in": emp_ids}}, {"id": 1, "full_name": 1, "department": 1}):
        emps[e["id"]] = e

    if user["role"] == "line_manager":
        # Only show employees in the line manager's department
        my_dept = (await db.employees.find_one({"work_email": user.get("email")}) or {}).get("department")
        if my_dept:
            rows = [r for r in rows if (emps.get(r.get("employee_id")) or {}).get("department") == my_dept]

    out = []
    for r in rows:
        emp = emps.get(r.get("employee_id"), {})
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
