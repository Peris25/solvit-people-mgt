"""Explicit, idempotent provisioning; existing passwords and roles are retained."""
from datetime import datetime, timezone
from collections import Counter

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from utils.auth import hash_password
from utils.security import validate_password_policy
from utils.employee_integrity import (
    employee_key, email_matches, find_employee, integrity_write,
    normalize_email, tenant_of, tenant_query,
    resolve_user_employee,
)


async def employee_login_review(db, actor):
    """Read-only rollout review. Reuse authentication's identity resolution.

    Readiness is a linkage check, not a promise that MFA/password requirements
    or deployment configuration have been completed. Never return credentials.
    """
    from utils.staff_directory import employment_type, visible_state

    tenant = tenant_of(actor)
    employees = await db.employees.find(tenant_query(tenant)).sort("full_name", 1).to_list(None)
    users = await db.users.find(tenant_query(tenant)).to_list(None)
    emails = Counter(str(e.get("work_email") or "").strip().lower() for e in employees)
    identities = Counter(employee_key(e) for e in employees)
    resolved, failures = {}, set()
    for user in users:
        try:
            target = await resolve_user_employee(db, user)
            if target:
                resolved[str(user["_id"])] = str(target["_id"])
        except HTTPException:
            failures.add(str(user["_id"]))
    result = []
    for employee in employees:
        kind = employment_type(employee.get("employment_type") or employee.get("employee_type"))
        if kind not in ("Full_Time", None, ""):
            continue
        key = employee_key(employee)
        if actor.get("role") == "hr_admin" and employee.get("board_only") and key != actor.get("employee_id"):
            continue
        aliases = {key, str(employee["_id"])}
        email = str(employee.get("work_email") or "").strip().lower()
        candidates = [u for u in users if (str(u.get("employee_id") or "") in aliases
                      or (email and str(u.get("email") or "").strip().lower() == email))]
        issues = []
        if not kind: issues.append("Employment type needs HR confirmation")
        if identities[key] > 1: issues.append("Employee identifier is duplicated")
        if email and emails[email] > 1: issues.append("Work email is shared by employee records")
        if employee.get("board_only") or not visible_state(employee):
            issues.append("Employee status or visibility requires HR review before access")
        try:
            normalize_email(employee.get("work_email"))
        except HTTPException:
            issues.append("Valid work email required")
        if not candidates:
            issues.append("No login account found")
        elif len(candidates) != 1:
            issues.append("Multiple matching accounts require integrity review")
        else:
            user = candidates[0]
            user_key = str(user["_id"])
            if user_key in failures or resolved.get(user_key) != str(employee["_id"]):
                issues.append("Account employee link requires integrity review")
            if user.get("is_active") is False:
                issues.append("Login account disabled")
        user = candidates[0] if len(candidates) == 1 else None
        result.append({"record_id": str(employee["_id"]), "employee_id": key, "full_name": employee.get("full_name"),
                       "work_email": employee.get("work_email"), "department": employee.get("department"),
                       "role": user.get("role") if user else None,
                       "account_id": str(user["_id"]) if user else None,
                       "must_change_password": bool(user.get("must_change_password")) if user else None,
                       "status": "Needs review" if issues else "Linked", "issues": issues})
        if actor.get("role") == "hr_admin":
            result[-1].pop("account_id", None)
    return result


