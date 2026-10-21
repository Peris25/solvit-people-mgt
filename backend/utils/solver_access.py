"""Tenant-scoped Solver identity and object authorization, without read writes."""
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from copy import deepcopy

from bson import ObjectId
from fastapi import HTTPException
from utils.access_matrix import get_module_access, CUSTOM_ROLE_DEFINITIONS
from utils.employee_integrity import tenant_of, tenant_query, find_employee, email_matches, normalize_email

HR_ROLES = {"hr_admin", "hr_manager"}
OPERATIONAL_FIELDS = ("full_name", "phone_number", "email", "region", "area_covered", "solver_code", "lifecycle_state",
                      "vehicle_categories", "zones_covered", "county", "sub_county", "onboarded_at",
                      "activation_date", "performance_tier", "accuracy_score", "reliability_score",
                      "timeliness_score", "client_rating_average", "jobs_completed", "payment_method",
                      "client_rating_30d", "client_rating_90d", "latest_client_rating", "latest_rating_at")
MANAGER_WRITE_FIELDS = {"full_name", "phone_number", "email", "vehicle_categories", "zones_covered",
                        "lifecycle_state", "region", "area_covered", "payment_method"}


def solver_key(record):
    return str(record.get("id") or record["_id"])


def solver_aliases(record):
    aliases = {solver_key(record), str(record["_id"])}
    aliases.update(ObjectId(value) for value in list(aliases) if ObjectId.is_valid(value))
    return list(aliases)


def validate_directory_identities(records):
    """Validate canonical aliases against a complete tenant-scoped snapshot.

    Match the string/ObjectId lookup rules of find_solver without issuing two
    database queries for every row. Never use this with a filtered snapshot.
    """
    by_alias = {}
    for record in records:
        for field in ("id", "_id"):
            value = record.get(field)
            if isinstance(value, (str, ObjectId)):
                by_alias.setdefault(value, set()).add(record["_id"])
    for record in records:
        reference = solver_key(record)
        aliases = [reference]
        if ObjectId.is_valid(reference):
            aliases.append(ObjectId(reference))
        matches = set()
        for alias in aliases:
            matches.update(by_alias.get(alias, ()))
        if matches != {record["_id"]}:
            raise HTTPException(409, "Solver not found or identity needs review")


def normalize_phone(value):
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    elif isinstance(value, float) and value.is_integer():
        value = str(int(value))
    if isinstance(value, str):
        value = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value)
    if not isinstance(value, str) or not re.fullmatch(r"\+?[\d\s().-]+", value.strip()):
        raise HTTPException(422, "A valid Solver phone number is required")
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise HTTPException(422, "A valid Solver phone number is required")
    return "+" + digits


async def find_solver(db, reference, user):
    if not isinstance(reference, (str, ObjectId)) or not str(reference):
        raise HTTPException(404, "Solver not found")
    reference = str(reference)
    clauses = [{"id": reference}, {"_id": reference}]
    if ObjectId.is_valid(reference):
        clauses += [{"_id": ObjectId(reference)}, {"id": ObjectId(reference)}]
    rows = await db.solvers.find({"$and": [tenant_query(tenant_of(user)), {"$or": clauses}]}).to_list(2)
    if len(rows) != 1:
        raise HTTPException(409 if rows else 404, "Solver not found or identity needs review")
    record = rows[0]
    # A unique storage alias must not bypass a duplicated canonical identity.
    canonical = solver_key(record)
    aliases = [{"id": canonical}, {"_id": canonical}]
    if ObjectId.is_valid(canonical):
        aliases += [{"id": ObjectId(canonical)}, {"_id": ObjectId(canonical)}]
    matches = await db.solvers.find({"$and": [tenant_query(tenant_of(user)), {"$or": aliases}]}).to_list(2)
    if len(matches) != 1 or matches[0]["_id"] != record["_id"]:
        raise HTTPException(409, "Solver identity needs review")
    return record


async def own_solver(db, user):
    if user.get("solver_id"):
        record = await find_solver(db, user["solver_id"], user)
        owners = await db.users.find({"$and": [tenant_query(tenant_of(user)),
                                               {"solver_id": {"$in": solver_aliases(record)}}]}).to_list(None)
        if any(str(owner["_id"]) != str(user.get("id") or user.get("_id")) for owner in owners):
            raise HTTPException(409, "Solver account links need review")
        return record
    # Existing email-login accounts can bind by a unique saved email. Never bind
    # by empty phone, names, department, or client-supplied subject IDs.
    if user.get("email"):
        matches = await email_matches(db.solvers, "email", user["email"], tenant_of(user))
        if len(matches) == 1:
            return await find_solver(db, solver_key(matches[0]), user)
    raise HTTPException(409, "Solver account link needs review")


