"""Employee lifecycle checklists; no identity creation or implicit account shutdown."""
from datetime import date, datetime, time, timedelta, timezone
import uuid

from fastapi import HTTPException
from utils.employee_access import authorize_employee, personal_grant, reference_ids
from utils.employee_integrity import (employee_key, find_employee, is_direct_report,
                                      tenant_of, tenant_query, validate_manager_departure)
from utils.security import revoke_all_user_refresh_tokens

HR = {"hr_admin", "hr_manager"}


def now():
    return datetime.now(timezone.utc).isoformat()


def query(employee, **fields):
    return {"$and": [tenant_query(tenant_of(employee)), {
        "entity_id": {"$in": reference_ids(employee) + [employee["_id"]]}, **fields}]}


def require_hr(user):
    if user.get("role") not in HR:
        raise HTTPException(403, "HR authorization required")
    personal_grant(user, "M04", write=True)


async def task_access(db, user, task, write=False):
    employee = await find_employee(db, task.get("entity_id"), tenant_of(user))
    if not employee:
        raise HTTPException(409, "Checklist employee needs an integrity review")
    from utils.staff_views import restricted
    owner = employee_key(employee) == user.get("employee_id")
    if restricted(employee.get("board_only")) and not owner and user.get("role") not in {"board", "it_admin"}:
        raise HTTPException(403, "Restricted employee record")
    if user.get("role") in HR:
        personal_grant(user, "M04", write=write)
        if task.get("task_type") == "exit_workflow":
            personal_grant(user, "M07", write=write)
        return employee
    assigned = task.get("assigned_role")
    permitted = ((assigned == "employee" and owner) or
                 (assigned == "line_manager" and not owner and is_direct_report(employee, user)) or
                 (assigned in {"it_admin", "finance"} and user.get("role") == assigned))
    if write:
        if not permitted or assigned == "system":
            raise HTTPException(403, "Only the responsible party can complete this checklist item")
    elif not (owner or permitted or is_direct_report(employee, user)):
        raise HTTPException(403, "No access to this checklist")
    # Assigned IT/Finance clearance grants task-only access, never employee HR data.
    if user.get("role") not in {"it_admin", "finance"}:
        await authorize_employee(db, user, employee_key(employee), "M04", write=write)
    return employee


def project(task, can_complete=False):
    fields = ("title", "task_key", "assigned_role", "status", "due_date", "completed_at", "document_id")
    return {"id": str(task.get("id") or task["_id"]),
            **{key: task.get(key) for key in fields}, "can_complete": can_complete}


async def audit(db, user, event, employee, **metadata):
    await db.audit_logs.insert_one({"tenant_id": tenant_of(user), "event": event,
        "entity_id": employee_key(employee), "actor_id": user["id"],
        "timestamp": now(), "metadata": metadata})


async def notify(db, employee, kind):
    recipients = [("employee", employee_key(employee)), ("role", "hr_admin"), ("role", "hr_manager")]
    manager = await find_employee(db, employee.get("line_manager_id"), tenant_of(employee))
    if manager:
        recipients.append(("employee", employee_key(manager)))
    recipients += [("role", "it_admin"), ("role", "finance")]
    for recipient_type, recipient in recipients:
        key = f"lifecycle:{tenant_of(employee)}:{employee['_id']}:{kind}:{recipient_type}:{recipient}"
        await db.notifications.update_one({"_id": key}, {"$setOnInsert": {
            "id": key, "tenant_id": tenant_of(employee), "category": "System",
            **({"recipient_role": recipient} if recipient_type == "role" else
               {"recipient_type": "employee", "recipient_id": recipient}),
            "data": {"lifecycle_employee_id": employee_key(employee)},
            "created_at": now(), "is_read": False}}, upsert=True)


