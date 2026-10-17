"""Employee-requested profile changes: HR review and separate Finance bank approval."""
from copy import deepcopy
from datetime import date, datetime, timezone
import re
import uuid

from fastapi import HTTPException
from email_validator import validate_email, EmailNotValidError
from utils.access_matrix import get_module_access
from utils.employee_access import authorize_employee, find_linked_record, reference_ids, personal_grant
from utils.employee_integrity import employee_key, resolve_user_employee, tenant_of, tenant_query, integrity_write

HR = {"hr_admin", "hr_manager"}
BANK = {"bank_name", "bank_branch", "bank_account_number", "bank_account", "mpesa_number", "payment_method", "preferred_payment_method"}
LEGACY = {"bank_account_number": "bank_account", "payment_method": "preferred_payment_method"}
TEXT = {"full_name": 160, "preferred_name": 100, "personal_email": 254, "phone_number": 30,
        "national_id_number": 40, "kra_pin": 30, "nssf_number": 40, "sha_number": 40,
        "date_of_birth": 10, "gender": 60, "bank_name": 120, "bank_branch": 120,
        "bank_account_number": 60, "mpesa_number": 30, "payment_method": 60}
EDITABLE = set(TEXT) | {"next_of_kin", "emergency_contact", "education"}
CONTACT = {"name": 160, "relationship": 80, "phone_number": 30, "email": 254}
EDUCATION = {"institution": 160, "qualification": 160, "year": 4}
PERSONAL = set(TEXT) | {"id", "full_name", "work_email", "department", "role_title", "role_level", "job_level",
                      "employment_type", "lifecycle_state", "line_manager_id", "line_manager_name", "start_date",
                      "probation_end_date", "contract_end_date", "staff_id", "employee_number"}


def now(): return datetime.now(timezone.utc).isoformat()


def safe_employee(employee):
    result = {key: employee[key] for key in PERSONAL if isinstance(employee.get(key), (str, int, float, bool))}
    result["id"] = employee_key(employee)
    for field, legacy in LEGACY.items():
        if field not in result and isinstance(employee.get(legacy), str): result[field] = employee[legacy]
    for key in ("next_of_kin", "emergency_contact"):
        value = employee.get(key)
        if isinstance(value, dict):
            result[key] = {k: v for k, v in value.items() if k in CONTACT and isinstance(v, str)}
        elif isinstance(value, str):
            result[key] = value
    education = employee.get("education")
    if isinstance(education, list):
        result["education"] = [{k: v for k, v in row.items() if k in EDUCATION and isinstance(v, (str, int))}
                               for row in education if isinstance(row, dict)]
    elif isinstance(education, str):
        result["education"] = education
    return result


def text(value, limit):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise HTTPException(422, "Profile fields must contain plain text within the permitted length")
    return value.strip()


def validated(field, value):
    value = text(value, TEXT[field] if field in TEXT else 254)
    if value and (field.endswith("email") or field == "email"):
        try: value = validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError: raise HTTPException(422, "Enter a valid personal/contact email")
    if value and field in {"phone_number", "mpesa_number"} and (not re.fullmatch(r"\+?[0-9 ()-]{7,30}", value) or not 7 <= sum(c.isdigit() for c in value) <= 15):
        raise HTTPException(422, "Enter a valid phone number")
    if field == "full_name" and len(value) < 2:
        raise HTTPException(422, "Full name must contain at least two characters")
    if value and field == "date_of_birth":
        try: parsed = date.fromisoformat(value)
        except ValueError: raise HTTPException(422, "Enter a valid date of birth")
        if len(value) != 10 or parsed > date.today(): raise HTTPException(422, "Date of birth cannot be in the future")
    if value and field == "year" and (not re.fullmatch(r"\d{4}", value) or not 1900 <= int(value) <= date.today().year + 10):
        raise HTTPException(422, "Enter a valid education year")
    return value