async def solver_access(db, user, write=False):
    entry = get_module_access("M02", user.get("role"))
    if not entry or (write and entry.get("level") not in ("Full", "Manage")):
        raise HTTPException(403, "No access to this Solver operation")
    base_role = CUSTOM_ROLE_DEFINITIONS.get(user.get("role"), {}).get("inherits_from", user.get("role"))
    if base_role in ("solver", "employee"):
        if write:
            raise HTTPException(403, "No access to modify this Solver record")
        own = await own_solver(db, user)
        from utils.solver_workflows import view
        if view(own)['lifecycle_state'] not in {'Active', 'Registering'}:
            raise HTTPException(403, 'Solver access is unavailable for this lifecycle state')
        return {"level": "Read", "scope": "own_record"}
    scope = entry.get("scope")
    if scope == "solvers_manager":
        employee = await find_employee(db, user.get("employee_id"), tenant_of(user))
        title = re.sub(r"[^a-z]", "", str((employee or {}).get("role_title") or "").lower())
        if not employee or title not in ("solversmanager", "operationscoordinator", "operationscoordinatorheadofsolvers"):
            raise HTTPException(403, "This operation requires the Solvers Manager")
        return entry
    if scope not in (None, "own_record", "aggregate"):
        raise HTTPException(403, "Solver access scope needs approval")
    if write and scope in ("own_record", "aggregate"):
        raise HTTPException(403, "No access to modify this Solver record")
    return entry


async def authorize_solver(db, user, reference, write=False):
    entry = await solver_access(db, user, write)
    if entry.get("scope") == "aggregate":
        raise HTTPException(403, "Only aggregate Solver information is available")
    if entry.get("scope") == "own_record":
        own = await own_solver(db, user)
        record = await find_solver(db, reference, user)
        if record["_id"] != own["_id"]:
            raise HTTPException(403, "No access to another Solver's record")
        return record
    return await find_solver(db, reference, user)


def solver_view(record, user):
    from utils.solver_workflows import view
    record = view(record)
    # Keep legacy UI storage-id URLs while providing the canonical UUID
    # explicitly. Neither identity is rewritten in MongoDB.
    out = deepcopy(record) if user.get("role") in HR_ROLES else {
        field: deepcopy(record[field]) for field in OPERATIONAL_FIELDS if field in record}
    for field in ("password_hash", "password_history", "refresh_tokens", "access_token", "otp_code", "otp_secret", "otp_expires_at", "refresh_token", "token", "stored_path"):
        out.pop(field, None)
    out.update(id=str(record["_id"]), _id=str(record["_id"]), canonical_id=solver_key(record))
    return out


def manager_fields(user, supplied):
    if user.get("role") not in HR_ROLES and set(supplied) - MANAGER_WRITE_FIELDS:
        raise HTTPException(403, "Restricted Solver fields require HR access")


async def unique_phone(db, value, user, exclude=None):
    normalized = normalize_phone(value)
    async for record in db.solvers.find(tenant_query(tenant_of(user)), {"_id": 1, "phone_number": 1}):
        if exclude is not None and record["_id"] == exclude:
            continue
        try:
            saved = normalize_phone(record.get("phone_number"))
        except HTTPException:
            continue
        if saved == normalized:
            raise HTTPException(409, "Solver phone number already registered")
    return normalized


async def solver_identity_write(db, supplied, user, original=None):
    """Called inside the existing persistent write lock by every identity writer."""
    out = dict(supplied)
    if "phone_number" in out:
        phone = await unique_phone(db, out["phone_number"], user, original["_id"] if original else None)
        if original and out["phone_number"] == original.get("phone_number"):
            out.pop("phone_number")  # An unchanged save must not rewrite legacy formats.
        else:
            out["phone_number"] = phone
    if out.get("email"):
        email = normalize_email(out["email"])
        matches = await email_matches(db.solvers, "email", email, tenant_of(user))
        if any(not original or r["_id"] != original["_id"] for r in matches):
            raise HTTPException(409, "Solver email already registered")
        if original and supplied["email"] == original.get("email"):
            out.pop("email")
        else:
            out["email"] = email
    if original and "email" in out and out["email"] != original.get("email"):
        old_email = original.get("email")
        if old_email:
            owners = await email_matches(db.users, "email", old_email, tenant_of(user))
            if any(owner.get("role") == "solver" and owner.get("solver_id") not in solver_aliases(original) for owner in owners):
                raise HTTPException(409, "Link the existing Solver account explicitly before changing its contact email")
    return out


async def audit_solver(db, user, event, records=(), fields=(), *, entity_type=None, entity_id=None):
    """Metadata-only audit, tenant scoped; never copy private record values."""
    try:
        await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(user),
            **({'entity_type': entity_type, 'entity_id': str(entity_id)} if entity_type and entity_id else {}),
            "actor_id": str(user.get("id") or user.get("_id") or ""), "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(), "outcome": "success",
            "detail": {"solver_ids": [solver_key(r) for r in records], "fields": sorted(fields)}})
    except Exception:
        raise HTTPException(503, "Solver operation audit could not be recorded; contact an administrator before retrying")
