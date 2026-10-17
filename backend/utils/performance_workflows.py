"""Scoped performance workflow over existing reviews; historical scores are immutable."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import math
import hashlib
import json
import uuid
from fastapi import HTTPException
from utils.employee_access import authorize_employee, find_linked_record, personal_grant, reference_ids
from utils.employee_integrity import employee_key, find_employee, is_direct_report, tenant_of, tenant_query
from utils.staff_views import restricted

HR = {"hr_admin", "hr_manager"}
POLICIES = {"handbook_frd": {"weights": [50, 30, 20], "section_c": "Client Feedback"},
            "developer_brief": {"weights": [60, 25, 15], "section_c": "Alignment"}}


def now(): return datetime.now(timezone.utc).isoformat()


def fail(message, status=422): raise HTTPException(status, message)


def text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        fail(f"A valid {label} is required")
    return value.strip()


def score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 3:
        fail("Assessment scores must be finite numbers from 1 to 3")
    return float(value)


async def employee_access(db, user, reference, write=False):
    employee = await authorize_employee(db, user, reference, "M05", write=write)
    if restricted(employee.get("board_only")):
        fail("Board-led reviews are administered through the existing Board process", 403)
    return employee


def require_hr(user):
    if user.get("role") not in HR: fail("HR authorization required", 403)
    personal_grant(user, "M05", write=True)


async def audit(db, user, event, row, **metadata):
    await db.audit_logs.insert_one({"tenant_id": tenant_of(user), "event": event,
        "entity_id": str(row.get("id") or row.get("_id")), "actor_id": user["id"],
        "timestamp": now(), "metadata": metadata})


def released(row):
    # Legacy Completed status is not evidence that HR published a score.
    return bool(row.get("released_at") and row.get("released_by"))


def projection(row, user, employee=None):
    result = {key: deepcopy(row[key]) for key in ("employee_id", "cycle_id", "cycle_type", "cycle_label", "cycle_year", "review_date", "status",
        "created_at", "updated_at", "self_due_on", "manager_due_on", "review_due_on", "workflow_version", "released_at") if key in row}
    result["goals_acknowledged_at"] = row.get("goals_acknowledged_at")
    result["id"] = str(row.get("id") or row.get("_id"))
    if employee:
        result.update(employee_id=employee_key(employee), employee_name=employee.get("full_name"),
                      role_title=employee.get("role_title"), department=employee.get("department"))
    own = (employee_key(employee) if employee else row.get("employee_id")) == user.get("employee_id")
    privileged = user.get("role") in HR or (not own and user.get("role") in {"line_manager", "finance", "executive"})
    result["scores_released"] = released(row)
    result["section_a_kpis"] = deepcopy(row.get("section_a_kpis") or []) if row.get("workflow_version") == 1 else []
    result["self_assessment"] = deepcopy(row.get("self_assessment")) if row.get("workflow_version") == 1 else None
    if privileged and not own or released(row):
        for key in ("section_a_score", "section_b_score", "section_c_score", "overall_score", "rating",
                    "nine_box_placement", "manager_assessment", "scoring_policy", "hr_summary"):
            if key in row: result[key] = deepcopy(row[key])
    else:
        for key in ("section_a_score", "section_b_score", "section_c_score", "overall_score", "rating", "nine_box_placement"):
            result[key] = None
    if "scoring_policy" in result and user.get("role") not in HR:
        result["scoring_policy"] = {key: result["scoring_policy"].get(key) for key in ("source", "weights", "section_c")}
    for key in ("section_a_score", "section_b_score", "section_c_score", "overall_score"):
        value = result.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value): result[key] = round(value, 1)
    writable = True
    try: personal_grant(user, "M05", write=True)
    except HTTPException: writable = False
    result["can_self_assess"] = writable and own and row.get("workflow_version") == 1 and row.get("status") in {"Draft", "Self_Draft"}
    result["can_update_goal_progress"] = writable and own and row.get("workflow_version") == 1 and row.get("status") in {"Draft", "Self_Draft", "Self_Submitted"}
    result["can_manage"] = writable and bool(employee and not own and is_direct_report(employee, user))
    result["can_hr_review"] = writable and user.get("role") in HR and not own
    return result


async def notify(db, row, event):
    employee = await find_employee(db, row.get("employee_id"), tenant_of(row))
    if not employee: fail("Review employee needs an integrity review", 409)
    recipients = [("employee", employee_key(employee)), ("role", "hr_admin"), ("role", "hr_manager")]
    manager = await find_employee(db, employee.get("line_manager_id"), tenant_of(row))
    if manager: recipients.append(("employee", employee_key(manager)))
    for kind, recipient in recipients:
        key = f"performance:{tenant_of(row)}:{row['id']}:{event}:{kind}:{recipient}"
        await db.notifications.update_one({"_id": key}, {"$setOnInsert": {"id": key,
            "tenant_id": tenant_of(row), "category": "Performance", "created_at": now(), "is_read": False,
            **({"recipient_role": recipient} if kind == "role" else {"recipient_type": "employee", "recipient_id": recipient}),
            "data": {"employee_id": employee_key(employee), "performance_review_id": row["id"]}}}, upsert=True)


async def create_cycle(db, user, body):
    require_hr(user)
    allowed = {"cycle_type", "cycle_year", "starts_on", "self_due_on", "manager_due_on", "policy", "approval_reference"}
    if set(body) - allowed: fail("Unknown cycle configuration fields")
    kind, year = body.get("cycle_type"), body.get("cycle_year")
    if not isinstance(kind, str) or kind not in {"Mid_Year", "Year_End"} or isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        fail("Choose a valid review cycle and year")
    try:
        start, self_due, manager_due = [date.fromisoformat(body[key]) for key in ("starts_on", "self_due_on", "manager_due_on")]
    except (KeyError, TypeError, ValueError): fail("Valid cycle and assessment dates are required")
    end = start + timedelta(days=27)
    if start.year != year or not start <= self_due <= manager_due <= end:
        fail("Assessment deadlines must fall within the four-week cycle")
    cycles = await db.performance_cycles.find(tenant_query(tenant_of(user))).to_list(None)
    if any(row.get("starts_on", "z") <= end.isoformat() and row.get("ends_on", "") >= start.isoformat() for row in cycles):
        fail("Review cycles cannot overlap", 409)
    policy = body.get("policy")
    if not isinstance(policy, str) or policy not in POLICIES: fail("Choose a documented scoring policy for HR approval")
    reference = text(body.get("approval_reference"), "HR scoring-policy approval reference", 300)
    if await db.performance_cycles.find_one({"$and": [tenant_query(tenant_of(user)), {"cycle_type": kind, "cycle_year": year}]}):
        fail("A cycle already exists for this period", 409)
    row = {"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "cycle_type": kind, "cycle_year": year,
        "starts_on": start.isoformat(), "self_due_on": self_due.isoformat(), "manager_due_on": manager_due.isoformat(),
        "ends_on": end.isoformat(), "status": "Configured", "created_at": now(), "created_by": user["id"],
        "scoring_policy": {**deepcopy(POLICIES[policy]), "source": policy, "approved_by": user["id"],
                           "approval_reference": reference, "approved_at": now()}}
    await audit(db, user, "performance.cycle.configured", row, policy=row["scoring_policy"])
    await db.performance_cycles.insert_one(row)
    return {k: v for k, v in row.items() if k not in {"_id", "tenant_id"}}


async def create_review(db, user, body):
    require_hr(user)
    employee = await employee_access(db, user, body["employee_id"], write=True)
    cycle = await db.performance_cycles.find_one({"$and": [tenant_query(tenant_of(user)), {
        "cycle_type": body["cycle_type"], "cycle_year": body["cycle_year"]}]})
    if not cycle: fail("HR must configure and approve this review cycle first", 409)
    aliases = reference_ids(employee) + [employee["_id"]]
    prior = await db.performance_reviews.find({"$and": [tenant_query(tenant_of(user)), {
        "employee_id": {"$in": aliases}, "cycle_year": body["cycle_year"]}]}).to_list(None)
    if any(row.get("cycle_type") == body["cycle_type"] or row.get("cycle_type") not in {"Mid_Year", "Year_End"} for row in prior):
        fail("An existing or ambiguous historical review requires HR reconciliation for this period", 409)
    row = {"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "employee_id": employee_key(employee),
        "cycle_id": cycle["id"], "cycle_type": body["cycle_type"], "cycle_year": body["cycle_year"],
        "workflow_version": 1, "status": "Draft", "section_a_kpis": [],
        "self_due_on": cycle["self_due_on"], "manager_due_on": cycle["manager_due_on"], "review_due_on": cycle["ends_on"],
        "scoring_policy": deepcopy(cycle["scoring_policy"]), "created_at": now(), "updated_at": now()}
    await audit(db, user, "performance.review.created", row, employee_id=employee_key(employee), cycle_id=cycle["id"])
    await db.performance_reviews.insert_one(row)
    await notify(db, row, "created")
    return projection(row, user, employee)


async def record(db, user, reference):
    row = await find_linked_record(db.performance_reviews, reference, user)
    employee = await employee_access(db, user, row.get("employee_id"))
    return row, employee


async def save(db, user, row, update, event):
    await audit(db, user, event, row, employee_id=row["employee_id"],
                before={key: deepcopy(row.get(key)) for key in update}, after=deepcopy(update))
    await db.performance_reviews.update_one({"_id": row["_id"]}, {"$set": {**update, "updated_at": now()}})
    row.update(update)
    fingerprint = hashlib.sha256(json.dumps(update, sort_keys=True, default=str).encode()).hexdigest()[:24]
    await notify(db, row, event + ":" + fingerprint)
    return row


async def goals(db, user, reference, body):
    row, employee = await record(db, user, reference)
    if row.get("workflow_version") != 1 or row.get("status") not in {"Draft", "Self_Draft", "Self_Submitted"}:
        fail("Goals are locked for this review stage", 409)
    actor = body.get("action")
    if not isinstance(actor, str): fail("Choose a valid goal action")
    items = deepcopy(row.get("section_a_kpis") or [])
    if actor == "acknowledge":
        personal_grant(user, "M05", write=True)
        if set(body) != {"action"}: fail("Goal acknowledgement cannot alter targets")
        if employee_key(employee) != user.get("employee_id"): fail("Only the employee may acknowledge their goals", 403)
        if not 3 <= len(items) <= 5: fail("Agree three to five KPIs before sign-off", 409)
        if not row.get("goals_acknowledged_at"):
            await save(db, user, row, {"goals_acknowledged_at": now(), "goals_acknowledged_by": user["id"]}, "performance.goals.acknowledged")
        return projection(row, user, employee)
    if actor == "assign":
        if row.get("status") == "Self_Submitted": fail("Submitted assessment targets are locked", 409)
        if row.get("goals_acknowledged_at"): fail("Signed-off targets require an approved amendment process", 409)
        await employee_access(db, user, row["employee_id"], write=True)
        if employee_key(employee) == user.get("employee_id"): fail("Goals require another authorized manager or HR", 403)
        if set(body) - {"action", "objective", "metric", "target", "due_on"}: fail("Unknown goal fields")
        if len(items) >= 5: fail("A review supports up to five agreed KPIs")
        try: due = date.fromisoformat(body["due_on"])
        except (KeyError, TypeError, ValueError): fail("A valid goal due date is required")
        if any(item.get("objective", "").strip().casefold() == text(body.get("objective"), "objective", 500).casefold() for item in items):
            fail("This goal is already assigned", 409)
        items.append({"id": str(uuid.uuid4()), "objective": text(body.get("objective"), "objective", 500),
            "metric": text(body.get("metric"), "measurement", 500), "target": text(body.get("target"), "target", 500),
            "due_on": due.isoformat(), "progress": 0, "status": "Assigned", "assigned_by": user["id"]})
    elif actor in {"progress", "review"}:
        if set(body) - {"action", "goal_id", "progress", "evidence"}: fail("Goal targets and owners cannot be overwritten")
        item = next((item for item in items if item.get("id") == body.get("goal_id")), None)
        if not item: fail("Goal not found", 404)
        if actor == "progress":
            personal_grant(user, "M05", write=True)
            if employee_key(employee) != user.get("employee_id"): fail("Only the employee can report their goal progress", 403)
            value = body.get("progress")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                fail("Progress must be between zero and 100")
            if item.get("status") == "Completed": fail("Reviewed goals are immutable", 409)
            item.update(progress=value, evidence=text(body.get("evidence"), "progress evidence"), status="Pending_Review" if value == 100 else "In_Progress")
        else:
            await employee_access(db, user, row["employee_id"], write=True)
            if employee_key(employee) == user.get("employee_id"): fail("Employees cannot approve their own goals", 403)
            if item.get("progress") != 100: fail("Completion requires reported progress and evidence", 409)
            item.update(status="Completed", reviewed_by=user["id"], reviewed_at=now())
    else: fail("Choose a valid goal action")
    await save(db, user, row, {"section_a_kpis": items}, "performance.goal." + actor)
    return projection(row, user, employee)


async def assess(db, user, reference, stage, body):
    row, employee = await record(db, user, reference)
    if stage == "legacy-release":
        require_hr(user)
        if employee_key(employee) == user.get("employee_id"): fail("HR cannot release their own review", 403)
        if row.get("workflow_version") == 1 or row.get("status") not in {"Completed", "Imported"}:
            fail("Only completed or imported historical reviews are eligible", 409)
        if set(body) != {"approval_reference"}: fail("Historical release requires an approval reference, never score changes")
        score(row.get("overall_score"))
        reference = text(body.get("approval_reference"), "historical publication approval reference", 300)
        if not released(row):
            await save(db, user, row, {"released_at": now(), "released_by": user["id"],
                "publication_approval_reference": reference}, "performance.historical.released")
        return projection(row, user, employee)
    if row.get("workflow_version") != 1: fail("Historical reviews require an approved reconciliation; scores are preserved", 409)
    status, own = row.get("status"), employee_key(employee) == user.get("employee_id")
    if stage == "self":
        personal_grant(user, "M05", write=True)
        if not own: fail("Only the employee can submit their self-assessment", 403)
        if status not in {"Draft", "Self_Draft"}: fail("Self-assessment has already been submitted", 409)
        if set(body) - {"summary", "achievements", "support_needed", "submit"}: fail("Self-assessments cannot contain manager or score fields")
        if "submit" in body and not isinstance(body["submit"], bool): fail("Submission must be a boolean")
        if body.get("submit") and not 3 <= len(row.get("section_a_kpis") or []) <= 5:
            fail("Agree three to five measurable KPIs before submitting the assessment", 409)
        if body.get("submit") and not row.get("goals_acknowledged_at"):
            fail("Employee acknowledgement of agreed goals is required", 409)
        assessment = {"summary": text(body.get("summary"), "self-assessment"),
                      "achievements": text(body.get("achievements"), "achievements"),
                      "support_needed": text(body.get("support_needed"), "support needs"), "actor_id": user["id"], "saved_at": now()}
        update = {"self_assessment": assessment, "status": "Self_Submitted" if body.get("submit") is True else "Self_Draft"}
    elif stage == "manager":
        await employee_access(db, user, row["employee_id"], write=True)
        if own or not is_direct_report(employee, user): fail("Only the employee's current reporting manager can assess them", 403)
        if status != "Self_Submitted": fail("The employee self-assessment must be submitted first", 409)
        if set(body) - {"summary", "kpi_scores"}: fail("Managers cannot set HR scores, signatures or final ratings")
        inputs = body.get("kpi_scores")
        agreed = row.get("section_a_kpis") or []
        if not isinstance(inputs, list) or not 3 <= len(inputs) <= 5 or len(inputs) != len(agreed):
            fail("Assess all three to five agreed KPIs")
        if any(not isinstance(item, dict) or not isinstance(item.get("goal_id"), str) for item in inputs):
            fail("KPI assessments require valid goal identifiers")
        if {item.get("goal_id") for item in inputs if isinstance(item, dict)} != {item["id"] for item in agreed} or len({item.get("goal_id") for item in inputs}) != len(inputs):
            fail("KPI assessments must match the agreed goals exactly")
        assessments = []
        for item in inputs:
            if set(item) != {"goal_id", "score", "evidence"}: fail("Each KPI requires a goal, score and evidence")
            assessments.append({"goal_id": item["goal_id"], "score": score(item["score"]), "evidence": text(item["evidence"], "KPI evidence")})
        update = {"manager_assessment": {"summary": text(body.get("summary"), "manager assessment"),
            "kpi_scores": assessments, "actor_id": user["id"], "submitted_at": now()},
            "section_a_score": sum(item["score"] for item in assessments) / len(assessments), "status": "Manager_Submitted"}
    elif stage == "hr":
        require_hr(user)
        if own: fail("HR cannot approve their own review", 403)
        if status != "Manager_Submitted": fail("Manager assessment must be submitted first", 409)
        if set(body) - {"section_b_score", "section_c_score", "evidence_reference", "summary"}: fail("Final scores are calculated, never supplied")
        policy = row.get("scoring_policy") or {}
        preset = POLICIES.get(policy.get("source"))
        if not preset or not policy.get("approval_reference") or not policy.get("approved_by") or policy.get("weights") != preset["weights"] or policy.get("section_c") != preset["section_c"]:
            fail("An explicitly approved scoring policy snapshot is required", 409)
        a, b, c = score(row.get("section_a_score")), score(body.get("section_b_score")), score(body.get("section_c_score"))
        weights = policy["weights"]
        overall = round(sum(value * weight / 100 for value, weight in zip((a, b, c), weights)), 1)
        from routes.performance import get_rating
        update = {"section_b_score": b, "section_c_score": c, "overall_score": overall, "rating": get_rating(overall),
            "hr_summary": text(body.get("summary"), "HR review summary"), "hr_evidence_reference": text(body.get("evidence_reference"), "score-source evidence reference", 500),
            "hr_reviewed_by": user["id"], "hr_reviewed_at": now(), "status": "HR_Reviewed"}
    elif stage == "release":
        require_hr(user)
        if own: fail("HR cannot release their own review", 403)
        if body: fail("Release does not accept score changes")
        if status != "HR_Reviewed": fail("HR review must be complete before releasing scores", 409)
        update = {"status": "Completed", "released_at": now(), "released_by": user["id"]}
    else: fail("Unknown assessment stage")
    await save(db, user, row, update, "performance.assessment." + stage)
    if stage == "release":
        try:
            from utils.email_triggers import fire_and_forget
            await fire_and_forget(db, "performance.review_complete", employee_id=employee_key(employee), extra={
                "score": row.get("overall_score"), "rating": row.get("rating"),
                "cycle_year": row.get("cycle_year"), "cycle_type": row.get("cycle_type")})
        except Exception:
            pass  # Preserve existing best-effort delivery; in-app events remain durable.
    return projection(row, user, employee)