def validate_changes(changes):
    if not isinstance(changes, dict) or not changes or set(changes) - EDITABLE:
        raise HTTPException(422, "Only permitted personal profile fields may be requested")
    result = {}
    for key, value in changes.items():
        if key in TEXT:
            result[key] = validated(key, value)
        elif key in {"next_of_kin", "emergency_contact"}:
            if not isinstance(value, dict) or not value or set(value) - set(CONTACT):
                raise HTTPException(422, "Contact changes require name, relationship, phone_number and/or email")
            result[key] = {k: validated(k, text(v, CONTACT[k])) for k, v in value.items()}
        elif key == "education":
            if not isinstance(value, list) or len(value) > 20:
                raise HTTPException(422, "Education must be a list of no more than 20 entries")
            result[key] = []
            for row in value:
                if not isinstance(row, dict) or not row or set(row) - set(EDUCATION):
                    raise HTTPException(422, "Education entries require institution, qualification and/or year")
                result[key].append({k: validated(k, text(v, EDUCATION[k])) for k, v in row.items()})
    return result


async def self_employee(db, user):
    personal_grant(user, "M01")
    employee = await resolve_user_employee(db, user)
    if not employee:
        raise HTTPException(409, "HR must link this account to an employee record")
    if str(employee.get("lifecycle_state", "")).lower() in {"exited", "suspended", "terminated"}:
        raise HTTPException(403, "This employee account is not eligible for self-service")
    return employee


async def reviewer(db, user, reference):
    if user.get("role") in HR:
        return await authorize_employee(db, user, reference, "M01", write=True)
    if user.get("role") == "finance" and get_module_access("M10", "finance"):
        from utils.employee_integrity import find_employee
        employee = await find_employee(db, reference, tenant_of(user))
        if employee: return employee
    raise HTTPException(403, "Only authorized HR/Finance may review profile changes")


def public_change(row, user):
    fields = {"id", "employee_id", "status", "changes", "created_at", "reviewed_at", "review_reason", "hr_approved_at", "finance_approved_at"}
    finance_review = user.get("role") == "finance" and user.get("employee_id") != row.get("employee_id")
    if finance_review:
        fields.discard("review_reason")
    result = {k: deepcopy(v) for k, v in row.items() if k in fields}
    if finance_review:
        result["changes"] = {k: v for k, v in result.get("changes", {}).items() if k in BANK}
    for field in ("next_of_kin", "emergency_contact"):
        if isinstance(result.get("changes", {}).get(field), dict):
            result["changes"][field] = {k: v for k, v in result["changes"][field].items() if k in CONTACT and isinstance(v, str)}
    if isinstance(result.get("changes", {}).get("education"), list):
        result["changes"]["education"] = [{k: v for k, v in entry.items() if k in EDUCATION and isinstance(v, (str, int))}
                                          for entry in result["changes"]["education"] if isinstance(entry, dict)]
    return result


async def list_changes(db, user, reference=None):
    employee = await reviewer(db, user, reference) if reference else await self_employee(db, user)
    rows = await db.employee_profile_changes.find({"$and": [tenant_query(tenant_of(user)), {
        "employee_id": {"$in": [*reference_ids(employee), employee["_id"]]}}]}).sort("created_at", -1).to_list(100)
    if reference and user.get("role") == "finance": rows = [r for r in rows if set(r.get("changes", {})) & BANK]
    return [public_change(row, user) for row in rows]


