"""Public contact directory policy; never writes employees or master settings."""
import json
import re
from pathlib import Path

from fastapi import HTTPException
from utils.employee_integrity import resolve_user_employee, tenant_of

STAFF_ROLES = frozenset(("employee", "line_manager", "hr_admin", "hr_manager", "finance",
                         "executive", "it_admin", "board"))
PRIVILEGED_DIRECTORY_ROLES = STAFF_ROLES - {"employee"}
# Interim conservative policy, pending HR UAT. Never publish performance or
# disciplinary state badges in a colleague's directory or organogram.
VISIBLE_STATES = frozenset(("active", "onboarding", "probation", "onleave", "noticeperiod", "exiting"))


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", value.lower()) if isinstance(value, str) else ""


def employment_type(value):
    equivalents = {"fte": "Full_Time", "fulltime": "Full_Time", "parttime": "Part_Time",
                    "fixedterm": "Fixed_Term", "solver": "Solver", "consultant": "Consultant",
                    "contractor": "Contractor"}
    return equivalents.get(normalized(value), value if isinstance(value, str) else None)


def visible_state(record):
    states = [normalized(record.get(field)) for field in ("lifecycle_state", "employment_status", "status")
              if isinstance(record.get(field), str) and record[field].strip()]
    # Conflicting legacy flags cannot publish an exited/restricted record just
    # because a newer field happens to say Active.
    return bool(states) and all(state in VISIBLE_STATES for state in states)


def business_email(value):
    if isinstance(value, str) and re.fullmatch(r"[^\s@/<>]+@[^\s@/<>]+\.[^\s@/<>]+", value.strip()):
        return value.strip()
    return None


def approved_work_phone(record):
    value = record.get("work_phone")
    if record.get("work_phone_directory_approved") is True and isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"\+?[\d ()-]{7,24}", value) and 7 <= len(re.sub(r"\D", "", value)) <= 15:
            return value
    return None


async def require_staff_directory(db, user):
    role = user.get("role")
    if role not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Staff directory access is not available for this account")
    if role not in PRIVILEGED_DIRECTORY_ROLES:
        record = await resolve_user_employee(db, user)
        if not record or employment_type(record.get("employment_type")) != "Full_Time" or not visible_state(record):
            raise HTTPException(status_code=403, detail="An eligible full-time employee account is required")


def reference_departments(tenant="solvit"):
    if tenant != "solvit":
        return []
    path = Path(__file__).resolve().parents[1] / "config" / "staff_directory.json"
    return json.loads(path.read_text(encoding="utf-8"))["departments"]


async def directory_departments(db, user):
    departments = reference_departments(tenant_of(user))
    settings = await db.system_settings.find_one({"tenant_id": tenant_of(user), "category": "workforce"},
                                                {"values.departments": 1})
    values = (settings or {}).get("values")
    configured = values.get("departments") if isinstance(values, dict) else None
    if not isinstance(configured, list):
        return departments
    # Only explicit contact_for entries override reference notes. Unknown saved
    # employee department values are preserved, never semantically remapped.
    for entry in configured:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        match = next((d for d in departments if normalized(d["name"]) == normalized(entry["name"])), None)
        if match and isinstance(entry.get("contact_for"), str):
            match["contact_for"] = entry["contact_for"]
        elif not match:
            departments.append({"name": entry["name"], "contact_for": entry.get("contact_for")
                                if isinstance(entry.get("contact_for"), str) else ""})
    return departments
