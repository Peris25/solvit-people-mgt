from fastapi import APIRouter, HTTPException, Request, Query
from typing import Literal, Optional
from database import get_db
from utils.employee_access import find_linked_record, reject_identity_changes
from utils.task_access import authorize_task
from utils.auth import get_current_user
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/automation", tags=["automation"])


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_rules(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    rules = await db.automation_rules.find({"tenant_id": "solvit"}).sort("rule_id", 1).to_list(100)
    return [fmt(r) for r in rules]


@router.put("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    rule = await db.automation_rules.find_one({"rule_id": rule_id, "tenant_id": "solvit"})
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    new_status = not rule.get("is_active", True)
    await db.automation_rules.update_one(
        {"rule_id": rule_id, "tenant_id": "solvit"},
        {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"rule_id": rule_id, "is_active": new_status}


@router.get("/tasks")
async def list_tasks(request: Request, status: str = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if status:
        query["status"] = status
    if user["role"] == "employee":
        query["assigned_to"] = user["id"]
    elif user["role"] == "line_manager":
        query["assigned_role"] = "line_manager"
    tasks = await db.tasks.find(query).sort("created_at", -1).to_list(200)
    visible = []
    for task in tasks:
        try:
            await authorize_task(db, user, task)
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        visible.append(fmt(task))
    return visible


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    current = await find_linked_record(db.tasks, task_id, user)
    if current.get("task_type") == "exit_workflow":
        from utils.lifecycle_workflows import update_checklist
        from utils.employee_integrity import integrity_write
        body = await request.json()
        reject_identity_changes(body, current, ("id", "_id", "tenant_id", "employee_id", "entity_id", "assigned_to", "assigned_role", "task_type", "task_key"))
        async with integrity_write(db):
            return await update_checklist(db, user, db.tasks, current, body.get("status"))
    await authorize_task(db, user, current, write=True)
    body = await request.json()
    reject_identity_changes(body, current, ("id", "_id", "tenant_id", "employee_id", "entity_id", "assigned_to", "assigned_role"))
    update = {k: v for k, v in body.items() if k in {"status", "notes"}}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    if body.get("status") == "Completed":
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
        update["completed_by"] = user["id"]
    result = await db.tasks.find_one_and_update({"_id": current["_id"]}, {"$set": update}, return_document=True)
    if not result:
        raise HTTPException(404, "Task not found")
    return fmt(result)


@router.get("/notifications")
async def get_notifications(request: Request):
    from utils.notification_centre import list_inbox
    user = await get_current_user(request)
    return (await list_inbox(get_db(), user))["items"]


@router.get("/notifications/centre")
async def notification_centre(request: Request, category: Optional[Literal["Leave", "Approvals", "Onboarding", "Training", "Announcements", "Performance", "Recognition", "Policies", "System"]] = None,
                              kind: Optional[Literal["Action required", "Updates", "Approvals"]] = None, read_status: Literal["all", "unread", "read"] = "all", offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    from utils.notification_centre import list_inbox
    return await list_inbox(get_db(), await get_current_user(request), category=category, kind=kind, read_status=read_status, offset=offset, limit=limit)


@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, request: Request):
    from utils.notification_centre import read_notification
    user = await get_current_user(request)
    return await read_notification(get_db(), user, notif_id)
