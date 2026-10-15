from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user, require_roles, format_doc
import uuid
from copy import deepcopy
from pymongo.errors import DuplicateKeyError
from utils.employee_access import authorize_employee, scoped_employee_query
from utils.access_matrix import get_module_access
from utils.employee_integrity import (
    employee_key, find_employee, resolve_user_employee, normalize_email,
    ensure_unique_employee, validate_manager, integrity_write, insert_employee, email_matches, is_direct_report, user_employee_aliases,
    validate_manager_departure, change_employee_state, tenant_of,
)

router = APIRouter(prefix="/employees", tags=["employees"])

LIFECYCLE_STATES = ["Candidate", "Onboarding", "Probation", "Active", "On_Leave", "PIP", "Realignment", "Exiting", "Exited"]
DEPARTMENTS = ["Operations", "Commercial & Business Development", "Finance", "Technology", "HR & People"]
ROLE_LEVELS = ["L1", "L2", "L3", "L4", "L5"]
EMPLOYMENT_TYPES = ["Full_Time", "Solver", "Consultant"]


class EmployeeCreate(BaseModel):
    full_name: str
    preferred_name: Optional[str] = None
    work_email: str
    personal_email: Optional[str] = None
    phone_number: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    department: str
    role_title: str
    role_level: str
    current_salary_kes: Optional[int] = None
    # Mandatory per UAT Fix — every employee must have a Line Manager for
    # approval routing. The only exception is the Board Chair record itself
    # (which sits at the apex of the reporting tree).
    line_manager_id: Optional[str] = None
    is_board_chair: bool = False
    start_date: str
    employment_type: str = "Full_Time"
    lifecycle_state: Optional[str] = "Onboarding"
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None


class EmployeeUpdate(BaseModel):
    work_email: Optional[str] = None
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    phone_number: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    department: Optional[str] = None
    role_title: Optional[str] = None
    role_level: Optional[str] = None
    current_salary_kes: Optional[int] = None
    line_manager_id: Optional[str] = None
    employment_type: Optional[str] = None
    lifecycle_state: Optional[str] = None
    profile_photo_url: Optional[str] = None
    # Review Meeting Panel routing flags (FRD §2)
    is_md: Optional[bool] = None
    reports_to_md: Optional[bool] = None
    reports_to_finance_ops: Optional[bool] = None


def fmt(doc):
    if not doc:
        return None
    # Preserve the canonical UUID `id` (used as foreign key across the schema:
    # line_manager_id, leave.employee_id, performance reviews, etc.). Only fall
    # back to the Mongo ObjectId string when a legacy record has no UUID.
    if not doc.get("id"):
        doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc


def employee_view(doc, user):
    """Private HR/self views stay distinct from a manager's team metadata."""
    if user.get("role") in ("hr_admin", "hr_manager", "board", "it_admin"):
        selected = deepcopy(doc)
    else:
        fields = {"id", "_id", "full_name", "preferred_name", "work_email", "department", "role_title",
                  "role_level", "job_level", "start_date", "employment_type", "lifecycle_state",
                  "line_manager_id", "line_manager_name", "probation_end_date", "is_md", "is_board_chair",
                  "reports_to_md", "reports_to_finance_ops"}
        if employee_key(doc) == user.get("employee_id"):
            fields |= {"personal_email", "phone_number", "national_id_number", "kra_pin", "nssf_number", "sha_number",
                       "bank_name", "bank_branch", "bank_account_number", "bank_account", "mpesa_number",
                       "payment_method", "current_salary_kes", "salary_kes", "gender", "date_of_birth",
                       "profile_photo_url", "emergency_contact", "next_of_kin"}
        selected = {key: deepcopy(value) for key, value in doc.items() if key in fields}
    for key in ("password_hash", "password_history", "refresh_tokens", "access_token"):
        selected.pop(key, None)
    return fmt(selected)


