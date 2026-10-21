from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
from utils.employee_access import find_linked_record
from utils.employee_integrity import tenant_of, tenant_query
from pathlib import Path
import uuid
import os
import shutil
import hashlib
from utils.employee_integrity import integrity_write
from utils.legacy_security import module_access, policy_visible, policy_record, audit, projection, HR
from utils import document_uploads

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
    content: Optional[str] = None
    status: Literal["Draft", "Active"] = "Draft"


def readable_policy(doc):
    if isinstance(doc.get("content"), str) and doc["content"].strip():
        return True
    value = doc.get("file_url")
    if not isinstance(value, str) or not value:
        return False
    try:
        path = Path(value).resolve()
        return path.is_relative_to(UPLOAD_ROOT.resolve()) and path.is_file() and path.stat().st_size > 0
    except (OSError, ValueError, RuntimeError):
        return False


def fmt(doc):
    if not doc:
        return None
    out = projection(doc, {"title", "version", "category", "description", "effective_date", "applies_to", "status", "content", "created_at", "updated_at", "acknowledgement_count", "file_name"})
    out["has_attachment"] = bool(doc.get("file_url"))
    out["acknowledgement_available"] = doc.get("status") == "Active" and readable_policy(doc)
    if isinstance(out.get("file_name"), str): out["file_name"] = out["file_name"].replace(chr(92), "/").split("/")[-1]
    return out


@router.get("")
async def list_policies(request: Request):
    user = await get_current_user(request)
    db = get_db()
    module_access(user, "M13")
    policies = await db.policies.find(tenant_query(tenant_of(user))).sort("category", 1).to_list(200)
    return [fmt(p) for p in policies if policy_visible(p, user)]