async def provision_employee_account(db, employee_id, password, actor):
    async with integrity_write(db):
        employee = await find_employee(db, employee_id, tenant_of(actor))
        if not employee:
            raise HTTPException(404, "Employee not found")
        from utils.staff_directory import visible_state
        if employee.get("board_only") or not visible_state(employee):
            raise HTTPException(409, "Employee status or visibility requires HR review before account provisioning.")
        tenant = tenant_of(employee)
        key = employee_key(employee)
        email = normalize_email(employee.get("work_email"))
        matches = await email_matches(db.employees, "work_email", email, tenant)
        if len(matches) != 1:
            raise HTTPException(409, "Employee email is ambiguous. Request an integrity review.")
        owners = await db.users.find({"$and": [tenant_query(tenant), {
            "employee_id": {"$in": [key, str(employee["_id"])]}
        }]}).to_list(2)
        candidates = await email_matches(db.users, "email", email)
        accounts = {str(u["_id"]): u for u in owners + candidates}
        if len(accounts) > 1:
            raise HTTPException(409, "Employee has conflicting accounts. Request an integrity review.")
        existing = next(iter(accounts.values()), None)
        if existing:
            if actor.get("role") == "hr_admin" and existing.get("role") != "employee":
                raise HTTPException(403, "IT Admin must manage existing privileged or manager accounts. Password and role were preserved.")
            if tenant_of(existing) != tenant or existing.get("account_type") in ("system", "solver", "board"):
                raise HTTPException(409, "Account is not eligible for employee linking.")
            link = existing.get("employee_id")
            linked_employee = await find_employee(db, link, tenant) if link else None
            if linked_employee and employee_key(linked_employee) != key:
                raise HTTPException(409, "Account is linked to a different employee.")
            if link and link not in (key, str(employee["_id"]), str(existing["_id"]), existing.get("id")):
                raise HTTPException(409, "Account is linked to a different employee.")
            if link != key:
                try:
                    await db.users.update_one({"_id": existing["_id"]}, {"$set": {
                        "employee_id": key, "account_type": "employee", "tenant_id": tenant,
                    }})
                except DuplicateKeyError:
                    raise HTTPException(409, "Employee already has a login account.")
            user_id = str(existing["_id"])
            created = False
        else:
            if not password:
                raise HTTPException(422, "An initial password is required for a new account.")
            validate_password_policy(password, [])
            try:
                result = await db.users.insert_one({
                    "tenant_id": tenant, "employee_id": key, "account_type": "employee",
                    "email": email, "email_normalized": email,
                    "full_name": employee.get("full_name", ""),
                    "department": employee.get("department"), "role": "employee",
                    "is_active": True, "must_change_password": True,
                    "password_hash": hash_password(password),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            except DuplicateKeyError:
                raise HTTPException(409, "Account identity already exists.")
            user_id, created = str(result.inserted_id), True
        await db.audit_logs.insert_one({
            "tenant_id": tenant, "event": "account.employee.provisioned",
            "actor_id": actor["id"], "entity_id": user_id,
            "metadata": {"employee_id": key, "created": created},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"id": user_id, "employee_id": key, "created": created}


async def preserve_employee_account_link(db, employee, new_email, actor):
    """Keep an already-authorized login attached during an explicit HR edit.

    The caller holds integrity_write. Resolve locally using the same rules as
    authentication; no external system or manual legacy verification is used.
    Login email, password, role and account activation remain unchanged.
    """
    tenant = tenant_of(employee)
    old_email = str(employee.get('work_email') or '').strip().lower()
    candidates = await email_matches(db.users, 'email', old_email) if old_email else []
    candidates += await email_matches(db.users, 'email', new_email)
    accounts = {str(user['_id']): user for user in candidates}
    pending = []
    for user in accounts.values():
        if tenant_of(user) != tenant:
            raise HTTPException(409, 'Email belongs to a different login account.')
        linked = await resolve_user_employee(db, user)
        if not linked or linked['_id'] != employee['_id']:
            raise HTTPException(409, 'Email belongs to a different or conflicting employee account.')
        if user.get('employee_id') != employee_key(employee):
            pending.append(user)
    for user in pending:
        await db.users.update_one({'_id': user['_id']}, {'$set': {
            'employee_id': employee_key(employee), 'account_type': 'employee', 'tenant_id': tenant}})
        await db.audit_logs.insert_one({'tenant_id': tenant, 'event': 'account.employee.link_normalized',
                                       'actor_id': actor['id'], 'entity_id': str(user['_id']),
                                       'metadata': {'employee_id': employee_key(employee)},
                                       'timestamp': datetime.now(timezone.utc).isoformat()})