@router.post("/bulk-transition")
async def bulk_transition(request: Request):
    """Transition multiple employees to a new lifecycle state in one call. HR Admin only."""
    user = await get_current_user(request)
    from utils.access_matrix import enforce_destructive
    enforce_destructive("employee.lifecycle.manual_change", user["role"])
    body = await request.json()
    employee_ids = body.get("employee_ids", [])
    new_state = body.get("lifecycle_state")
    if not employee_ids or not new_state:
        raise HTTPException(status_code=400, detail="employee_ids and lifecycle_state required")
    db = get_db()
    valid_states = ["Onboarding", "Probation", "Active", "On_Leave", "PIP", "Suspended", "Notice_Period", "Exiting", "Exited"]
    if new_state not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state. Must be one of: {valid_states}")
    updated = 0
    async with integrity_write(db):
        records = []
        for emp_id in dict.fromkeys(employee_ids):
            current = await find_employee(db, emp_id)
            if not current:
                raise HTTPException(404, "Employee not found")
            await validate_manager_departure(db, current, new_state)
            records.append(current)
        for current in records:
            res = await db.employees.update_one({"_id": current["_id"]}, {"$set": {
                "lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()
            }})
            updated += res.modified_count
    # Audit
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "employees.bulk_transition",
        "entity": f"employees ({len(employee_ids)})",
        "performed_by": user["id"],
        "metadata": {"new_state": new_state, "count": updated, "employee_ids": employee_ids},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"status": "success", "updated_count": updated, "new_state": new_state}


@router.post("/seed-demo")
async def seed_demo_employees_endpoint(request: Request):
    """Seed additional dummy employees covering all 9 lifecycle states. HR Admin only."""
    user = await get_current_user(request)
    if user["role"] != "hr_admin":
        raise HTTPException(status_code=403, detail="Only HR Admin can seed demo employees")
    db = get_db()
    from automation.seed_data import seed_extended_employees, require_demo_data_access
    require_demo_data_access()
    inserted = await seed_extended_employees(db)
    return {"status": "success", "inserted": inserted, "message": f"{inserted} demo employees added covering all lifecycle states"}


async def _my_employee_id(db, user) -> Optional[str]:
    """Resolve the calling user's own employees.id from their work email.
    Returns None if the user has no matching employee record (system role)."""
    emp = await resolve_user_employee(db, user)
    return employee_key(emp) if emp else None


async def _line_manager_name(db, manager_id, tenant="solvit"):
    """Resolve display data only; keep the canonical relationship ID unchanged."""
    if not manager_id:
        return None
    try:
        manager = await find_employee(db, manager_id, tenant)
    except HTTPException as error:
        if error.status_code != 409:
            raise
        return None  # Display fallback only; authorization still rejects ambiguity.
    return manager.get("full_name") if manager and isinstance(manager.get("full_name"), str) else None


@router.get("/me")
async def get_my_employee(request: Request):
    """Return the current authenticated user's own employee record.

    Used by Leave to auto-populate the read-only Line Manager field, and by
    other employee-self views. Returns 404 if the user has no matching
    employee record (e.g. system users, IT Admin without an employee profile).
    """
    user = await get_current_user(request)
    db = get_db()
    emp = await resolve_user_employee(db, user)
    if not emp:
        raise HTTPException(status_code=404, detail="No employee record for this account")
    formatted = employee_view(emp, user)
    formatted["line_manager_name"] = await _line_manager_name(db, formatted.get("line_manager_id"), tenant_of(user))
    return formatted


@router.get("/directory")
async def employee_directory(request: Request):
    """Public-safe, non-exited staff metadata with shared Board-only visibility."""
    user = await get_current_user(request)
    from utils.staff_directory import require_staff_directory
    from utils.staff_views import read_staff_views
    db = get_db()
    await require_staff_directory(db, user)
    directory, _ = await read_staff_views(db, user)
    return directory


@router.get("/staff-directory")
async def staff_directory(request: Request):
    """Staff-facing contact list; privileged private HR endpoints stay separate."""
    user = await get_current_user(request)
    db = get_db()
    from utils.staff_directory import require_staff_directory, directory_departments, normalized
    from utils.staff_views import read_staff_views
    await require_staff_directory(db, user)
    directory, _ = await read_staff_views(db, user)
    departments = await directory_departments(db, user)
    notes = {normalized(d["name"]): d["contact_for"] for d in departments}
    for entry in directory:
        entry["contact_for"] = notes.get(normalized(entry["department_label"]), "")
    return {"employees": directory, "departments": departments}


