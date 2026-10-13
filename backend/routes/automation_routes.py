from fastapi import APIRouter, HTTPException, Request
from database import get_db
from utils.employee_access import find_linked_record, reject_identity_changes
from utils.task_access import authorize_task, authorize_notification
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
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit", "$or": [{"recipient_id": user["id"]}, {"recipient_role": user["role"]}]}
    notifications = await db.notifications.find(query).sort("created_at", -1).limit(50).to_list(50)
    visible = []
    for notification in notifications:
        try:
            await authorize_notification(db, user, notification)
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        visible.append(fmt(notification))
    return visible


@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    current = await find_linked_record(db.notifications, notif_id, user)
    await authorize_notification(db, user, current)
    await db.notifications.update_one({"_id": current["_id"]}, {"$set": {"is_read": True}})
    return {"message": "Marked as read"}