async def create_exit_tasks(db, employee):
    """Reuse the seven existing exit tasks and Form 23 clearance fields; retry-safe."""
    from automation.engine import EXIT_WORKFLOW_TASKS
    from routes.forms_data import EXTRA_SCHEMAS
    # Keep legacy ET keys and collections so existing form outcomes still resolve.
    templates = [{**row, "day_offset": row["days_due"],
                  "assigned_role": "hr_admin" if row["assigned_role"] == "system" else row["assigned_role"]}
                 for row in EXIT_WORKFLOW_TASKS]
    templates.append({"task_key": "HANDOVER", "title": "Verify completed handover with employee",
                      "assigned_role": "line_manager", "day_offset": 0})
    form = EXTRA_SCHEMAS["form-23"]
    for section in form["sections"]:
        role = {"it": "it_admin", "finance": "finance"}.get(section["id"], "hr_admin")
        for field in section["fields"]:
            templates.append({"task_key": "clearance:" + field["id"], "title": field["label"],
                              "assigned_role": role, "day_offset": 0})
    existing = await db.tasks.find(query(employee, task_type="exit_workflow")).to_list(None)
    keys = {row.get("task_key") for row in existing}
    due = employee.get("last_working_day") or employee.get("exit_date")
    for template in templates:
        if template["task_key"] in keys:
            continue
        await db.tasks.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(employee),
            "entity_id": employee_key(employee), "entity_type": "employee", "task_type": "exit_workflow",
            "task_key": template["task_key"], "title": template["title"],
            "assigned_role": template["assigned_role"], "status": "Pending",
            "due_date": due, "created_at": now()})