@router.post("")
async def create_policy(policy: PolicyCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    module_access(user, "M13", write=True)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **policy.model_dump(),
        "status": policy.status,
        "acknowledgement_count": 0,
        "file_url": None,
        "file_name": None,
        "content": policy.content,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if doc["status"] == "Active" and not readable_policy(doc):
        raise HTTPException(422, "Readable policy content is required before publication")
    async with integrity_write(db):
        await audit(db, user, "policy.created", doc["id"])
        result = await db.policies.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    if doc["status"] == "Active":
        await notify_publication(db, doc)
    return doc


async def notify_publication(db, doc):
    try:
        from automation.engine import automation_engine
        await automation_engine.fire_event("policy_updated", {"policy_id": doc["id"]})
    except Exception:
        pass
    try:
        from utils.email_triggers import fire_and_forget
        active_emps = await db.employees.find(
            {"tenant_id": tenant_of(doc), "lifecycle_state": {"$in": ["Active", "Probation"]}}
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



@router.post("/{policy_id}/upload")
async def upload_policy_file(policy_id: str, request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR can upload policy files")
    db = get_db()
    module_access(user, "M13", write=True)
    p = await policy_record(db, user, policy_id)
    name, ext = document_uploads.filename(file.filename)
    content = await document_uploads.read_bounded(file)
    document_uploads.validate_content(content, ext, file.content_type)
    await document_uploads.scan_content(content)
    policy_dir = (UPLOAD_ROOT / str(p['_id'])).resolve()
    if not policy_dir.is_relative_to(UPLOAD_ROOT.resolve()):
        raise HTTPException(409, 'Policy storage needs administrator review')
    path = policy_dir / f"{uuid.uuid4()}{ext}"
    async with integrity_write(db):
        current = await policy_record(db, user, policy_id)
        if current != p: raise HTTPException(409, "Policy changed; refresh before uploading")
        await audit(db, user, "policy.file.uploaded", p['_id'])
        policy_dir.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(content)
        history = list(p.get('file_history') or [])
        if p.get('file_url'):
            history.append({key: p.get(key) for key in ('file_url', 'file_name', 'version', 'updated_at')})
        await db.policies.update_one({"_id": p["_id"]}, {"$set": {"file_url": str(path), "file_name": name,
            "file_history": history, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "File uploaded successfully", "file_name": name}


@router.get("/{policy_id}/download")
async def download_policy_file(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    p = await policy_record(db, user, policy_id)
    file_url = p.get("file_url")
    path = Path(file_url).resolve() if isinstance(file_url, str) else None
    if not path or not path.is_relative_to(UPLOAD_ROOT.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="No file attached to this policy")
    await audit(db, user, "policy.file.downloaded", p["_id"])
    return FileResponse(
        path=path,
        filename=p.get("file_name", "policy_document"),
        media_type="application/octet-stream"
    )


@router.get("/{policy_id}")
async def get_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    p = await policy_record(db, user, policy_id)
    return fmt(p)


@router.post("/{policy_id}/acknowledge")
async def acknowledge_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    p = await policy_record(db, user, policy_id)
    body = await request.json()
    if not isinstance(body, dict) or set(body) - {"signature", "confirmed"} or not isinstance(body.get("signature"), str) or not body["signature"].strip() or len(body["signature"]) > 10000:
        raise HTTPException(422, "A bounded signature is required")
    version = str(p.get("version") or "legacy")
    key = hashlib.sha256(f"{tenant_of(user)}:{p['_id']}:{version}:{user['id']}".encode()).hexdigest()
    async with integrity_write(db):
        current = await policy_record(db, user, policy_id)
        if current != p:
            raise HTTPException(409, "Policy changed; refresh before acknowledging")
        existing = await db.policy_acknowledgements.find_one({"_id": "policy-ack:" + key})
        if existing: return {"message": "Already acknowledged", "already_done": True}
        if p.get("status") != "Active" or not readable_policy(p):
            raise HTTPException(409, "Readable published policy content is required before acknowledgement")
        doc = {"_id": "policy-ack:" + key, "id": str(uuid.uuid4()), "tenant_id": tenant_of(user),
            "policy_id": str(p.get("id") or p['_id']), "policy_storage_id": str(p['_id']), "policy_version": version,
            "employee_id": user["id"], "employee_email": user.get("email"), "signature": body["signature"],
            "confirmed": True, "acknowledged_at": datetime.now(timezone.utc).isoformat()}
        await audit(db, user, "policy.acknowledged", p['_id'])
        await db.policy_acknowledgements.insert_one(doc)
    return {"message": "Policy acknowledged successfully"}


@router.get("/{policy_id}/acknowledgements")
async def get_acknowledgements(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    p = await policy_record(db, user, policy_id)
    acks = await db.policy_acknowledgements.find({"$and": [tenant_query(tenant_of(user)), {"policy_id": {"$in": [str(p.get("id") or p["_id"]), str(p["_id"])]}}]}).to_list(500)
    return [fmt(a) for a in acks]


@router.put("/{policy_id}")
async def update_policy(policy_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    module_access(user, "M13", write=True)
    body = await request.json()
    if not isinstance(body, dict) or set(body) - {'title', 'version', 'category', 'description', 'effective_date', 'applies_to', 'status', 'content'}:
        raise HTTPException(422, 'Policy file paths and ownership cannot be changed through metadata')
    if "applies_to" in body and (not isinstance(body["applies_to"], list) or not body["applies_to"] or any(not isinstance(x, str) for x in body["applies_to"])):
        raise HTTPException(422, "Explicit policy audiences are required")
    if body.get("status") and body["status"] not in {"Active", "Draft", "Archived", "Retired"}:
        raise HTTPException(422, "Unknown policy status")
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    existing = await find_linked_record(db.policies, policy_id, user)
    if body.get("content") != existing.get("content") and "content" in body and body.get("version", existing.get("version")) == existing.get("version"):
        raise HTTPException(409, "Policy content changes require a new version")
    async with integrity_write(db):
        current = await find_linked_record(db.policies, policy_id, user)
        if current != existing:
            raise HTTPException(409, "Policy changed; refresh before updating")
        prospective = {**existing, **body}
        if prospective.get("status") == "Active" and not readable_policy(prospective):
            raise HTTPException(422, "Readable policy content is required before publication")
        await audit(db, user, "policy.updated", existing["_id"])
        result = await db.policies.find_one_and_update({"_id": existing["_id"]}, {"$set": body}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Policy not found")
    if result.get("status") == "Active" and (existing.get("status") != "Active" or existing.get("version") != result.get("version")):
        await notify_publication(db, result)
    return fmt(result)
