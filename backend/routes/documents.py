"""Employee Personal Documents — upload / list / view / delete with audit log.

Storage: local filesystem at /app/backend/uploads/employee_docs/{employee_id}/.
Metadata persisted in MongoDB `employee_documents` collection.
"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from database import get_db
from utils.auth import get_current_user
import uuid
import os


async def _find_employee(db, employee_id: str):
    """Resolve an employee by UUID id or Mongo ObjectId string."""
    emp = await db.employees.find_one({"id": employee_id})
    if emp:
        return emp
    try:
        return await db.employees.find_one({"_id": ObjectId(employee_id)})
    except (InvalidId, TypeError):
        return None

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_ROOT = Path(os.environ.get("DOC_UPLOAD_ROOT", "/app/backend/uploads/employee_docs"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".docx"}
ALLOWED_MIME = {
    "application/pdf", "image/jpeg", "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

DEFAULT_CATEGORIES = [
    "National ID / Passport",
    "Signed Employment Contract",
    "Academic Certificates",
    "NSSF Card / Registration",
    "NHIF Card / Registration",
    "Bank Account Details Letter",
    "KRA PIN Certificate",
    "Disciplinary Letter",
    "Performance Improvement Plan",
    "Other",
]


async def _get_categories():
    """Pulled live from masters_settings.lookups.document_categories."""
    from routes.masters_settings import get_setting
    cats = await get_setting("lookups", "document_categories", DEFAULT_CATEGORIES)
    return cats or DEFAULT_CATEGORIES


async def _can_view_employee_docs(user: dict, employee_id: str) -> bool:
    """HR Admin/HR Manager full; Line Manager only for direct reports; others denied."""
    role = user.get("role")
    if role in ("hr_admin", "hr_manager", "it_admin"):
        return True
    if role == "line_manager":
        db = get_db()
        emp = await _find_employee(db, employee_id)
        if emp and emp.get("line_manager_id") in (user.get("employee_id"), user.get("id")):
            return True
    return False


def _can_write(user: dict) -> bool:
    return user.get("role") in ("hr_admin", "hr_manager")


@router.get("/categories")
async def list_categories(request: Request):
    await get_current_user(request)
    return {"categories": await _get_categories()}


@router.get("/employee/{employee_id}")
async def list_employee_documents(employee_id: str, request: Request):
    user = await get_current_user(request)
    if not await _can_view_employee_docs(user, employee_id):
        raise HTTPException(status_code=403, detail="No access to this employee's documents")
    db = get_db()
    rows = await db.employee_documents.find(
        {"tenant_id": "solvit", "employee_id": employee_id, "deleted_at": None}
    ).sort("uploaded_at", -1).to_list(500)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "employee_id": r.get("employee_id"),
            "category": r.get("category"),
            "category_label": r.get("category_label"),
            "file_name": r.get("file_name"),
            "size_bytes": r.get("size_bytes"),
            "uploaded_at": r.get("uploaded_at"),
            "uploaded_by": r.get("uploaded_by"),
            "uploaded_by_name": r.get("uploaded_by_name"),
        })
    return out


@router.post("/employee/{employee_id}/upload")
async def upload_document(
    employee_id: str,
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    category_label: Optional[str] = Form(None),
):
    user = await get_current_user(request)
    if not _can_write(user):
        raise HTTPException(status_code=403, detail="Only HR can upload employee documents")
    db = get_db()
    emp = await _find_employee(db, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Validate
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext}. Allowed: PDF, JPEG, PNG, DOCX")
    if file.content_type and file.content_type not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported MIME type {file.content_type}")

    cats = await _get_categories()
    if category not in cats:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit")

    # Persist
    doc_id = str(uuid.uuid4())
    target_dir = UPLOAD_ROOT / employee_id
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{doc_id}{ext}"
    target_path = target_dir / safe_name
    with open(target_path, "wb") as f:
        f.write(content)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": doc_id,
        "tenant_id": "solvit",
        "employee_id": employee_id,
        "category": category,
        "category_label": category_label if category == "Other" else None,
        "file_name": file.filename,
        "stored_path": str(target_path),
        "size_bytes": len(content),
        "content_type": file.content_type or "application/octet-stream",
        "uploaded_at": now,
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("full_name") or user.get("email"),
        "deleted_at": None,
    }
    await db.employee_documents.insert_one(doc)
    await db.document_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "document_id": doc_id,
        "employee_id": employee_id,
        "action": "uploaded",
        "by_user_id": user["id"],
        "by_user_name": user.get("full_name") or user.get("email"),
        "by_role": user.get("role"),
        "file_name": file.filename,
        "category": category,
        "timestamp": now,
    })
    return {"id": doc_id, "file_name": file.filename, "category": category, "uploaded_at": now}


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    doc = await db.employee_documents.find_one({"id": doc_id, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await _can_view_employee_docs(user, doc["employee_id"]):
        raise HTTPException(status_code=403, detail="No access")
    path = Path(doc["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, media_type=doc.get("content_type") or "application/octet-stream",
                        filename=doc.get("file_name") or path.name)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    if not _can_write(user):
        raise HTTPException(status_code=403, detail="Only HR can delete documents")
    db = get_db()
    doc = await db.employee_documents.find_one({"id": doc_id, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.employee_documents.update_one(
        {"id": doc_id},
        {"$set": {"deleted_at": now, "deleted_by": user["id"], "deleted_by_name": user.get("full_name") or user.get("email")}}
    )
    # Physically remove the file
    try:
        p = Path(doc["stored_path"])
        if p.exists():
            p.unlink()
    except Exception:
        pass
    await db.document_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "document_id": doc_id,
        "employee_id": doc["employee_id"],
        "action": "deleted",
        "by_user_id": user["id"],
        "by_user_name": user.get("full_name") or user.get("email"),
        "by_role": user.get("role"),
        "file_name": doc.get("file_name"),
        "category": doc.get("category"),
        "timestamp": now,
    })
    return {"deleted": True, "id": doc_id}


@router.get("/audit-log")
async def document_audit_log(request: Request, employee_id: Optional[str] = None, limit: int = 200):
    user = await get_current_user(request)
    if user.get("role") not in ("hr_admin", "hr_manager", "it_admin"):
        raise HTTPException(status_code=403, detail="Audit log restricted")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if employee_id:
        q["employee_id"] = employee_id
    rows = await db.document_audit.find(q).sort("timestamp", -1).to_list(min(limit, 500))
    for r in rows:
        r.pop("_id", None)
    return rows