@router.get("/organogram")
async def organogram(request: Request):
    """Read-only reporting forest; unresolved/ambiguous edges are not guessed."""
    user = await get_current_user(request)
    from utils.staff_directory import require_staff_directory
    from utils.staff_views import read_staff_views
    db = get_db()
    await require_staff_directory(db, user)
    _, hierarchy = await read_staff_views(db, user)
    return hierarchy


@router.get("")
async def list_employees(request: Request, lifecycle_state: Optional[str] = None, department: Optional[str] = None, search: Optional[str] = None, include_exited: bool = False):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if lifecycle_state:
        query["lifecycle_state"] = lifecycle_state
    elif not include_exited:
        query["lifecycle_state"] = {"$ne": "Exited"}
    if department:
        query["department"] = department
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"work_email": {"$regex": search, "$options": "i"}},
            {"role_title": {"$regex": search, "$options": "i"}}
        ]
    if user["role"] == "employee":
        own = await find_employee(db, user.get("employee_id"))
        if not own:
            return []
        query["_id"] = own["_id"]
    elif user["role"] == "solver":
        return []
    elif user["role"] == "line_manager":
        # Line managers see THEIR OWN record + records of their direct reports.
        # Matches line_manager_id against the manager's employees.id (NOT the
        # users.id, which differ).
        my_emp_id = await _my_employee_id(db, user)
        if not my_emp_id:
            return []
        me = await find_employee(db, my_emp_id)
        lm_scope = [{"_id": me["_id"]}, {"line_manager_id": {"$in": user_employee_aliases(user)}}]
        if "$or" in query:
            # Preserve the existing search $or — combine with scope using $and
            query["$and"] = [{"$or": query.pop("$or")}, {"$or": lm_scope}]
        else:
            query["$or"] = lm_scope
    elif user["role"] == "finance":
        # Finance only sees compensation data
        pass
    grant = get_module_access("M01", user["role"])
    finance_view = grant and grant.get("scope") == "salary_band"
    # Preserve the existing explicitly authorized Board/system-admin directory.
    if not finance_view and user["role"] not in ("board", "it_admin"):
        scope = await scoped_employee_query(db, user, "M01", field="id")
        # Legacy own records without UUID are already constrained by the _id branch.
        if user["role"] != "employee":
            query = {"$and": [query, scope]}
    employees = await db.employees.find(query).sort("full_name", 1).to_list(500)
    # Section §7/§9 Board-only visibility for MD/ED records.
    # Filter out board_only records (MD, ED) for everyone except Board, the
    # MD/ED themselves (own record), and IT Admin (system role).
    if user["role"] not in ("board", "it_admin"):
        employees = [
            e for e in employees
            if not e.get("board_only") or employee_key(e) == user.get("employee_id")
        ]
    if finance_view:
        allowed = {"id", "full_name", "department", "role_title", "role_level", "current_salary_kes", "lifecycle_state", "work_email", "start_date"}
        return [{k: v for k, v in fmt(e).items() if k in allowed} for e in employees]
    return [employee_view(e, user) for e in employees]