async def submit(db, user, changes):
    changes = validate_changes(changes)
    async with integrity_write(db):
        employee = await self_employee(db, user)
        if "education" in changes and employee.get("education"):
            saved = employee["education"]
            if not isinstance(saved, list) or any(not isinstance(entry, dict) for entry in saved):
                raise HTTPException(409, "HR must review the legacy education format before adding a record")
            changes["education"] = deepcopy(saved) + changes["education"]
        for field, legacy in LEGACY.items():
            if field in changes and legacy in employee:
                if field in employee and employee[field] != employee[legacy]:
                    raise HTTPException(409, "Conflicting legacy bank fields require HR reconciliation")
                changes[legacy] = changes[field]
                if field not in employee: changes.pop(field)
        # Partial contact changes preserve all saved fields, including legacy names.
        for key in ("next_of_kin", "emergency_contact"):
            if key in changes and isinstance(employee.get(key), dict):
                changes[key] = {**employee[key], **changes[key]}
        changes = {k: v for k, v in changes.items() if v != employee.get(k)}
        if not changes: raise HTTPException(422, "No changed profile fields were supplied")
        pending = await db.employee_profile_changes.find_one({"$and": [tenant_query(tenant_of(user)), {
            "employee_id": employee_key(employee), "status": {"$in": ["Pending_HR", "Pending_Finance", "Applying"]}}]})
        if pending: raise HTTPException(409, "An existing profile change is awaiting review")
        row = {"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "employee_id": employee_key(employee),
               "employee_storage_id": str(employee["_id"]), "changes": changes,
               "before": {k: deepcopy(employee.get(k)) for k in changes}, "status": "Pending_HR",
               "submitted_by": user["id"], "created_at": now()}
        await db.employee_profile_changes.insert_one(row)
    return public_change(row, user)


async def decide(db, user, reference, decision, reason=""):
    if decision not in {"Approve", "Reject"}: raise HTTPException(422, "Choose Approve or Reject")
    reason = text(reason, 2000)
    async with integrity_write(db):
        row = await find_linked_record(db.employee_profile_changes, reference, user)
        employee = await reviewer(db, user, row["employee_id"])
        if str(employee["_id"]) != row.get("employee_storage_id"):
            raise HTTPException(409, "Employee identity changed; HR integrity review is required")
        if row.get("submitted_by") == user["id"] or employee_key(employee) == user.get("employee_id"):
            raise HTTPException(403, "Employees cannot approve their own profile changes")
        required = "hr" if row["status"] == "Pending_HR" else "finance" if row["status"] == "Pending_Finance" else None
        if required is None: raise HTTPException(409, "This request is no longer awaiting review")
        if (required == "hr" and user.get("role") not in HR) or (required == "finance" and user.get("role") != "finance"):
            raise HTTPException(403, "This request is assigned to a different reviewer")
        if row.get("hr_approved_by") == user["id"]:
            raise HTTPException(403, "Finance review must be independent of HR approval")
        # Detect intervening HR edits rather than overwrite them with an old request.
        if decision == "Approve" and any(employee.get(k) != v for k, v in row["before"].items()):
            raise HTTPException(409, "Saved profile changed since submission; reject and submit a fresh request")
        status = "Rejected" if decision == "Reject" else "Pending_Finance" if required == "hr" and set(row["changes"]) & BANK else "Approved"
        if decision == "Reject" and not reason: raise HTTPException(422, "A rejection reason is required")
        update = {"status": status, "review_reason": reason, "reviewed_at": now(), f"{required}_approved_by": user["id"] if decision == "Approve" else None}
        if decision == "Approve": update[f"{required}_approved_at"] = now()
        if status == "Approved":
            # Mark in-flight before writing the employee. An interrupted multi-write
            # is visibly fail-closed, never silently retried or applied twice.
            await db.employee_profile_changes.update_one({"_id": row["_id"]}, {"$set": {**update, "status": "Applying", "application_started_at": now()}})
            changed = await db.employees.update_one({"_id": employee["_id"], **row["before"]}, {"$set": {**row["changes"], "updated_at": now()}})
            if changed.modified_count != 1:
                raise RuntimeError("Profile application needs operator review; the request remains Applying")
        await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "action": "profile.change." + decision.lower(),
                                        "actor_id": user["id"], "employee_id": employee_key(employee), "change_request_id": row["id"],
                                        "fields": list(row["changes"]), "stage": required, "created_at": now()})
        await db.employee_profile_changes.update_one({"_id": row["_id"]}, {"$set": update})
    return public_change({**row, **update}, user)
