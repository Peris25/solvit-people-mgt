"""Read-only compatibility view. Never writes balances or recalculates saved units."""
from datetime import datetime, timezone
import math
from fastapi import HTTPException
from utils.employee_access import reference_ids
from utils.employee_integrity import tenant_of, tenant_query


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


async def balances(db, employee):
    from routes.leave import _active_leave_types
    from utils.leave_workflow import availability
    now = datetime.now(timezone.utc)
    aliases = [*reference_ids(employee), employee["_id"]]
    scope = {"$and": [tenant_query(tenant_of(employee)), {"employee_id": {"$in": aliases}}]}
    collection = getattr(db, "leave_balances", None)
    snapshots = await collection.find(scope).to_list(None) if collection is not None else []
    candidates = [row for row in snapshots if row.get("year") in (None, now.year, str(now.year))]
    if len(candidates) > 1:
        raise HTTPException(409, "Multiple balance snapshots need an approved HR reconciliation")
    types = await _active_leave_types()
    result = {}
    if candidates:
        snapshot = candidates[0]
        # Preserve recognized figures verbatim; unknown formats are unavailable.
        for name, info in types.items():
            recorded = snapshot.get(name) if isinstance(snapshot.get(name), dict) else {}
            remaining = recorded.get("remaining")
            if remaining is None:
                key = "annual_remaining_days" if name == "Annual" else "sick_remaining_days" if name == "Sick" else None
                remaining = snapshot.get(key) if key else None
            if remaining is None:
                remaining = snapshot.get("annual_days_remaining" if name == "Annual" else "sick_days_remaining" if name == "Sick" else "__unused__")
            result[name] = {"remaining": remaining if numeric(remaining) else None, "description": info["description"], "balance_label": "Recorded balance"}
            for field in ("entitlement", "used", "accrued_kenyan_act"):
                if numeric(recorded.get(field)):
                    result[name][field] = recorded[field]
        result.update(source="stored_snapshot", year=snapshot.get("year"), warning="Recorded figures are preserved. New workflow commitments are shown separately; HR must reconcile undated or stale snapshots.")
    else:
        rows = await db.leave_requests.find(scope).to_list(None)
        used = {}
        for row in rows:
            if row.get("status") == "Approved" and str(row.get("start_date", "")).startswith(str(now.year)):
                value = row.get("working_days", 0)
                if not numeric(value):
                    raise HTTPException(409, "Historical leave units need HR reconciliation")
                kind = row.get("leave_type", "Annual")
                used[kind] = used.get(kind, 0) + value
        months = max(0, now.month - 1)
        start_valid = False
        try:
            start = datetime.fromisoformat(employee.get("start_date", ""))
            start_valid = start.date() <= now.date()
            if start.year == now.year:
                months = max(0, now.month - start.month - (0 if now.day >= start.day else 1))
        except (TypeError, ValueError):
            pass
        accrued = round(months * 1.75, 2) if start_valid else None
        for name, info in types.items():
            entitlement = info["days_entitlement"]
            result[name] = {"entitlement": entitlement, "used": used.get(name, 0), "remaining": max(0, entitlement - used.get(name, 0)), "description": info["description"]}
            if name == "Annual":
                result[name].update(accrued_kenyan_act=accrued, completed_months_in_year=months,
                                    remaining=round(max(0, accrued - used.get(name, 0)), 2) if accrued is not None else None,
                                    balance_label="Legacy derived estimate")
        result.update(source="legacy_derived", year=now.year, accrued_annual=accrued,
                      warning="No saved balance snapshot. Existing derived figures are retained; new contract/policy estimates do not replace them. HR verification is required.")
    result["annual_days_remaining"] = result.get("Annual", {}).get("remaining")
    result["sick_days_remaining"] = result.get("Sick", {}).get("remaining")
    try:
        result["annual_available_to_request"] = await availability(db, employee, result)
    except HTTPException:
        result["annual_available_to_request"] = None
    return result
