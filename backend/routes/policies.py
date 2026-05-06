from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyCreate(BaseModel):
    title: str
    version: str
    category: str
    description: Optional[str] = None
    effective_date: str
    applies_to: Optional[list] = ["all"]


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_policies(request: Request):
    user = await get_current_user(request)
    db = get_db()
    policies = await db.policies.find({"tenant_id": "solvit"}).sort("title", 1).to_list(100)
    return [fmt(p) for p in policies]


@router.post("")
async def create_policy(policy: PolicyCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **policy.model_dump(),
        "status": "Active",
        "acknowledgement_count": 0,
        "file_url": None,
        "content": None,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.policies.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Fire automation event
    from automation.engine import automation_engine
    await automation_engine.fire_event("policy_updated", {"policy_id": doc["id"]})
    return doc


@router.get("/{policy_id}")
async def get_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        p = await db.policies.find_one({"_id": ObjectId(policy_id)})
    except Exception:
        p = await db.policies.find_one({"id": policy_id})
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    return fmt(p)


@router.post("/{policy_id}/acknowledge")
async def acknowledge_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    existing = await db.policy_acknowledgements.find_one({
        "policy_id": policy_id,
        "employee_id": user["id"],
        "tenant_id": "solvit"
    })
    if existing:
        return {"message": "Already acknowledged", "already_done": True}
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "policy_id": policy_id,
        "employee_id": user["id"],
        "employee_email": user.get("email"),
        "signature": body.get("signature"),
        "confirmed": True,
        "acknowledged_at": datetime.now(timezone.utc).isoformat()
    }
    await db.policy_acknowledgements.insert_one(doc)
    await db.policies.update_one({"id": policy_id}, {"$inc": {"acknowledgement_count": 1}})
    return {"message": "Policy acknowledged successfully"}


@router.get("/{policy_id}/acknowledgements")
async def get_acknowledgements(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    acks = await db.policy_acknowledgements.find({"policy_id": policy_id, "tenant_id": "solvit"}).to_list(500)
    return [fmt(a) for a in acks]


@router.put("/{policy_id}")
async def update_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.policies.find_one_and_update(
            {"_id": ObjectId(policy_id)}, {"$set": body}, return_document=True
        )
    except Exception:
        result = await db.policies.find_one_and_update(
            {"id": policy_id}, {"$set": body}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Policy not found")
    # Fire automation event for updated policy
    from automation.engine import automation_engine
    await automation_engine.fire_event("policy_updated", {"policy_id": policy_id})
    return fmt(result)
