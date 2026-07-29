from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
from pathlib import Path
import uuid
import os
import shutil

router = APIRouter(prefix="/policies", tags=["policies"])

UPLOAD_ROOT = Path(os.environ.get("POLICY_UPLOAD_ROOT", "/opt/render/project/src/backend/uploads/policies"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg"}

CATEGORIES = [
    "01 - People Strategy Foundation",
    "02 - Talent Acquisition",
    "03 - Onboarding",
    "04 - Performance Management",
    "05 - Learning and Development",
    "06 - Rewards and Recognition",
    "07 - Retention",
    "08 - Policies and Compliance",
    "09 - Templates",
    "10 - People Management System",
    "11 - Internal Communications",
    "Code of Conduct",
    "Leave",
    "Compensation",
    "IT Security",
    "Health & Safety",
    "Disciplinary",
    "Other",
]


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
    policies = await db.policies.find({"tenant_id": "solvit"}).sort("category", 1).to_list(200)
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
        "file_name": None,
        "content": None,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.policies.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    try:
        from automation.engine import automation_engine
        await automation_engine.fire_event("policy_updated", {"policy_id": doc["id"]})
    except Exception:
        pass
    try:
        from utils.email_triggers import fire_and_forget
        active_emps = await db.employees.find(
            {"tenant_id": "solvit", "lifecycle_state": {"$in": ["Active", "Probation"]}}
        ).to_list(500)
        for emp in active_emps:
            if emp.get("work_email"):
                await fire_and_forget(db, "policy.published",
                                      employee_id=emp.get("id"), extra={
                                          "policy_title": doc.get("title"),
                                          "policy_version": doc.get("version"),
                                          "effective_date": doc.get("effective_date"),
                                          "category": doc.get("category"),
                                      })
    except Exception:
        pass
    return doc


@router.post("/{policy_id}/upload")
async def upload_policy_file(policy_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR can upload policy files")
    db = get_db()
    try:
        p = await db.policies.find_one({"_id": ObjectId(policy_id)})
    except Exception:
        p = await db.policies.find_one({"id": policy_id})
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")
    policy_dir = UPLOAD_ROOT / policy_id
    policy_dir.mkdir(parents=True, exist_ok=True)
    for old in policy_dir.iterdir():
        old.unlink()
    file_path = policy_dir / f"policy{ext}"
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.policies.update_one(
            {"_id": ObjectId(policy_id)},
            {"$set": {"file_url": str(file_path), "file_name": file.filename, "updated_at": now}}
        )
    except Exception:
        await db.policies.update_one(
            {"id": policy_id},
            {"$set": {"file_url": str(file_path), "file_name": file.filename, "updated_at": now}}
        )
    return {"message": "File uploaded successfully", "file_name": file.filename}


@router.get("/{policy_id}/download")
async def download_policy_file(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        p = await db.policies.find_one({"_id": ObjectId(policy_id)})
    except Exception:
        p = await db.policies.find_one({"id": policy_id})
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    file_url = p.get("file_url")
    if not file_url or not Path(file_url).exists():
        raise HTTPException(status_code=404, detail="No file attached to this policy")
    return FileResponse(
        path=file_url,
        filename=p.get("file_name", "policy_document"),
        media_type="application/octet-stream"
    )


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
    try:
        from automation.engine import automation_engine
        await automation_engine.fire_event("policy_updated", {"policy_id": policy_id})
    except Exception:
        pass
    return fmt(result)
