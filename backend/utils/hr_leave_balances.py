"""Read-only HR balance overview; reuse the personal balance calculator."""
import asyncio
from fastapi import HTTPException
from utils.employee_integrity import tenant_of, tenant_query, employee_key
from utils.employee_access import authorize_employee, personal_grant, reference_ids
from utils.staff_views import token
from utils.leave_balances import balances


async def overview(db, user, search="", department="", offset=0, limit=20):
    if user.get("role") not in {"hr_admin", "hr_manager", "general_manager"}:
        raise HTTPException(403, "HR access required")
    personal_grant(user, "M18")
    employees = await db.employees.find(tenant_query(tenant_of(user))).to_list(None)
    employees = [e for e in employees if token(e.get("employment_type")) in {"", "fte", "fulltime"}]
    departments = sorted({str(e.get("department") or "Not specified") for e in employees})
    needle = search.strip().casefold()
    employees = [e for e in employees if (not department or str(e.get("department") or "Not specified") == department)
                 and (not needle or needle in str(e.get("full_name") or e.get("name") or "").casefold())]
    employees.sort(key=lambda e: (str(e.get("full_name") or e.get("name") or "").casefold(), str(e["_id"])))
    semaphore = asyncio.Semaphore(4)

    async def item(employee):
        row = {"record_key": str(employee["_id"]), "employee_id": employee_key(employee), "name": employee.get("full_name") or employee.get("name") or "Name unavailable",
               "department": employee.get("department") or "Not specified", "status": employee.get("lifecycle_state") or employee.get("status"),
               "balances": None, "needs_review": False}
        async with semaphore:
            try:
                checked = await authorize_employee(db, user, employee_key(employee), "M18")
                row["balances"] = await balances(db, checked)
                from utils.leave_workflow import PENDING
                from utils.leave_balances import numeric
                from datetime import datetime, timezone
                year = str(datetime.now(timezone.utc).year)
                pending = await db.leave_requests.find({"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": [*reference_ids(checked), checked["_id"]]}, "status": {"$in": list(PENDING)}, "leave_type": "Annual"}]}).to_list(None)
                amounts = [r.get("working_days") for r in pending if str(r.get("start_date", "")).startswith(year)]
                row["annual_pending_days"] = sum(amounts) if all(numeric(v) for v in amounts) else None
                row["needs_review"] = bool(row["balances"].get("historical_balance_review") or row["balances"].get("source") == "legacy_derived" or row["balances"].get("annual_available_to_request") is None)
            except HTTPException as error:
                if error.status_code not in (404, 409):
                    raise
                row["needs_review"] = True
        return row

    return {"items": await asyncio.gather(*(item(e) for e in employees[offset:offset + limit])),
            "total": len(employees), "departments": departments, "offset": offset, "limit": limit}
