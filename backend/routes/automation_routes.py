from fastapi import APIRouter, HTTPException, Request
from database import get_db
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
    return [fmt(t) for t in tasks]


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    if body.get("status") == "Completed":
        body["completed_at"] = datetime.now(timezone.utc).isoformat()
        body["completed_by"] = user["id"]
    from bson import ObjectId
    try:
        result = await db.tasks.find_one_and_update(
            {"_id": ObjectId(task_id)}, {"$set": body}, return_document=True
        )
    except Exception:
        result = await db.tasks.find_one_and_update(
            {"id": task_id}, {"$set": body}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return fmt(result)


@router.get("/notifications")
async def get_notifications(request: Request):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit", "$or": [{"recipient_id": user["id"]}, {"recipient_role": user["role"]}]}
    notifications = await db.notifications.find(query).sort("created_at", -1).limit(50).to_list(50)
    return [fmt(n) for n in notifications]


@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    from bson import ObjectId
    try:
        await db.notifications.update_one({"_id": ObjectId(notif_id)}, {"$set": {"is_read": True}})
    except Exception:
        await db.notifications.update_one({"id": notif_id}, {"$set": {"is_read": True}})
    return {"message": "Marked as read"}
