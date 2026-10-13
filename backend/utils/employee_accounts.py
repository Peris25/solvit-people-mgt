"""Explicit, idempotent provisioning; existing passwords and roles are retained."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from utils.auth import hash_password
from utils.security import validate_password_policy
from utils.employee_integrity import (
    employee_key, email_matches, find_employee, integrity_write,
    normalize_email, tenant_of, tenant_query,
)


async def provision_employee_account(db, employee_id, password, actor):
    async with integrity_write(db):
        employee = await find_employee(db, employee_id, tenant_of(actor))
        if not employee:
            raise HTTPException(404, "Employee not found")
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