@router.get("/{employee_id}/profile")
async def get_employee_profile(employee_id: str, request: Request):
    """Aggregated profile: timeline, IDP, leave history, recognitions, performance, training."""
    user = await get_current_user(request)
    db = get_db()
    emp = await find_employee(db, employee_id, tenant_of(user))
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp_id = str(emp.get("id", str(emp["_id"])))
    if user["role"] not in ("board", "it_admin"):
        await authorize_employee(db, user, employee_id, "M01")

    # Permission gate: employee can only view self; line_manager only direct reports; HR/exec all.
    # Board-only override: MD/ED records hidden from everyone except Board, IT Admin, and the person themselves.
    if emp.get("board_only") and user["role"] not in ("board", "it_admin") and employee_key(emp) != user.get("employee_id"):
        raise HTTPException(status_code=403, detail="MD / ED record — Board access only")
    if user["role"] == "employee" and employee_key(emp) != user.get("employee_id"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if user["role"] == "line_manager":
        # LM can view self + direct reports. Resolve the LM's employees.id and
        # match against the target's line_manager_id (canonical UUID).
        is_self = employee_key(emp) == user.get("employee_id")
        is_report = is_direct_report(emp, user)
        if not (is_self or is_report):
            raise HTTPException(status_code=403, detail="Not allowed")

    emp["line_manager_name"] = await _line_manager_name(db, emp.get("line_manager_id"), tenant_of(user))

    # Parallel-ish gathers
    reviews = await db.performance_reviews.find({"employee_id": emp_id}).sort("created_at", -1).to_list(20)
    leave = await db.leave_requests.find({"employee_id": emp_id}).sort("created_at", -1).to_list(50)
    recogs_received = await db.recognitions.find({"nominee_id": emp_id}).sort("created_at", -1).to_list(50)
    recogs_given = await db.recognitions.find({"nominator_id": user.get("id")}).sort("created_at", -1).to_list(50) if user.get("id") == emp_id else []
    trainings = await db.training_requests.find({"employee_id": emp_id}).sort("created_at", -1).to_list(50)
    idp = await db.idps.find_one({"employee_id": emp_id})
    cases = await db.disciplinary_cases.find({"employee_id": emp_id}).sort("created_at", -1).to_list(20) if user["role"] in ["hr_admin", "hr_manager"] else []
    notifications = await db.notifications.find({"recipient_id": emp_id}).sort("created_at", -1).to_list(20) if user["role"] in ["hr_admin", "hr_manager"] or employee_key(emp) == user.get("employee_id") else []

    # Build timeline
    timeline = []
    if emp.get("start_date"):
        timeline.append({"date": emp["start_date"], "type": "joined", "title": "Joined Solvit", "color": "#22C55E"})
    if emp.get("probation_end_date"):
        timeline.append({"date": emp["probation_end_date"], "type": "probation_end", "title": "Probation End Date", "color": "#3B82F6"})
    for r in reviews:
        timeline.append({"date": r.get("created_at", "")[:10], "type": "performance", "title": f"Review · {r.get('cycle_type','').replace('_',' ')} {r.get('cycle_year','')} · score {r.get('overall_score') or '-'}", "color": "#F97316"})
    for l in leave:
        if l.get("status") == "Approved":
            timeline.append({"date": l.get("start_date", ""), "type": "leave", "title": f"{l.get('leave_type')} leave ({l.get('working_days')} days)", "color": "#8B5CF6"})
    for rc in recogs_received:
        timeline.append({"date": rc.get("created_at", "")[:10], "type": "recognition", "title": f"Recognized: {rc.get('recognition_type')} — {(rc.get('values_demonstrated') or [''])[0]}", "color": "#FCD34D"})
    for t in trainings:
        if t.get("status", "").startswith("Completed"):
            timeline.append({"date": t.get("created_at", "")[:10], "type": "training", "title": f"Training: {t.get('training_name')}", "color": "#06B6D4"})
    timeline.sort(key=lambda x: x["date"] or "", reverse=True)

    return {
        "employee": employee_view(emp, user),
        "timeline": timeline,
        "performance_history": [{"id": str(r.get("_id")), "cycle": f"{r.get('cycle_type','').replace('_',' ')} {r.get('cycle_year','')}", "score": r.get("overall_score"), "rating": r.get("rating"), "placement": r.get("nine_box_placement"), "status": r.get("status")} for r in reviews],
        "leave_history": [{"id": str(l.get("_id")), "type": l.get("leave_type"), "start": l.get("start_date"), "end": l.get("end_date"), "days": l.get("working_days"), "status": l.get("status")} for l in leave],
        "recognitions": [{"id": str(r.get("_id")), "type": r.get("recognition_type"), "from": r.get("nominator_name"), "values": r.get("values_demonstrated"), "behaviour": r.get("specific_behaviour"), "status": r.get("status"), "created_at": r.get("created_at")} for r in recogs_received],
        "trainings": [{"id": str(t.get("_id")), "name": t.get("training_name"), "provider": t.get("provider"), "cost_kes": t.get("cost_kes"), "status": t.get("status")} for t in trainings],
        "idp": ({k: v for k, v in idp.items() if k not in ["_id"]} if idp else None),
        "disciplinary_cases": [{"id": str(c.get("_id")), "case_ref": c.get("case_ref"), "type": c.get("case_type"), "status": c.get("status")} for c in cases],
        "notifications": [{"id": str(n.get("_id")), "title": n.get("title"), "message": n.get("message"), "is_read": n.get("is_read", False), "created_at": n.get("created_at")} for n in notifications],
    }


@router.get("/kanban")
async def get_kanban(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    employees = await db.employees.find({"tenant_id": "solvit"}).sort("full_name", 1).to_list(500)
    kanban = {"Onboarding": [], "Active": [], "Exiting": [], "Exited": []}
    for emp in employees:
        formatted = fmt(emp)
        state = emp.get("lifecycle_state", "Active")
        if state in ["Candidate", "Onboarding", "Probation"]:
            kanban["Onboarding"].append(formatted)
        elif state in ["Active", "PIP", "Realignment", "On_Leave"]:
            kanban["Active"].append(formatted)
        elif state == "Exiting":
            kanban["Exiting"].append(formatted)
        elif state == "Exited":
            kanban["Exited"].append(formatted)
    return kanban


@router.get("/stats")
async def get_stats(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    pipeline = [{"$match": {"tenant_id": "solvit"}}, {"$group": {"_id": "$lifecycle_state", "count": {"$sum": 1}}}]
    results = await db.employees.aggregate(pipeline).to_list(20)
    stats = {r["_id"]: r["count"] for r in results}
    total = sum(stats.values())
    solver_count = await db.solvers.count_documents({"tenant_id": "solvit", "lifecycle_state": "Active"})
    open_tasks = await db.tasks.count_documents({"tenant_id": "solvit", "status": {"$in": ["Pending", "In_Progress"]}})
    return {
        "total_fte": total,
        "active": stats.get("Active", 0),
        "onboarding": stats.get("Onboarding", 0) + stats.get("Probation", 0),
        "exiting": stats.get("Exiting", 0),
        "pip": stats.get("PIP", 0),
        "active_solvers": solver_count,
        "open_tasks": open_tasks,
        "by_state": stats
    }


@router.post("")
async def create_employee(emp: EmployeeCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    if emp.is_board_chair and user["role"] != "hr_admin":
        raise HTTPException(403, "Only HR Admin may create the reporting apex.")

    from dateutil.relativedelta import relativedelta
    from routes.masters_settings import get_setting
    probation_months = int(await get_setting("organisation", "probation_period_months", 3) or 3)
    start_dt = datetime.fromisoformat(emp.start_date) if emp.start_date else datetime.now(timezone.utc)
    probation_end = (start_dt + relativedelta(months=probation_months)).isoformat()[:10]

    emp_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **emp.model_dump(),
        "work_email": emp.work_email.lower(),
        "lifecycle_state": emp.lifecycle_state or "Onboarding",
        "probation_end_date": probation_end,
        "flight_risk_score": None,
        "flight_risk_level": None,
        "project_ownership_eligible": False,
        "last_performance_score": None,
        "last_review_date": None,
        "profile_photo_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        response_doc = fmt(await insert_employee(db, emp_doc))

    # Fire automation event
    from automation.engine import automation_engine
    await automation_engine.fire_event("employee_created", {"employee_id": response_doc["id"], "employee": response_doc})

    # Log audit
    await db.audit_log.insert_one({
        "tenant_id": "solvit",
        "action": "employee_created",
        "entity": "employee",
        "entity_id": response_doc["id"],
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    # Send the welcome email to the new employee (best-effort).
    try:
        from utils.email_triggers import fire_and_forget
        await fire_and_forget(db, "onboarding.welcome", employee_id=response_doc["id"])
    except Exception:
        pass
    return response_doc


@router.get("/{employee_id}")
async def get_employee(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    emp = await find_employee(db, employee_id, tenant_of(user))
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    # Board-only override (MD / ED): hidden from everyone except Board, IT Admin, self.
    if emp.get("board_only") and user["role"] not in ("board", "it_admin") and employee_key(emp) != user.get("employee_id"):
        raise HTTPException(status_code=403, detail="MD / ED record — Board access only")
    if user["role"] == "employee" and employee_key(emp) != user.get("employee_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] == "line_manager":
        is_self = employee_key(emp) == user.get("employee_id")
        is_report = is_direct_report(emp, user)
        if not (is_self or is_report):
            raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] not in ("board", "it_admin"):
        await authorize_employee(db, user, employee_id, "M01")
    return employee_view(emp, user)


@router.put("/{employee_id}")
async def update_employee(employee_id: str, upd: EmployeeUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    async with integrity_write(db):
        current = await find_employee(db, employee_id, tenant_of(user))
        if not current:
            raise HTTPException(404, "Employee not found")
        if user["role"] == "line_manager":
            my_id = await _my_employee_id(db, user)
            if not my_id or not is_direct_report(current, user):
                raise HTTPException(403, "Access denied")
            if upd.model_fields_set & {"line_manager_id", "work_email", "is_md", "reports_to_md", "reports_to_finance_ops"}:
                raise HTTPException(403, "HR must change identity or reporting relationships.")
            protected = {"role_title", "current_salary_kes", "national_id_number", "kra_pin", "nssf_number", "sha_number"}
            proposed = upd.model_dump(exclude_unset=True, exclude_none=True)
            if any(field in proposed and proposed[field] != current.get(field) for field in protected):
                raise HTTPException(403, "HR must change role titles or restricted identity/pay fields.")
        update_data = {k: v for k, v in upd.model_dump(exclude_unset=True).items() if v is not None}
        if "work_email" in upd.model_fields_set:
            if upd.work_email == current.get("work_email"):
                update_data.pop("work_email", None)
            else:
                email = normalize_email(upd.work_email)
                old_email = str(current.get("work_email") or "").strip().lower()
                await ensure_unique_employee(db, email, tenant_of(user), exclude_id=current["_id"])
                aliases = [employee_key(current), str(current["_id"])]
                if email != old_email:
                    owners = await email_matches(db.users, "email", old_email)
                    if any(tenant_of(owner) != tenant_of(user) or owner.get("employee_id") not in aliases for owner in owners):
                        raise HTTPException(409, "Review the legacy account link before changing employee email.")
                    candidates = await email_matches(db.users, "email", email)
                    if any(tenant_of(owner) != tenant_of(user) or owner.get("employee_id") not in aliases for owner in candidates):
                        raise HTTPException(409, "Email belongs to a different login account.")
                # Linked account login email, password and sessions remain unchanged.
                update_data.update(work_email=email, work_email_normalized=email)
        if "line_manager_id" in upd.model_fields_set:
            if upd.line_manager_id != current.get("line_manager_id"):
                update_data["line_manager_id"] = await validate_manager(db, upd.line_manager_id, current, tenant_of(user))
            else:
                update_data.pop("line_manager_id", None)
        if "lifecycle_state" in update_data:
            if update_data["lifecycle_state"] != current.get("lifecycle_state"):
                from utils.access_matrix import enforce_destructive
                enforce_destructive("employee.lifecycle.manual_change", user["role"])
            await validate_manager_departure(db, current, update_data["lifecycle_state"])
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            result = await db.employees.find_one_and_update(
                {"_id": current["_id"]}, {"$set": update_data}, return_document=True
            )
        except DuplicateKeyError:
            raise HTTPException(409, "Employee identity already exists.")
        if not result:
            raise HTTPException(404, "Employee not found")
    await db.audit_log.insert_one({
        "tenant_id": tenant_of(user),
        "action": "employee_updated",
        "entity": "employee",
        "entity_id": employee_id,
        "changes": update_data,
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return employee_view(result, user)


@router.post("/{employee_id}/transition")
async def transition_state(employee_id: str, request: Request):
    user = await get_current_user(request)
    # Section B: manual lifecycle change is HR-Admin-only (destructive action)
    from utils.access_matrix import enforce_destructive
    enforce_destructive("employee.lifecycle.manual_change", user["role"])
    body = await request.json()
    new_state = body.get("lifecycle_state")
    if new_state not in LIFECYCLE_STATES:
        raise HTTPException(status_code=400, detail="Invalid lifecycle state")
    db = get_db()
    emp, old_state = await change_employee_state(db, employee_id, new_state)

    from automation.engine import automation_engine
    await automation_engine.fire_event("lifecycle_state_changed", {
        "employee_id": employee_id,
        "new_state": new_state,
        "old_state": old_state
    })

    if new_state == "Exiting":
        await automation_engine.fire_event("employee_exiting", {"employee_id": employee_id})

    await db.audit_log.insert_one({
        "tenant_id": "solvit",
        "action": "lifecycle_transition",
        "entity": "employee",
        "entity_id": employee_id,
        "from_state": old_state,
        "to_state": new_state,
        "performed_by": user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return fmt(emp)
