"""Server-side object authorization for employee-linked resources."""
from bson import ObjectId
from fastapi import HTTPException

from utils.access_matrix import get_module_access, RUNTIME_OVERRIDES, CUSTOM_ROLE_DEFINITIONS
from utils.employee_integrity import (
    employee_key, find_employee, is_direct_report, tenant_of, tenant_query, user_employee_aliases,
)


def personal_grant(user, module, write=False):
    role = user.get("role")
    entry = get_module_access(module, role)
    # All staff retain their base Employee rights for their OWN record only.
    # Explicit runtime revocation must not be bypassed by that base layer.
    if (entry is None or entry.get("scope") not in (None, "own_record", "own_cases", "own_team", "own_reports")) and (module, role) not in RUNTIME_OVERRIDES and user.get("employee_id"):
        base = get_module_access(module, "employee")
        if base and base.get("scope") in ("own_record", "own_cases"):
            entry = base
    rank = {"Read": 1, "Manage": 2, "Full": 3}
    if not entry or rank.get(entry.get("level"), 0) < (2 if write else 1):
        raise HTTPException(403, "No permission for this employee operation.")
    # Personal-record boundaries are not widened by a generic matrix override.
    base_role = CUSTOM_ROLE_DEFINITIONS.get(role, {}).get("inherits_from", role)
    entry = dict(entry)
    if base_role in ("employee", "solver"):
        entry["scope"] = "own_record"
    elif base_role == "line_manager" and entry.get("scope") is None:
        entry["scope"] = "own_team"
    if entry.get("scope") not in (None, "own_record", "own_cases", "own_team", "own_reports"):
        raise HTTPException(403, "This permission does not allow individual employee records.")
    return entry


async def authorize_employee(db, user, reference, module, write=False, approve=False):
    entry = personal_grant(user, module, write or approve)
    employee = await find_employee(db, reference, tenant_of(user))
    if not employee:
        raise HTTPException(404, "Employee not found")
    own = employee_key(employee) == user.get("employee_id")
    scope = entry.get("scope")
    if scope is None:
        return employee
    if own and not approve:
        return employee
    if (scope in ("own_team", "own_reports") or (scope == "own_cases" and user.get("role") == "line_manager")) and not own and is_direct_report(employee, user):
        return employee
    raise HTTPException(403, "No access to this employee's record.")


def reference_ids(employee):
    return list({employee_key(employee), str(employee["_id"])})


async def scoped_employee_query(db, user, module, employee_id=None, field="employee_id"):
    entry = personal_grant(user, module)
    query = tenant_query(tenant_of(user))
    if employee_id:
        employee = await authorize_employee(db, user, employee_id, module)
        return {"$and": [query, {field: {"$in": reference_ids(employee)}}]}
    if entry.get("scope") is None:
        return query
    refs = list(user_employee_aliases(user))
    if (entry.get("scope") in ("own_team", "own_reports") or (entry.get("scope") == "own_cases" and user.get("role") == "line_manager")) and user.get("employee_id"):
        async for employee in db.employees.find({"$and": [tenant_query(tenant_of(user)), {
            "line_manager_id": {"$in": user_employee_aliases(user)}
        }]}):
            # Duplicate IDs must never turn a scoped list into an authorization bypass.
            await find_employee(db, employee_key(employee), tenant_of(user))
            refs.extend(reference_ids(employee))
    return {"$and": [query, {field: {"$in": list(set(refs))}}]}


async def find_linked_record(collection, reference, user):
    clauses = [{"id": reference}]
    if ObjectId.is_valid(reference):
        clauses.append({"_id": ObjectId(reference)})
    rows = await collection.find({"$and": [tenant_query(tenant_of(user)), {"$or": clauses}]}).to_list(2)
    if len(rows) != 1:
        raise HTTPException(404 if not rows else 409, "Record not found or ambiguous")
    return rows[0]


async def saved_manager(db, user, employee, supplied=None):
    manager = await find_employee(db, employee.get("line_manager_id"), tenant_of(user))
    if not manager:
        raise HTTPException(409, "Employee manager needs an integrity review.")
    if supplied:
        chosen = await find_employee(db, supplied, tenant_of(user))
        if not chosen or employee_key(chosen) != employee_key(manager):
            raise HTTPException(403, "The supplied manager does not match the saved reporting relationship.")
    return employee_key(manager)


def reject_identity_changes(body, record, fields=("employee_id", "tenant_id", "id", "_id", "line_manager_id")):
    for field in fields:
        if field in body and body[field] != record.get(field):
            raise HTTPException(403, "Record identity and reporting relationships cannot be reassigned here.")
