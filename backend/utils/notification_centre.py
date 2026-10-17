"""Recipient-scoped inbox projections and per-account receipts for legacy events."""
from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import quote

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from utils.employee_integrity import (employee_key, find_employee, resolve_user_employee,
                                      tenant_of, tenant_query, user_employee_aliases)
from utils.employee_access import authorize_employee, find_linked_record, personal_grant
from utils.solver_access import own_solver, solver_aliases, authorize_solver
from utils.staff_views import token, restricted
from utils.access_matrix import get_module_access

CATEGORIES = ("Benefits", "Leave", "Approvals", "Onboarding", "Training", "Announcements", "Performance", "Recognition", "Policies", "System")
MODULES = {"Benefits": "M01", "Leave": "M18", "Approvals": "M18", "Onboarding": "M04", "Training": "M08", "Performance": "M05", "Recognition": "M11", "Policies": "M13"}
PREVIEWS = {
    "Benefits": ("Benefits update", "There is an update about a benefit membership request."),
    "Leave": ("Leave update", "There is an update about a leave request."),
    "Approvals": ("Approval required", "A request needs an authorized approver's attention."),
    "Onboarding": ("Onboarding update", "There is an update about onboarding or probation."),
    "Training": ("Training update", "There is an update about learning or training."),
    "Announcements": ("HR announcement", "Your HR team has shared an update."),
    "Performance": ("Performance update", "There is an update about a review or assigned action."),
    "Recognition": ("Recognition update", "There is a recognition update."),
    "Policies": ("Policy update", "There is an update about a policy or acknowledgement."),
    "System": ("System notification", "There is an update in Solvit People."),
}


def category_of(row):
    value = token(row.get("category"))
    aliases = {"benefits": "Benefits", "benefit": "Benefits", "leave": "Leave", "approval": "Approvals", "approvals": "Approvals", "onboarding": "Onboarding",
               "probation": "Onboarding", "training": "Training", "learning": "Training", "lnd": "Training",
               "announcement": "Announcements", "announcements": "Announcements", "hrannouncement": "Announcements",
               "performance": "Performance", "recognition": "Recognition", "policies": "Policies", "policy": "Policies"}
    if value in aliases:
        return aliases[value]
    rule = str(row.get("rule_id") or "").upper()
    for prefixes, category in ((('AR-LV', 'REM-LEAVE'), 'Leave'), (('AR-OB', 'AR-PR', 'REM-ONBOARD', 'REM-PROB'), 'Onboarding'),
                               (('AR-PF', 'REM-PERF'), 'Performance'), (('REM-RECOG', 'AR-RK'), 'Recognition')):
        if rule.startswith(prefixes):
            return category
    return "System"


