"""Handbook v2 policy for new leave; no balance or historical-record writes."""
import calendar
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from utils.employee_integrity import employee_key, tenant_of, tenant_query
from utils.employee_access import reference_ids, find_linked_record

VERSION = "handbook-v2-task06"
ACTIVE = {"Pending", "Submitted", "Pending_Manager", "Pending_HR", "Discussion_Requested", "Approved"}
PLANNED_TYPES = {"Annual", "Maternity", "Paternity", "Compassionate", "Unpaid"}


def today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise HTTPException(422, "Dates must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "A valid date is required")


def add_months(value, months):
    total = value.year * 12 + value.month - 1 + months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(value.day, calendar.monthrange(year, month + 1)[1]))


def annual_accrual(start, as_of, monthly=1.75, entitlement=21):
    """Prospective policy estimate, not a recalculation of a stored balance."""
    if as_of < start:
        return 0
    anchor = max(start, date(as_of.year, 1, 1))
    cutoff = as_of + timedelta(days=1)  # Date-only estimates include the completed date.
    months = (cutoff.year - anchor.year) * 12 + cutoff.month - anchor.month
    months -= cutoff.day < anchor.day
    return round(min(entitlement, max(0, months) * monthly), 2)


def working_units(start, end, holidays=(), saturday=0.5, workday_weights=None):
    start, end = day(start), day(end)
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Leave must end on or after its start and span no more than one year")
    result = 0.0
    current = start
    while current <= end:
        if current.isoformat() not in holidays:
            result += workday_weights[str(current.weekday())] if workday_weights else 1 if current.weekday() < 5 else saturday if current.weekday() == 5 else 0
        current += timedelta(days=1)
    return result


def sick_pay(used, requested, full_limit=30, half_limit=15):
    full = min(requested, max(0, full_limit - used))
    half = min(requested - full, max(0, full_limit + half_limit - max(full_limit, used)))
    return {"full_pay_days": full, "half_pay_days": half, "unpaid_days": requested - full - half}


