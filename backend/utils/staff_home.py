"""Read-only personal home projection. Never accepts a client employee identity."""
from datetime import datetime, timezone
from urllib.parse import quote
import math

from fastapi import HTTPException

from utils.access_matrix import get_module_access
from utils.employee_access import personal_grant, reference_ids
from utils.employee_integrity import employee_key, resolve_user_employee, tenant_of, tenant_query
from utils.form_access import authorize_signature
from utils.task_access import authorize_task
from utils.notification_centre import list_inbox


def project(record, fields):
    # Keep malformed legacy nested values out of the public summary DTO.
    return {field: value for field in fields
            if isinstance((value := record.get(field)), (str, int, float, bool))
            and (not isinstance(value, float) or math.isfinite(value))}


def identifier(record):
    return str(record.get("id") or record.get("_id") or "")


def can_personal(user, module):
    try:
        personal_grant(user, module)
        return True
    except HTTPException as error:
        if error.status_code != 403:
            raise
        return False


async def staff_home_data(db, user, balance_loader):
    if user.get("role") == "solver":
        raise HTTPException(403, "Use the Solver dashboard")
    employee = await resolve_user_employee(db, user)
    if not employee:
        raise HTTPException(409, "This account needs an employee link from HR")
    refs = reference_ids(employee)
    refs.append(employee["_id"])  # Historical native ObjectId foreign keys.
    user = {**user, "employee_id": employee_key(employee), "employee_reference_ids": refs}
    tenant = tenant_query(tenant_of(user))
    own = {"$and": [tenant, {"employee_id": {"$in": refs}}]}
    snapshot = {"employee": {"id": employee_key(employee), **project(employee, ("full_name", "role_title", "department"))},
                "leave_balance": None, "pending_leave": None, "tasks": [], "notifications": [],
                "reviews": None, "recognitions": None, "quick_links": [],
                "as_of": datetime.now(timezone.utc).isoformat()}

    def link(label, path):
        snapshot["quick_links"].append({"label": label, "path": path})

    if can_personal(user, "M01"):
        link("My Profile", "/employees/" + quote(employee_key(employee), safe=""))
    if can_personal(user, "M18"):
        link("Leave", "/leave")
        # Missing/invalid start date must not turn into invented full-year accrual.
        try:
            start = datetime.fromisoformat(employee.get("start_date") or "").date()
        except (TypeError, ValueError):
            start = None
        if start and start <= datetime.now(timezone.utc).date():
            # Existing balance endpoint is Solvit-specific; fail empty for other tenants.
            if tenant_of(user) == "solvit":
                balance = await balance_loader(employee_key(employee))
                snapshot["leave_balance"] = project(balance, ("annual_days_remaining", "annual_available_to_request", "sick_days_remaining", "accrued_annual"))
                if "annual_available_to_request" in balance:
                    snapshot["leave_balance"]["annual_available_to_request"] = balance["annual_available_to_request"]
        rows = await db.leave_requests.find({"$and": [own, {"status": {"$in": ["Pending_Manager", "Pending_HR", "Discussion_Requested", "Pending", "Submitted"]}}]}).sort("created_at", -1).to_list(None)
        snapshot["pending_leave"] = [{"id": identifier(row), **project(row, ("leave_type", "start_date", "end_date", "working_days", "status"))} for row in rows]

    if get_module_access("M13", user.get("role")):
        link("Documents & policies", "/policies")
    if can_personal(user, "M08"):
        link("Learning & Development", "/lnd")

    task_access = get_module_access("M17", user.get("role"))
    if task_access:
        link("My Tasks", "/my-tasks")
        forms = await db.form_submissions.find({"$and": [tenant, {"subject_employee_id": {"$in": refs}, "status": "InProgress"}]}).sort("created_at", -1).to_list(None)
        for row in forms:
            try:
                await authorize_signature(db, user, row.get("next_required_role"), row.get("subject_employee_id"), row.get("started_by"))
            except HTTPException as error:
                if error.status_code == 403:
                    continue
                raise
            snapshot["tasks"].append({"id": identifier(row), "kind": "form", "path": "/my-tasks",
                                      **project(row, ("form_title", "form_id", "due_date", "status"))})

    if can_personal(user, "M04"):
        if not task_access:
            link("My Tasks", "/my-tasks")
        rows = await db.tasks.find({"$and": [tenant, {"status": {"$in": ["Pending", "In_Progress", "Open"]}}, {
            "$or": [{"assigned_to": {"$in": [user["id"], *refs]}},
                    {"assigned_to_user_id": user["id"]},
                    {"employee_id": {"$in": refs}, "assigned_role": user.get("role")},
                    {"entity_type": "employee", "entity_id": {"$in": refs}, "assigned_role": user.get("role")}]
        }]}).sort("due_date", 1).to_list(None)
        for row in rows:
            subject = row.get("employee_id") or row.get("entity_id")
            if row.get("solver_id") or row.get("entity_type") == "solver" or (subject and subject not in refs):
                continue
            if row.get("assigned_to") and row["assigned_to"] not in [user["id"], *refs]:
                continue
            check = dict(row)
            if check.get("assigned_to_user_id"):
                if check["assigned_to_user_id"] != user["id"]:
                    continue
                if check.get("assigned_to") and check["assigned_to"] not in [user["id"], *refs]:
                    continue
                check["assigned_to"] = user["id"]
            try:
                await authorize_task(db, user, check)
            except HTTPException as error:
                if error.status_code == 403:
                    continue
                raise
            snapshot["tasks"].append({"id": identifier(row), "kind": "task", "path": "/my-tasks",
                                      **project(row, ("title", "due_date", "status"))})

    inbox = await list_inbox(db, user, limit=5, personal_only=True)
    snapshot["notifications"] = inbox["items"]
    snapshot["unread_notifications"] = inbox["unread_count"]
    link("Notifications", "/notifications")

    if can_personal(user, "M05"):
        rows = await db.performance_reviews.find(own).sort("created_at", -1).to_list(30)
        snapshot["reviews"] = [{"id": identifier(row), **project(row, ("overall_score", "rating", "section_a_score", "section_b_score", "section_c_score", "cycle_type", "cycle_year", "status"))} for row in rows]
    if can_personal(user, "M11"):
        rows = await db.recognitions.find({"$and": [tenant, {"$or": [{"employee_id": {"$in": refs}}, {"nominee_id": {"$in": refs}}]}]}).sort("created_at", -1).to_list(30)
        snapshot["recognitions"] = [{"id": identifier(row), **project(row, ("recognition_type", "specific_behaviour", "created_at")),
                                     "is_anonymous": bool(row.get("is_anonymous"))} for row in rows]
    return snapshot