async def finalize_exit(db, user, employee):
    require_hr(user)
    await task_access(db, user, {"entity_id": employee_key(employee), "task_type": "exit_workflow"}, write=True)
    if employee_key(employee) == user.get("employee_id"):
        raise HTTPException(403, "Employees cannot approve their own exit")
    if employee.get("lifecycle_state") == "Exited" and employee.get("offboarding_completed_at"):
        return
    if not employee.get("offboarding_started_at") or employee.get("lifecycle_state") != "Exiting":
        raise HTTPException(409, "An HR-initiated offboarding workflow is required")
    try:
        last_day = date.fromisoformat(employee["last_working_day"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, "HR must confirm the last working day")
    cutoff = datetime.combine(last_day, time(17), timezone(timedelta(hours=3)))
    if datetime.now(timezone.utc) < cutoff:
        raise HTTPException(409, "Access cannot be revoked before 17:00 EAT on the last working day")
    await create_exit_tasks(db, employee)
    tasks = await db.tasks.find(query(employee, task_type="exit_workflow")).to_list(None)
    if not tasks or any(task.get("status") != "Completed" for task in tasks):
        raise HTTPException(409, "All clearance responsibilities must be completed first")
    await validate_manager_departure(db, employee, "Exited")
    await deactivate_account(db, user, employee)
    await db.employees.update_one({"_id": employee["_id"]}, {"$set": {
        "lifecycle_state": "Exited", "offboarding_completed_at": now(), "updated_at": now()}})
    await audit(db, user, "offboarding.completed", employee)


async def deactivate_account(db, user, employee):
    require_hr(user)
    await task_access(db, user, {"entity_id": employee_key(employee), "task_type": "exit_workflow"}, write=True)
    if employee_key(employee) == user.get("employee_id"):
        raise HTTPException(403, "Employees cannot authorize their own deactivation")
    if not employee.get("offboarding_started_at"):
        raise HTTPException(409, "HR-initiated offboarding is required")
    cutoff = datetime.combine(date.fromisoformat(employee["last_working_day"]), time(17), timezone(timedelta(hours=3)))
    if datetime.now(timezone.utc) < cutoff:
        raise HTTPException(409, "Access cannot be revoked before 17:00 EAT on the last working day")
    if employee.get("offboarding_access_revoked_at"):
        return
    accounts = await db.users.find({"$and": [tenant_query(tenant_of(user)), {
        "employee_id": {"$in": reference_ids(employee) + [employee["_id"]]}}]}).to_list(3)
    if len(accounts) != 1 or accounts[0].get("account_type") in {"system", "solver", "board"}:
        raise HTTPException(409, "Account linkage requires HR integrity review before deactivation")
    if str(accounts[0]["_id"]) == user["id"]:
        raise HTTPException(403, "HR cannot deactivate their own account through offboarding")
    await audit(db, user, "offboarding.deactivation.authorized", employee,
                last_working_day=employee["last_working_day"], account_id=str(accounts[0]["_id"]))
    # Persisted authorization precedes writes. The shared integrity lock prevents
    # concurrent provisioning; interruptions retain the lock for operator review.
    await revoke_all_user_refresh_tokens(db, str(accounts[0]["_id"]))
    await db.users.update_one({"_id": accounts[0]["_id"]}, {"$set": {"is_active": False, "sessions_invalidated_at": now()}})
    revoked_at = now()
    await db.employees.update_one({"_id": employee["_id"]}, {"$set": {"offboarding_access_revoked_at": revoked_at}})
    employee["offboarding_access_revoked_at"] = revoked_at
    await audit(db, user, "offboarding.access.revoked", employee)


async def update_checklist(db, user, collection, current, status, notes=None, document_id=None):
    current = await collection.find_one({"_id": current["_id"]})
    if not current:
        raise HTTPException(404, "Checklist item not found")
    employee = await task_access(db, user, current, write=True)
    if status not in {"Pending", "In_Progress", "Completed"}:
        raise HTTPException(422, "Choose a valid checklist status")
    if employee.get("offboarding_completed_at") and current.get("task_type") == "exit_workflow":
        raise HTTPException(409, "Completed offboarding is immutable")
    if current.get("status") == "Completed" and status != "Completed":
        raise HTTPException(409, "Completed checklist items require HR review; history is preserved")
    if document_id:
        from utils.employee_access import find_linked_record
        doc = await find_linked_record(db.employee_documents, document_id, user)
        if doc.get("employee_id") not in reference_ids(employee) + [employee["_id"]] or doc.get("deleted_at") or doc.get("publication_state") not in (None, "Ready"):
            raise HTTPException(403, "Document does not belong to this workflow employee")
        require_hr(user)  # Verification does not publish private documents.
    if current.get("task_key") == "DOCS" and status == "Completed" and not (document_id or current.get("document_id")):
        raise HTTPException(422, "HR must link a verified Document Centre record")
    if status == current.get("status") and not document_id:
        return project(current, True)
    await audit(db, user, "lifecycle.checklist.updated", employee,
                task_id=str(current.get("id") or current["_id"]), previous_status=current.get("status"), status=status,
                document_id=document_id)
    update = {"status": status, "updated_at": now()}
    if status == "Completed":
        update.update(completed_at=now(), completed_by=user["id"])
    if document_id:
        update["document_id"] = document_id
    # Do not put free-text HR/medical notes into shared checklist projections.
    await collection.update_one({"_id": current["_id"]}, {"$set": update})
    await notify(db, employee, "checklist:" + str(current["_id"]) + ":" + status)
    return project({**current, **update}, True)


async def process_approved_exits(db):
    """Only previously authorized exits are eligible for timed processing."""
    from bson import ObjectId
    from utils.employee_integrity import integrity_write
    rows = await db.employees.find({"lifecycle_state": "Exiting",
        "offboarding_deactivation_approved_by": {"$exists": True}}).to_list(None)
    for row in rows:
        try:
            cutoff = datetime.combine(date.fromisoformat(row["last_working_day"]), time(17), timezone(timedelta(hours=3)))
            if datetime.now(timezone.utc) < cutoff:
                continue
            actor_id = row["offboarding_deactivation_approved_by"]
            if not ObjectId.is_valid(actor_id):
                continue
            actor = await db.users.find_one({"_id": ObjectId(actor_id), "is_active": {"$ne": False}})
            if not actor or tenant_of(actor) != tenant_of(row) or actor.get("role") not in HR:
                continue
            async with integrity_write(db):
                employee = await find_employee(db, employee_key(row), tenant_of(row))
                actor = {**actor, "id": str(actor["_id"])}
                await deactivate_account(db, actor, employee)
                await finalize_exit(db, actor, employee)
        except (HTTPException, KeyError, ValueError):
            # A failed guard never deactivates an account. One deduplicated HR
            # notification signals the required manual review, without private data.
            await notify(db, row, "offboarding:blocked")
