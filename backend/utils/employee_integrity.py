"""Shared identity validation. No indexes, backfills, or account creation on reads."""
import re
import uuid
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from bson import ObjectId
from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

WORKER_INSTANCE = str(uuid.uuid4())

INELIGIBLE_MANAGER_STATES = {"Exited", "Exiting", "Terminated", "Inactive"}

def tenant_of(record):
    return record.get("tenant_id") or "solvit"


def employee_key(record):
    return str(record.get("id") or record["_id"])


def user_employee_aliases(user):
    return user.get("employee_reference_ids") or ([user["employee_id"]] if user.get("employee_id") else ["__unlinked_employee__"])


def is_direct_report(employee, user):
    return bool(user.get("employee_id")) and employee.get("line_manager_id") in user_employee_aliases(user)


def normalize_email(value):
    value = str(value or "").strip().lower()
    try:
        validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        raise HTTPException(422, "A valid email address is required.")
    return value


def tenant_query(tenant):
    # Historical records without a tenant belong to the original Solvit tenant.
    if tenant == "solvit":
        return {"$or": [{"tenant_id": tenant}, {"tenant_id": {"$exists": False}}]}
    return {"tenant_id": tenant}


def email_query(field, email):
    # The expression also finds legacy mixed-case/whitespace records without a
    # backfill. $convert handles historical null or malformed values safely.
    return {"$or": [
        {f"{field}_normalized": email},
        {"$expr": {"$eq": [{"$toLower": {"$trim": {"input": {
            "$convert": {"input": f"${field}", "to": "string", "onError": "", "onNull": ""}
        }}}}, email]}},
    ]}


async def email_matches(collection, field, email, tenant=None):
    query = email_query(field, email)
    if tenant:
        query = {"$and": [tenant_query(tenant), query]}
    return await collection.find(query).to_list(2)


async def find_employee(db, reference, tenant="solvit"):
    if isinstance(reference, ObjectId):
        reference = str(reference)
    if not isinstance(reference, str) or not reference.strip():
        return None
    clauses = [{"id": reference}, {"_id": reference}]
    if ObjectId.is_valid(reference):
        clauses.extend([{"_id": ObjectId(reference)}, {"id": ObjectId(reference)}])
    rows = await db.employees.find({"$and": [tenant_query(tenant), {"$or": clauses}]}).to_list(2)
    if len(rows) > 1:
        raise HTTPException(409, "Employee reference is ambiguous. Request an integrity review.")
    return rows[0] if rows else None


async def resolve_user_employee(db, user):
    """Prefer the explicit link. Only recognize the known legacy self-ID bug."""
    if user.get("account_type") in ("system", "solver", "board"):
        return None
    tenant = tenant_of(user)
    link = user.get("employee_id")
    employee = await find_employee(db, link, tenant) if link else None
    if not employee:
        self_ids = {str(user.get("id", "")), str(user.get("_id", ""))}
        if link and link not in self_ids:
            raise HTTPException(409, "Account employee link needs an integrity review.")
        email = str(user.get("email") or "").strip().lower()
        rows = await email_matches(db.employees, "work_email", email, tenant) if email else []
        if len(rows) > 1:
            raise HTTPException(409, "Account employee match is ambiguous. Request an integrity review.")
        employee = rows[0] if rows else None
    if employee:
        # A unique legacy storage alias must not authorize an ambiguous canonical
        # identity shared with another record. Keep reads fail-closed before
        # exposing employee_key as the account's application identity.
        canonical = await find_employee(db, employee_key(employee), tenant)
        if not canonical or canonical["_id"] != employee["_id"]:
            raise HTTPException(409, "Account employee identity needs an integrity review.")
        storage = await find_employee(db, str(employee["_id"]), tenant)
        if not storage or storage["_id"] != employee["_id"]:
            raise HTTPException(409, "Account employee aliases need an integrity review.")
        # Do not authorize two accounts for one employee, even before migration.
        aliases = [employee_key(employee), str(employee["_id"])]
        owners = await db.users.find({"$and": [tenant_query(tenant), {
            "$or": [{"employee_id": {"$in": aliases}}, email_query("email", str(employee.get("work_email") or "").strip().lower())]
        }]}).to_list(3)
        own_id = str(user.get("_id") or user.get("id"))
        if any(str(owner["_id"]) != own_id for owner in owners):
            raise HTTPException(409, "Employee has conflicting accounts. Request an integrity review.")
    return employee


@asynccontextmanager
async def integrity_write(db):
    """Serialize API identity/reporting writes across workers using Mongo's _id.

    No TTL: a crashed writer leaves a fail-closed lock requiring operator review.
    Expiring a lock during a slow write could allow duplicate/cyclic assignments.
    Only lock documents are removed; employee/account records are never deleted.
    """
    token = str(uuid.uuid4())
    try:
        await db.integrity_locks.insert_one({"_id": "employee-account-writes", "owner": token,
                                            "created_at": datetime.now(timezone.utc).isoformat(),
                                            "worker_instance": WORKER_INSTANCE, "process_id": os.getpid()})
    except DuplicateKeyError:
        raise HTTPException(409, "An integrity update is in progress. Retry; persistent conflicts need administrator review.")
    uncertain = False
    try:
        yield
    except BaseException as error:
        # A timeout, cancellation or unexpected error may leave a server-side
        # write in flight. Releasing here could admit a second writer too early.
        uncertain = not isinstance(error, (HTTPException, DuplicateKeyError))
        raise
    finally:
        if not uncertain:
            await asyncio.shield(db.integrity_locks.delete_one({"_id": "employee-account-writes", "owner": token}))