async def contract_policy(db, employee):
    base = {"annual_entitlement": 21, "monthly_accrual": 1.75, "saturday_weight": 0.5, "sick_full_pay_days": 30, "sick_half_pay_days": 15,
            "sick_certificate_after_days": 3, "maternity_calendar_months": 3, "paternity_calendar_days": 14, "compassionate_paid_days": 14,
            "sick_year_basis": "anniversary", "source": "Handbook v2 / Developer Brief", "contract_verified": False}
    collection = getattr(db, "leave_policy_profiles", None)
    if collection is None:
        return base
    rows = await collection.find({"$and": [tenant_query(tenant_of(employee)), {"employee_id": {"$in": [*reference_ids(employee), employee["_id"]]}}]}).to_list(2)
    if not rows:
        return base
    if len(rows) != 1 or rows[0].get("status") != "Approved" or not isinstance(rows[0].get("contract_reference"), str) or not rows[0]["contract_reference"].strip():
        raise HTTPException(409, "Contract leave terms need an approved HR review")
    row = rows[0]
    for field in ("annual_entitlement", "monthly_accrual", "saturday_weight", "sick_full_pay_days", "sick_half_pay_days", "sick_certificate_after_days", "maternity_calendar_months", "paternity_calendar_days", "compassionate_paid_days"):
        if field in row:
            value = row[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise HTTPException(409, "Contract leave terms need an approved HR review")
            base[field] = value
    if not 0 <= base["saturday_weight"] <= 1 or not 0 < base["annual_entitlement"] <= 366 or base["monthly_accrual"] <= 0:
        raise HTTPException(409, "Contract leave terms need an approved HR review")
    base.update(source="Approved individual contract", contract_verified=True)
    if row.get("sick_year_basis"):
        if row["sick_year_basis"] not in {"calendar", "anniversary"}:
            raise HTTPException(409, "Contract sick-leave year requires HR reconciliation")
        base["sick_year_basis"] = row["sick_year_basis"]
    if row.get("annual_year_basis") not in (None, "calendar"):
        raise HTTPException(409, "Non-calendar annual leave requires an approved balance reconciliation plan")
    if not isinstance(base["maternity_calendar_months"], int) or not 1 <= base["maternity_calendar_months"] <= 12:
        raise HTTPException(409, "Contract maternity duration requires HR review")
    if row.get("annual_eligible_from"):
        base["annual_eligible_from"] = day(row["annual_eligible_from"]).isoformat()
    if row.get("leave_eligible_until"):
        base["leave_eligible_until"] = day(row["leave_eligible_until"]).isoformat()
    weights = row.get("workday_weights")
    if weights is not None:
        if not isinstance(weights, dict) or set(weights) != set("0123456") or any(isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1 for value in weights.values()):
            raise HTTPException(409, "Contract working calendar needs an approved HR review")
        base["workday_weights"] = weights
    return base


async def own_requests(db, employee):
    return await db.leave_requests.find({"$and": [tenant_query(tenant_of(employee)), {
        "employee_id": {"$in": [*reference_ids(employee), employee["_id"]]}
    }]}).to_list(None)


async def evidence(db, employee, reference):
    if not reference:
        return None
    row = await find_linked_record(db.leave_evidence, reference, employee)
    if row.get("employee_id") not in [*reference_ids(employee), employee["_id"]]:
        raise HTTPException(403, "Supporting document belongs to another employee")
    return row


async def preview(db, employee, payload, *, exclude=None, enforce=True, submitted_on=None):
    current = submitted_on or today()
    start, end = day(payload.get("start_date")), day(payload.get("end_date"))
    if end < start:
        raise HTTPException(422, "End date must be on or after start date")
    kind = payload.get("leave_type")
    if kind not in PLANNED_TYPES | {"Sick"}:
        raise HTTPException(422, "This leave category needs an explicit HR policy")
    state = str(employee.get("lifecycle_state") or "").replace("_", "").lower()
    if state not in {"active", "probation", "onboarding", "onleave", "pip", "realignment", "exiting"}:
        raise HTTPException(403, "This employee is not eligible for a new leave request")
    try:
        joined = day(employee.get("start_date"))
    except HTTPException:
        raise HTTPException(409, "HR must confirm the employment start date")
    if start < joined:
        raise HTTPException(422, "Leave cannot precede employment")
    policy = await contract_policy(db, employee)
    if policy.get("leave_eligible_until") and end > day(policy["leave_eligible_until"]):
        raise HTTPException(422, "Leave extends beyond verified contract eligibility")
    holiday_collection = getattr(db, "public_holidays", None)
    holidays = await holiday_collection.find(tenant_query(tenant_of(employee))).to_list(None) if holiday_collection is not None else []
    holiday_dates = {row.get("date") for row in holidays if isinstance(row.get("date"), str)}
    units = working_units(start.isoformat(), end.isoformat(), holiday_dates, policy["saturday_weight"], policy.get("workday_weights"))
    if units <= 0:
        raise HTTPException(422, "The requested period contains no working time")
    emergency = kind == "Sick" and payload.get("emergency_sick") is True and start <= current
    if not emergency and start <= current and enforce:
        raise HTTPException(422, "Planned leave must be requested in advance")
    if kind == "Annual":
        notice = 28 if units > 5 else 7
        if enforce and (start - current).days < notice:
            raise HTTPException(422, f"Annual leave requires at least {notice} days' advance notice")
        if policy.get("annual_eligible_from") and start < day(policy["annual_eligible_from"]):
            raise HTTPException(422, "Annual leave is not yet eligible under the verified contract")
    else:
        notice = 0
    if kind in {"Annual", "Compassionate"} and start.year != end.year:
        raise HTTPException(422, "Split this request at the calendar leave-year boundary")
    # FRD identifies a contract-anniversary sick leave year. Handbook does not
    # override its boundary; contract/HR verification remains part of final review.
    sick_anchor = add_months(joined, 12 * (start.year - joined.year))
    if sick_anchor > start:
        sick_anchor = add_months(joined, 12 * (start.year - joined.year - 1))
    sick_end = add_months(sick_anchor, 12) - timedelta(days=1)
    if policy["sick_year_basis"] == "calendar":
        sick_anchor, sick_end = date(start.year, 1, 1), date(start.year, 12, 31)
    if kind == "Sick" and end > sick_end:
        raise HTTPException(422, "Split sick leave at the contract-anniversary leave-year boundary")
    rows = [row for row in await own_requests(db, employee) if row.get("_id") != exclude]
    used_sick = 0.0
    used_compassionate = 0.0
    for row in rows:
        if row.get("status") not in ACTIVE:
            continue
        try:
            previous_start, previous_end = day(row.get("start_date")), day(row.get("end_date"))
        except HTTPException:
            raise HTTPException(409, "An existing leave record needs HR date reconciliation")
        if previous_start <= end and previous_end >= start:
            raise HTTPException(409, "This employee already has an overlapping or duplicate leave request")
        value = row.get("working_days", 0)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise HTTPException(409, "An existing leave record needs HR day reconciliation")
        if row.get("leave_type") == "Sick" and sick_anchor <= previous_start <= sick_end:
            used_sick += value
        if row.get("leave_type") == "Compassionate" and previous_start.year == start.year:
            used_compassionate += value
    tiers = sick_pay(used_sick, units, policy["sick_full_pay_days"], policy["sick_half_pay_days"])
    calendar_days = (end - start).days + 1
    requires_document = (kind == "Sick" and (calendar_days > policy["sick_certificate_after_days"] or used_sick + units > policy["sick_full_pay_days"])) or kind in {"Maternity", "Paternity"}
    doc = await evidence(db, employee, payload.get("supporting_document_id"))
    expected_type = {"Sick": "medical_certificate", "Maternity": "maternity_confirmation", "Paternity": "birth_notification"}.get(kind)
    if doc and expected_type and doc.get("document_type") != expected_type:
        raise HTTPException(422, "The supporting document type does not match this leave category")
    if enforce and requires_document and not doc:
        raise HTTPException(422, "This leave request requires its supporting medical/birth document")
    if kind == "Maternity":
        delivery = day(payload.get("expected_delivery_date"))
        if end > add_months(start, policy["maternity_calendar_months"]) - timedelta(days=1):
            raise HTTPException(422, "Maternity leave is limited to three calendar months")
        if start < delivery - timedelta(days=42) and payload.get("early_maternity_advice") is not True:
            raise HTTPException(422, "Earlier maternity leave requires documented medical advice and HR review")
    if kind == "Paternity":
        birth = day(payload.get("birth_date"))
        if start < birth or end > add_months(birth, 2) or calendar_days > policy["paternity_calendar_days"]:
            raise HTTPException(422, "Paternity leave is up to two weeks within two months of birth")
        same_event = sum((day(row["end_date"]) - day(row["start_date"])).days + 1 for row in rows
                         if row.get("leave_type") == "Paternity" and row.get("status") in ACTIVE and row.get("birth_date") == birth.isoformat())
        if same_event + calendar_days > policy["paternity_calendar_days"]:
            raise HTTPException(422, "Paternity requests for this birth exceed two weeks")
    if kind == "Compassionate" and payload.get("family_relationship") not in {"spouse", "child", "parent", "sibling"}:
        raise HTTPException(422, "Compassionate leave requires an immediate-family relationship")
    if enforce and not emergency and (not str(payload.get("notes") or "").strip() or not payload.get("handover_contact_id")):
        raise HTTPException(422, "Planned leave requires written handover notes and a covering colleague")
    if payload.get("handover_contact_id"):
        from utils.employee_integrity import find_employee
        covering = await find_employee(db, payload["handover_contact_id"], tenant_of(employee))
        if not covering or employee_key(covering) == employee_key(employee) or covering.get("lifecycle_state") != "Active":
            raise HTTPException(422, "Choose an active, different colleague for handover")
    return {"policy_version": VERSION, "working_days": units, "calendar_days": calendar_days,
            "notice_days_required": notice, "planned_handover_required": not emergency,
            "supporting_document_required": requires_document, "supporting_document_present": bool(doc),
            "extended_sick_followup_required": kind == "Sick" and units > 7,
            "sick_pay": tiers if kind == "Sick" else None,
            "compassionate_paid_days": min(units, max(0, policy["compassionate_paid_days"] - used_compassionate)) if kind == "Compassionate" else None,
            "compassionate_unpaid_days": max(0, units - max(0, policy["compassionate_paid_days"] - used_compassionate)) if kind == "Compassionate" else None,
            "short_maternity_notice": kind == "Maternity" and (start - current).days < 28,
            "high_activity": kind == "Annual" and any((start + timedelta(days=i)).month in {1, 7, 8, 9, 10, 11, 12} for i in range(calendar_days)),
            "annual_policy_estimate": annual_accrual(joined, current, policy["monthly_accrual"], policy["annual_entitlement"]),
            "policy": policy, "warning": "HR must verify contract eligibility, gazetted holidays and the recorded balance before final approval."}


async def department_cover(db, employee, current):
    if not employee.get("department"):
        raise HTTPException(409, "HR must confirm the employee department")
    # Legacy spellings are compared using the existing configurable normalizer.
    from utils.staff_views import token
    employees = await db.employees.find(tenant_query(tenant_of(employee))).to_list(None)
    peers = [row for row in employees if token(row.get("department")) == token(employee["department"]) and row["_id"] != employee["_id"]]
    start, end = day(current["start_date"]), day(current["end_date"])
    for peer in peers:
        for row in await own_requests(db, peer):
            if row.get("status") == "Approved":
                try:
                    a, b = day(row["start_date"]), day(row["end_date"])
                except HTTPException:
                    raise HTTPException(409, "HR must reconcile an approved department absence")
                if a <= end and b >= start:
                    raise HTTPException(409, "Another department absence is approved in this period; HR must resolve cover")
