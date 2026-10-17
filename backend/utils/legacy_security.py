"""Conservative authorization adapters for legacy routes; no read-time repairs."""
from copy import deepcopy
from datetime import datetime, timezone
from fastapi import HTTPException
from utils.access_matrix import get_module_access
from utils.employee_integrity import tenant_of, tenant_query, find_employee, employee_key
from utils.employee_access import find_linked_record

HR = {"hr_admin", "hr_manager"}


def module_access(user, module, write=False):
    entry = get_module_access(module, user.get("role"))
    if not entry or (write and entry.get("level") not in {"Full", "Manage"}):
        raise HTTPException(403, "No permission for this module operation")
    return entry


async def audit(db, user, event, reference):
    # Required evidence, no confidential payload copied into previews/audit feeds.
    await db.audit_logs.insert_one({"tenant_id": tenant_of(user), "actor_id": user["id"],
        "event": event, "entity_id": str(reference), "timestamp": datetime.now(timezone.utc).isoformat()})


def projection(row, fields):
    out = {key: deepcopy(row[key]) for key in fields if key in row}
    out["id"] = str(row.get("_id") or row.get("id"))
    out["_id"] = out["id"]
    return out


async def recruitment_scope(db, user, write=False):
    entry = module_access(user, "M03", write)
    query = tenant_query(tenant_of(user))
    if user.get("role") in HR:
        return query
    if user.get("role") == "executive" and not write:
        return query
    if user.get("role") != "line_manager" or write:
        raise HTTPException(403, "Recruitment changes require HR")
    employee = await find_employee(db, user.get("employee_id"), tenant_of(user))
    if not employee or not employee.get("department"):
        raise HTTPException(403, "Manager department needs review")
    return {"$and": [query, {"department": employee["department"]}]}


async def candidate_record(db, user, reference, write=False):
    scope = await recruitment_scope(db, user, write)
    if user.get("role") == "executive":
        raise HTTPException(403, "Only aggregate recruitment information is available")
    row = await find_linked_record(db.candidates, reference, user)
    # Reuse the actual database scope, rather than a supplied department.
    allowed = await db.candidates.find_one({"$and": [scope, {"_id": row["_id"]}]})
    if not allowed:
        raise HTTPException(403, "No access to this candidate")
    return row


CANDIDATE_FIELDS = {"full_name", "email", "phone_number", "position_applied", "department", "role_level",
    "source", "candidate_type", "current_stage", "stage_scores", "stage_notes", "status", "created_at", "updated_at", "employee_id"}


def candidate_view(row, user):
    fields = CANDIDATE_FIELDS if user.get("role") in HR else CANDIDATE_FIELDS - {"email", "phone_number", "stage_notes", "stage_scores"}
    return projection(row, fields)


def policy_visible(row, user):
    if user.get("role") in HR:
        return True
    if row.get("status") != "Active":
        return False
    audience = row.get("applies_to")
    if not isinstance(audience, list) or not audience:
        return False
    allowed = {str(x).strip().lower() for x in audience if isinstance(x, str)}
    if "all" in allowed or user.get("role", "").lower() in allowed:
        return True
    return user.get("role") != "solver" and bool(user.get("employee_id")) and bool(allowed & {"fte", "employees", "employee"})


async def policy_record(db, user, reference):
    module_access(user, "M13")
    row = await find_linked_record(db.policies, reference, user)
    if not policy_visible(row, user):
        raise HTTPException(403, "Policy is not available to this audience")
    return row


def serialize_write(function):
    """Use only on legacy handlers that do not already acquire this lock."""
    from functools import wraps
    from utils.employee_integrity import integrity_write
    @wraps(function)
    async def wrapped(*args, **kwargs):
        from database import get_db
        async with integrity_write(get_db()):
            return await function(*args, **kwargs)
    return wrapped