async def validate_manager(db, manager_id, employee=None, tenant="solvit"):
    if employee and employee.get("reports_to_board") is True:
        if str(employee.get("role_title") or "").strip().casefold() != "managing director":
            raise HTTPException(422, "Only the Managing Director can use the Board reporting root.")
        if manager_id:
            raise HTTPException(422, "Board reporting cannot also name an employee manager.")
        return None
    if not manager_id:
        if employee and employee.get("is_board_chair") is True:
            return None
        raise HTTPException(422, "Line Manager is required for approval routing.")
    manager = await find_employee(db, manager_id, tenant)
    if not manager:
        raise HTTPException(422, "Selected Line Manager not found.")
    if manager.get("lifecycle_state") in INELIGIBLE_MANAGER_STATES:
        raise HTTPException(422, "Selected Line Manager is no longer eligible.")
    canonical = employee_key(manager)
    target_aliases = {employee_key(employee), str(employee.get("_id") or "")} if employee else set()
    visited = set()
    current = manager
    while current:
        key = employee_key(current)
        if key in target_aliases or str(current["_id"]) in target_aliases:
            raise HTTPException(422, "Line Manager assignment would create a reporting cycle.")
        if key in visited:
            raise HTTPException(422, "Selected reporting chain already contains a cycle.")
        visited.add(key)
        parent = current.get("line_manager_id")
        if not parent:
            break  # Preserve legacy roots; do not guess their manager.
        current = await find_employee(db, parent, tenant)
        if not current:
            raise HTTPException(422, "Selected reporting chain contains an unresolved manager.")
    return canonical


async def validate_manager_departure(db, employee, new_state):
    if new_state not in INELIGIBLE_MANAGER_STATES or new_state == employee.get("lifecycle_state"):
        return
    report = await db.employees.find_one({"$and": [tenant_query(tenant_of(employee)), {
        "line_manager_id": {"$in": [employee_key(employee), str(employee["_id"])]},
        "lifecycle_state": {"$nin": list(INELIGIBLE_MANAGER_STATES)},
        "_id": {"$ne": employee["_id"]},
    }]})
    if report:
        raise HTTPException(409, "Reassign active direct reports before this manager leaves.")


async def change_employee_state(db, reference, new_state):
    async with integrity_write(db):
        current = await find_employee(db, reference)
        if not current:
            raise HTTPException(404, "Employee not found")
        if current.get("offboarding_started_at") and new_state != current.get("lifecycle_state"):
            raise HTTPException(409, "Use the authorized offboarding workflow to change this lifecycle state.")
        await validate_manager_departure(db, current, new_state)
        result = await db.employees.find_one_and_update({"_id": current["_id"]}, {"$set": {
            "lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()
        }}, return_document=True)
        return result, current.get("lifecycle_state")


async def ensure_unique_employee(db, email, tenant, exclude_id=None, employee_code=None):
    query = {"$and": [tenant_query(tenant), email_query("work_email", email)]}
    if exclude_id is not None:
        query["$and"].append({"_id": {"$ne": exclude_id}})
    if await db.employees.find_one(query):
        raise HTTPException(409, "An employee with this email already exists.")
    if employee_code:
        query = {"$and": [tenant_query(tenant), {"employee_code": employee_code}]}
        if await db.employees.find_one(query):
            raise HTTPException(409, "Employee code already exists.")


async def insert_employee(db, document):
    """Caller holds integrity_write; all interactive creation paths use this."""
    doc = dict(document)
    tenant = tenant_of(doc)
    email = normalize_email(doc.get("work_email"))
    await ensure_unique_employee(db, email, tenant, employee_code=doc.get("employee_code"))
    accounts = await email_matches(db.users, "email", email)
    if len(accounts) > 1:
        raise HTTPException(409, "Email has conflicting login accounts. Request an integrity review.")
    for account in accounts:
        if tenant_of(account) != tenant or account.get("account_type") in ("system", "solver", "board"):
            raise HTTPException(409, "Email belongs to an incompatible login account.")
        link = account.get("employee_id")
        if link:
            linked = await find_employee(db, link, tenant)
            legacy_self = link in (str(account["_id"]), account.get("id")) and not linked
            if linked or not legacy_self:
                raise HTTPException(409, "Email belongs to an account linked to another employee.")
    if doc.get("is_board_chair") and await db.employees.find_one({"$and": [tenant_query(tenant), {"is_board_chair": True}]}):
        raise HTTPException(409, "A reporting apex already exists. Request an integrity review.")
    doc["line_manager_id"] = await validate_manager(db, doc.get("line_manager_id"), employee=doc, tenant=tenant)
    doc.update(work_email=email, work_email_normalized=email, tenant_id=tenant)
    try:
        result = await db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Employee identity already exists.")
    return await db.employees.find_one({"_id": result.inserted_id})


async def resolve_manager_name(db, name, tenant="solvit"):
    name = str(name or "").strip()
    if not name:
        raise HTTPException(422, "Line Manager is required for approval routing.")
    rows = await db.employees.find({"$and": [tenant_query(tenant), {
        "full_name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
    }]}).to_list(2)
    if len(rows) != 1:
        raise HTTPException(422, "Line Manager name must identify exactly one existing employee.")
    return employee_key(rows[0])
