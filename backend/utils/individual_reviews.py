"""HR creates a dated employee review in one action, reusing performance records."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import uuid
from fastapi import HTTPException
from utils.employee_integrity import employee_key, find_employee, tenant_of, tenant_query
from utils.employee_access import reference_ids
from utils.staff_views import token

TYPES = {"Mid_Year", "Year_End", "Probation"}


async def create(db, user, body):
    from utils import performance_workflows as flow
    flow.require_hr(user)
    employee = await flow.employee_access(db, user, body["employee_id"], write=True)
    kind, year = body.get("cycle_type"), body.get("cycle_year")
    if kind not in TYPES or isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        flow.fail("Choose a valid review type and year")
    state = token(employee.get("lifecycle_state") or employee.get("status"))
    if state not in {"active", "onboarding", "probation", "onleave", "pip"}:
        flow.fail("This employee is not eligible for a new review", 409)
    if kind == "Probation":
        if state not in {"onboarding", "probation"} and employee.get("onboarding_recorded_status") != "In_Progress":
            flow.fail("Probation reviews are for employees in onboarding or probation", 409)
        if isinstance(body.get("review_month"), bool) or body.get("review_month") not in (1, 2, 3):
            flow.fail("Choose probation Month 1, 2 or 3")
    elif body.get("review_month") is not None:
        flow.fail("Probation month applies only to probation reviews")
    manager = await find_employee(db, employee.get("line_manager_id"), tenant_of(user))
    if not manager or manager["_id"] == employee["_id"]:
        flow.fail("Assign a valid line manager before creating this review", 409)
    if token(manager.get("lifecycle_state") or manager.get("status")) not in {"active", "probation", "onleave", "pip"}:
        flow.fail("An active reporting manager is required", 409)
    try:
        start, self_due, manager_due, hr_due = [date.fromisoformat(body[key]) for key in ("starts_on", "self_due_on", "manager_due_on", "review_due_on")]
    except (KeyError, TypeError, ValueError): flow.fail("Enter all four review dates")
    today = datetime.now(timezone(timedelta(hours=3))).date()
    if start.year != year or not start <= self_due <= manager_due <= hr_due or self_due < today:
        flow.fail("Dates must follow start, employee deadline, manager deadline and HR deadline; submission deadlines cannot be in the past")
    if kind != "Probation" and hr_due > start + timedelta(days=27):
        flow.fail("Mid-year and year-end review deadlines must fit within four weeks of the start")
    prior = await db.performance_reviews.find({"$and": [tenant_query(tenant_of(user)),
        {"employee_id": {"$in": reference_ids(employee) + [employee["_id"]]}, "cycle_year": year}]}).to_list(None)
    if any((r.get("cycle_type") == kind and (kind != "Probation" or r.get("review_month") == body.get("review_month"))) or r.get("cycle_type") not in TYPES for r in prior):
        flow.fail("A review already exists for this employee and period. Open the existing review", 409)
    if kind == "Probation":
        if body.get("policy") or body.get("policy_confirmed"):
            flow.fail("Probation reviews use qualitative review criteria, not weighted annual scores")
        policy = {"source": "probation_form_08", "approved_by": user["id"], "approved_at": flow.now()}
    else:
        if body.get("policy_confirmed") is not True or body.get("policy") not in flow.POLICIES:
            flow.fail("HR must confirm the selected scoring policy in this popup")
        policy = {**deepcopy(flow.POLICIES[body["policy"]]), "source": body["policy"], "approved_by": user["id"],
                  "approval_reference": "HR confirmed policy when creating this individual review", "approved_at": flow.now()}
    row = {"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "employee_id": employee_key(employee),
        "cycle_type": kind, "cycle_year": year, "review_scope": "individual", "workflow_version": 1,
        "status": "Draft", "section_a_kpis": [], "starts_on": start.isoformat(), "self_due_on": self_due.isoformat(),
        "manager_due_on": manager_due.isoformat(), "review_due_on": hr_due.isoformat(), "scoring_policy": policy,
        "created_at": flow.now(), "updated_at": flow.now()}
    if kind == "Probation": row["review_month"] = body["review_month"]
    await flow.audit(db, user, "performance.review.created", row, employee_id=employee_key(employee), review_type=kind, dates={k:row[k] for k in ("starts_on","self_due_on","manager_due_on","review_due_on")})
    await db.performance_reviews.insert_one(row)
    await flow.notify(db, row, "created")
    return flow.projection(row, user, employee)


async def probation_assessment(db, user, row, employee, stage, body):
    from utils import performance_workflows as flow
    own = employee_key(employee) == user.get("employee_id")
    if stage == "manager":
        from utils.employee_integrity import is_direct_report
        await flow.employee_access(db, user, row["employee_id"], write=True)
        if own or not is_direct_report(employee, user): flow.fail("Only the current reporting manager may assess probation", 403)
        if row.get("status") != "Self_Submitted": flow.fail("Employee self-assessment must be submitted first", 409)
        if set(body) != {"summary", "delivery_rating", "values_rating", "specific_examples", "areas_for_improvement", "recommendation"}:
            flow.fail("Provide the probation review fields only")
        if body["delivery_rating"] not in {"Exceeds", "Meets", "Approaching", "Below"} or body["values_rating"] not in {"Strong", "Adequate", "Concerns"}:
            flow.fail("Select valid probation ratings")
        allowed = {"Continue probation"} if row.get("review_month") in (1,2) else {"Confirm", "Extend by 1 month", "Fail"}
        if body["recommendation"] not in allowed: flow.fail("Select a recommendation appropriate to this probation month")
        assessment = {k:flow.text(body[k], k.replace('_',' ')) for k in body}
        assessment.update(actor_id=user["id"], submitted_at=flow.now())
        update = {"manager_assessment": assessment, "status":"Manager_Submitted"}
    else:
        flow.require_hr(user)
        if own: flow.fail("HR cannot approve their own probation review", 403)
        if row.get("status") != "Manager_Submitted": flow.fail("Manager assessment must be submitted first", 409)
        if set(body) != {"summary"}: flow.fail("Probation approval accepts an HR summary, not numeric scores or employment-status changes")
        update = {"hr_summary":flow.text(body["summary"], "HR summary"), "hr_reviewed_by":user["id"], "hr_reviewed_at":flow.now(), "status":"HR_Reviewed"}
    await flow.save(db,user,row,update,"performance.assessment."+stage)
    return flow.projection(row,user,employee)