def date_value(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def storage_key(row):
    return str(row.get("_id") or row.get("id"))


async def inbox_user(db, user):
    user = dict(user)
    if user.get("role") == "solver":
        solver = await own_solver(db, user)
        if token(solver.get("lifecycle_state") or solver.get("status")) in {"inactive", "suspended", "exited", "deactivated", "terminated"}:
            raise HTTPException(403, "Notification access is unavailable for this account status")
        user["solver_reference_ids"] = solver_aliases(solver)
        user["notification_active_solver"] = token(solver.get("lifecycle_state") or solver.get("status")) == "active"
    else:
        employee = await resolve_user_employee(db, user)
        if employee:
            status = token(employee.get("lifecycle_state") or employee.get("employment_status") or employee.get("status"))
            if status not in {"onboarding", "probation", "active", "onleave", "pip", "realignment", "exiting"}:
                raise HTTPException(403, "Notification access is unavailable for this employee status")
            if restricted(employee.get("board_only")) and user.get("role") not in ("board", "it_admin"):
                raise HTTPException(403, "Notification access is unavailable for this employee classification")
            user["employee_id"] = employee_key(employee)
            user["employee_reference_ids"] = [employee_key(employee), str(employee["_id"]), employee["_id"]]
            user["notification_active_fte"] = status == "active" and token(employee.get("employment_type")) in {"", "fulltime", "fte"}
        elif user.get("role") not in {"hr_admin", "hr_manager", "it_admin", "finance", "executive", "board"}:
            raise HTTPException(409, "This account needs an employee link from HR")
        else:
            user["employee_id"] = None
            user["employee_reference_ids"] = []
    return user


async def authorize_recipient(db, user, row):
    if tenant_of(row) != tenant_of(user):
        raise HTTPException(403, "Notification belongs to another account")
    refs = [user["id"], *(user_employee_aliases(user) if user.get("employee_id") else []), *user.get("solver_reference_ids", [])]
    addressed = False
    for field in ("recipient_id", "user_id"):
        value = row.get(field)
        if value is not None and value != "":
            addressed = True
            allowed = [user["id"]] if field == "user_id" else refs
            if value not in allowed:
                raise HTTPException(403, "Notification belongs to another account")
            # recipient_id historically means either user or employee. An alias
            # collision across collections must not authorize both identities.
            if field == "recipient_id" and row.get("recipient_type") not in ("employee", "account", "solver"):
                employee = await find_employee(db, value, tenant_of(user))
                if employee and employee_key(employee) != user.get("employee_id"):
                    raise HTTPException(403, "Notification recipient needs an integrity review")
                if ObjectId.is_valid(str(value)):
                    owner = await db.users.find_one({"$and": [tenant_query(tenant_of(user)), {"_id": ObjectId(str(value))}]})
                    if owner and str(owner["_id"]) != user["id"]:
                        raise HTTPException(403, "Notification recipient needs an integrity review")
            if field == "recipient_id" and row.get("recipient_type") == "account" and str(value) != user["id"]:
                raise HTTPException(403, "Notification belongs to another account")
            if field == "recipient_id" and row.get("recipient_type") == "employee" and value not in user_employee_aliases(user):
                raise HTTPException(403, "Notification belongs to another account")
            if field == "recipient_id" and row.get("recipient_type") == "solver" and value not in user.get("solver_reference_ids", []):
                raise HTTPException(403, "Notification belongs to another account")
    if not addressed:
        role = row.get("recipient_role")
        group = (role == "all_active_fte" and user.get("notification_active_fte")) or (role == "all_active_solvers" and user.get("notification_active_solver"))
        if role != user.get("role") and not group:
            raise HTTPException(403, "Notification belongs to another role")
    data = row.get("data") or {}
    if not isinstance(data, dict):
        raise HTTPException(403, "Notification routing needs an integrity review")
    module = MODULES.get(category_of(row))
    if user.get("role") == "solver" and category_of(row) == "Performance":
        module = "M02"  # Solver ratings belong to M02, not FTE reviews (M05).
    if module == "M13":
        if not get_module_access(module, user.get("role")):
            raise HTTPException(403, "No access to this notification module")
    elif module:
        if user.get("role") == "solver":
            if not get_module_access(module, "solver"):
                raise HTTPException(403, "No access to this notification module")
        else:
            personal_grant(user, module)
    subjects = [ref for ref in (row.get("employee_id"), data.get("employee_id"),
                               row.get("entity_id") if row.get("entity_type") == "employee" else None) if ref]
    resolved = []
    for ref in subjects:
        module = MODULES.get(category_of(row), "M04")
        if module == "M13" and not get_module_access(module, user.get("role")):
            raise HTTPException(403, "No access to this notification module")
        employee = await authorize_employee(db, user, ref, "M01" if module == "M13" else module)
        resolved.append(employee_key(employee))
    if len(set(resolved)) > 1:
        raise HTTPException(403, "Notification routing needs an integrity review")
    for ref in (row.get("solver_id"), data.get("solver_id")):
        if ref:
            await authorize_solver(db, user, ref)


async def related_link(db, user, row, category):
    data = row.get("data") or {}
    if not isinstance(data, dict):
        return None, None
    try:
        if data.get('solver_assessment_id'):
            from utils.solver_assessments import load
            await load(db, user, data['solver_assessment_id'])
            return '/solver-assessments?assessment=' + quote(data['solver_assessment_id'], safe=''), None
        if data.get('solver_workflow') and data.get('solver_id'):
            await authorize_solver(db, user, data['solver_id'])
            return '/solvers', None
        if category == "Performance" and data.get("performance_review_id"):
            from utils.performance_workflows import record
            review, employee = await record(db, user, data["performance_review_id"])
            if data.get("employee_id") not in [employee_key(employee), str(employee["_id"]), employee["_id"]]:
                return None, None
            return "/performance?review=" + quote(str(review.get("id") or review["_id"]), safe=""), None
        if data.get("lifecycle_employee_id"):
            from utils.lifecycle_workflows import task_access, query
            employee = await find_employee(db, data["lifecycle_employee_id"], tenant_of(user))
            if not employee:
                return None, None
            for collection in (db.onboarding_tasks, db.tasks):
                for task in await collection.find(query(employee)).to_list(None):
                    try:
                        await task_access(db, user, task)
                        return "/onboarding", None
                    except HTTPException:
                        continue
            return None, None
        if category == "Benefits":
            record = await find_linked_record(db.benefit_requests, str(data.get("benefit_request_id") or ""), user)
            employee = await authorize_employee(db, user, record.get("employee_id"), "M01")
            if user.get("role") not in {"hr_admin", "hr_manager"} and employee_key(employee) != user.get("employee_id"):
                return None, None
            return "/benefits", None
        if category in ("Leave", "Approvals", "Training"):
            field = "training_request_id" if category == "Training" else "leave_request_id"
            reference = data.get(field) or row.get(field)
            if not reference:
                return None, None
            collection = db.training_requests if category == "Training" else db.leave_requests
            record = await find_linked_record(collection, str(reference), user)
            module = "M08" if category == "Training" else "M18"
            employee = await authorize_employee(db, user, record.get("employee_id"), module)
            supplied = data.get("employee_id") or row.get("employee_id")
            if supplied:
                chosen = await find_employee(db, supplied, tenant_of(user))
                if not chosen or chosen["_id"] != employee["_id"]:
                    return None, None
            path = ("/lnd?training=" if category == "Training" else "/leave?request=") + quote(str(record.get("id") or storage_key(record)) if category == "Training" else storage_key(record), safe="")
            if category != "Training" and employee_key(employee) != user.get("employee_id"):
                path += "&view=team"
            action = None
            if category != "Training":
                from utils.leave_workflow import stage_for
                stage = await stage_for(db, user, record)
                if stage:
                    action = {"kind": "leave_review", "record_id": storage_key(record), "stage": stage}
            return path, action
        subject = data.get("employee_id") or row.get("employee_id")
        if subject and category in ("Onboarding", "Performance", "Recognition"):
            employee = await authorize_employee(db, user, subject, "M01")
            return "/employees/" + quote(employee_key(employee), safe=""), None
    except HTTPException:
        # A deleted, ambiguous or inaccessible target must never become a link.
        pass
    return None, None


async def list_inbox(db, user, *, category=None, kind=None, read_status="all", offset=0, limit=50, personal_only=False):
    user = await inbox_user(db, user)
    refs = [user["id"], *(user_employee_aliases(user) if user.get("employee_id") else []), *user.get("solver_reference_ids", [])]
    roles = [user.get("role")]
    if user.get("notification_active_fte"):
        roles.append("all_active_fte")
    if user.get("notification_active_solver"):
        roles.append("all_active_solvers")
    rows = await db.notifications.find({"$and": [tenant_query(tenant_of(user)), {"$or": [
        {"recipient_id": {"$in": refs}}, {"user_id": user["id"]}, {"recipient_role": {"$in": roles}}
    ]}]}).to_list(None)
    receipts = await db.notification_receipts.find({"$and": [tenant_query(tenant_of(user)), {"user_id": user["id"]}]}).to_list(None)
    reads = {row.get("notification_id") for row in receipts if row.get("read_at")}
    visible = []
    for row in rows:
        if personal_only:
            data = row.get("data") or {}
            subjects = [ref for ref in (row.get("employee_id"), data.get("employee_id") if isinstance(data, dict) else None) if ref]
            if any(ref not in user_employee_aliases(user) for ref in subjects):
                continue
        try:
            await authorize_recipient(db, user, row)
        except HTTPException as error:
            if error.status_code in (403, 404):
                continue
            raise
        category_value = category_of(row)
        link, action = await related_link(db, user, row, category_value)
        title, message = PREVIEWS[category_value]
        kind_value = "Approvals" if action else "Action required" if category_value in ("Onboarding", "Training", "Policies") else "Updates"
        created = date_value(row.get("created_at"))
        visible.append({"id": storage_key(row), "title": title, "message": message,
                        "category": category_value, "kind": kind_value, "sender": "System" if row.get("rule_id") else "Solvit People",
                        "created_at": created.isoformat() if created else None, "link": link, "action": action,
                        # Legacy flags remain a baseline; new reads never change
                        # that shared flag, including for role broadcasts.
                        "is_read": storage_key(row) in reads or row.get("is_read") is True or token(row.get("is_read")) in {"true", "1", "yes"} or date_value(row.get("read_at")) is not None})
    visible.sort(key=lambda row: (row["created_at"] or "", row["id"]), reverse=True)
    unread = sum(not row["is_read"] for row in visible)
    filtered = [row for row in visible if (not category or row["category"] == category)
                and (not kind or row["kind"] == kind)
                and (read_status == "all" or row["is_read"] == (read_status == "read"))]
    return {"items": filtered[offset:offset + limit], "unread_count": unread, "total": len(visible),
            "filtered_total": len(filtered), "offset": offset, "limit": limit,
            "categories": [item for item in CATEGORIES if any(row["category"] == item for row in visible)]}


async def read_notification(db, user, reference):
    user = await inbox_user(db, user)
    current = await find_linked_record(db.notifications, reference, user)
    await authorize_recipient(db, user, current)
    key = hashlib.sha256(json.dumps([tenant_of(user), user["id"], storage_key(current)]).encode()).hexdigest()
    fields = {"tenant_id": tenant_of(user), "user_id": user["id"], "notification_id": storage_key(current),
              "read_at": datetime.now(timezone.utc).isoformat()}
    try:
        await db.notification_receipts.update_one({"_id": key}, {"$setOnInsert": fields}, upsert=True)
    except DuplicateKeyError:
        receipt = await db.notification_receipts.find_one({"_id": key})
        if not receipt or any(receipt.get(field) != fields[field] for field in ("tenant_id", "user_id", "notification_id")):
            raise HTTPException(409, "Notification receipt needs an integrity review")
    return {"message": "Marked as read", "is_read": True}
