"""Employee Personal Documents — upload / list / view / delete with audit log.

Storage: private DOC_UPLOAD_ROOT, with immutable random names under employee storage IDs.
Metadata persisted in MongoDB `employee_documents` collection.
"""
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime, timezone, date
from typing import Optional
from bson import ObjectId
from bson.errors import InvalidId
from database import get_db
from utils.employee_integrity import is_direct_report, find_employee, employee_key, tenant_of, tenant_query, integrity_write
from utils.employee_access import reference_ids, find_linked_record, authorize_employee, personal_grant
from utils.auth import get_current_user
import uuid
import os
from utils.document_uploads import MAX_BYTES, MIME, filename, read_bounded, validate_content, scan_content


async def _find_employee(db, employee_id: str, tenant="solvit"):
    """Resolve an employee by UUID id or Mongo ObjectId string."""
    return await find_employee(db, employee_id, tenant)

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_ROOT = Path(os.environ.get("DOC_UPLOAD_ROOT", "/app/backend/uploads/employee_docs"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
ALLOWED_EXT = set(MIME)
ALLOWED_MIME = set(MIME.values())

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
    """Scope the employee first; individual files require explicit visibility too."""
    role = user.get("role")
    try:
        employee = await authorize_employee(get_db(), user, employee_id, "M01")
        if role not in {'hr_admin', 'hr_manager'} and str(employee.get('lifecycle_state') or '').lower() in {'exited', 'suspended', 'terminated'}:
            return False
        return role != "solver"
    except HTTPException:
        return False


def _visible(doc, employee, user):
    if user.get("role") in ("hr_admin", "hr_manager"):
        return True
    category = " ".join(str(doc.get(key) or "") for key in ("category", "category_label", "title")).lower()
    if doc.get("restricted") or doc.get("confidential") is not False or any(term in category for term in ("disciplin", "medical", "salary", "payslip", "p9", "warning", "hearing", "improvement plan")):
        return False
    visibility = doc.get("visibility")
    if employee_key(employee) == user.get("employee_id"):
        return visibility in {"hr_employee", "hr_employee_manager", "HR + employee", "HR + employee + line manager"}
    return visibility in {"hr_employee_manager", "HR + employee + line manager"} and is_direct_report(employee, user)


def _restricted(doc):
    description = ' '.join(str(doc.get(key) or '') for key in ('category', 'category_label', 'title')).lower()
    return bool(doc.get('restricted')) or any(term in description for term in ('disciplin', 'medical', 'salary', 'payslip', 'p9', 'warning', 'hearing', 'improvement plan'))


def _can_write(user: dict) -> bool:
    return user.get("role") in ("hr_admin", "hr_manager")


def _display_name(value):
    return ''.join(c for c in str(value or '').replace('\\', '/').rsplit('/', 1)[-1] if ord(c) >= 32 and ord(c) != 127)[:200] or 'Document'


def _metadata(doc, employee, user):
    allowed = {key: value for key in ('category', 'category_label', 'size_bytes', 'uploaded_at', 'uploaded_by_name', 'title', 'issued_date', 'effective_date', 'expiry_date')
               if (value := doc.get(key)) is None or isinstance(value, (str, int, float, bool))}
    allowed.update(id=str(doc.get('id') or doc['_id']), employee_id=employee_key(employee), file_name=_display_name(doc.get('file_name')))
    available = doc.get('publication_state') in (None, 'Ready')
    allowed['download_allowed'] = available
    current = datetime.now(timezone.utc).date().isoformat()
    allowed['status'] = 'Available' if available else 'Needs administrator review'
    if available and isinstance(doc.get('expiry_date'), str) and doc['expiry_date'] < current: allowed['status'] = 'Expired'
    elif available and isinstance(doc.get('effective_date'), str) and doc['effective_date'] > current: allowed['status'] = 'Not yet effective'
    if _can_write(user):
        visibility = {'HR + employee': 'hr_employee', 'HR + employee + line manager': 'hr_employee_manager'}.get(doc.get('visibility'), doc.get('visibility'))
        allowed.update(visibility=visibility if visibility in {'hr_only', 'hr_employee', 'hr_employee_manager'} else 'hr_only', confidential=doc.get('confidential') is not False or _restricted(doc),
                       scan_status=doc.get('scan_status') or 'Legacy scan not recorded')
    return allowed


@router.get('/me')
async def my_documents(request: Request):
    from utils.profile_self_service import self_employee
    user = await get_current_user(request)
    employee = await self_employee(get_db(), user)
    return await list_employee_documents(employee_key(employee), request)


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
    employee = await _find_employee(db, employee_id, tenant_of(user))
    if not employee: raise HTTPException(404, "Employee not found")
    rows = await db.employee_documents.find(
        {"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": [*reference_ids(employee), employee["_id"]]}, "deleted_at": None}]}
    ).sort("uploaded_at", -1).to_list(500)
    out = []
    seen = set()
    for r in rows:
        if not _visible(r, employee, user): continue
        reference = str(r.get('id') or r['_id'])
        if reference in seen: raise HTTPException(409, 'Ambiguous document references require administrator review')
        seen.add(reference)
        if r.get('publication_state') not in (None, 'Ready') and not _can_write(user): continue
        out.append(_metadata(r, employee, user))
    return out


@router.post("/employee/{employee_id}/upload")
async def upload_document(
    employee_id: str,
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    category_label: Optional[str] = Form(None),
    visibility: str = Form("hr_only"),
    confidential: bool = Form(True),
):
    user = await get_current_user(request)
    if not _can_write(user):
        raise HTTPException(status_code=403, detail="Only HR can upload employee documents")
    db = get_db()
    emp = await _find_employee(db, employee_id, tenant_of(user))
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    await authorize_employee(db, user, employee_id, "M01", write=True)
    if visibility not in {"hr_only", "hr_employee", "hr_employee_manager"}:
        raise HTTPException(422, "Choose an approved document visibility")
    employee_id = employee_key(emp)

    # Validate
    file_name, ext = filename(file.filename)

    cats = await _get_categories()
    if category not in cats:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")

    if category_label is not None and (len(category_label) > 200 or any(ord(c) < 32 for c in category_label)):
        raise HTTPException(422, 'Document label must be plain text within 200 characters')
    content = await read_bounded(file)
    validate_content(content, ext, file.content_type)
    await scan_content(content)

    # Persist
    doc_id = str(uuid.uuid4())
    target_dir = UPLOAD_ROOT / str(emp["_id"])
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe_name = f"{doc_id}{ext}"
    target_path = (target_dir / safe_name).resolve()
    if not target_path.is_relative_to(UPLOAD_ROOT.resolve()):
        raise HTTPException(409, "Document storage needs administrator review")
    with os.fdopen(os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
        f.write(content)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": doc_id,
        "tenant_id": tenant_of(user),
        "visibility": visibility,
        "confidential": confidential,
        "employee_id": employee_id,
        "category": category,
        "category_label": category_label if category == "Other" else None,
        "file_name": file_name,
        "title": file_name,
        "scan_status": "Clean",
        "publication_state": "Pending_Audit",
        "stored_path": str(target_path),
        "size_bytes": len(content),
        "content_type": MIME[ext],
        "uploaded_at": now,
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("full_name") or user.get("email"),
        "deleted_at": None,
    }
    inserted = False
    try:
        async with integrity_write(db):
            await authorize_employee(db, user, employee_id, 'M01', write=True)
            await db.employee_documents.insert_one(doc)
            inserted = True
            await db.document_audit.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_of(user),
                "document_id": doc_id,
                "employee_id": employee_id,
                "action": "uploaded",
                "by_user_id": user["id"],
                "by_user_name": user.get("full_name") or user.get("email"),
                "by_role": user.get("role"),
                "file_name": file_name,
                "category": category,
                "timestamp": now,
            })
            await db.employee_documents.update_one({'id': doc_id, 'tenant_id': tenant_of(user)}, {'$set': {'publication_state': 'Ready'}})
    except HTTPException:
        if not inserted: target_path.unlink(missing_ok=True)
        raise
    except Exception:
        raise HTTPException(503, {'code': 'document_upload_needs_review', 'id': doc_id, 'message': 'Upload needs administrator review. Refresh before retrying.'})
    return {"id": doc_id, "file_name": file_name, "category": category, "uploaded_at": now}


@router.put('/{doc_id}')
async def update_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    if not _can_write(user): raise HTTPException(403, 'Only HR can manage employee documents')
    body = await request.json()
    fields = {'title', 'category', 'category_label', 'visibility', 'confidential', 'issued_date', 'effective_date', 'expiry_date'}
    if not isinstance(body, dict) or not body or set(body) - fields:
        raise HTTPException(422, 'Only document classification and display metadata may be changed; ownership is fixed')
    for key, value in body.items():
        if key == 'confidential':
            if not isinstance(value, bool): raise HTTPException(422, 'Confidential must be true or false')
        elif key.endswith('_date'):
            if value is not None:
                try:
                    if not isinstance(value, str) or len(value) != 10: raise ValueError()
                    date.fromisoformat(value)
                except ValueError: raise HTTPException(422, 'Document dates must use valid YYYY-MM-DD values')
        elif not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
            raise HTTPException(422, 'Document metadata must be plain text within 200 characters')
    if 'visibility' in body and body['visibility'] not in {'hr_only', 'hr_employee', 'hr_employee_manager'}:
        raise HTTPException(422, 'Choose an approved document visibility')
    db = get_db()
    async with integrity_write(db):
        doc = await find_linked_record(db.employee_documents, doc_id, user)
        employee = await authorize_employee(db, user, doc.get('employee_id'), 'M01', write=True)
        if doc.get('deleted_at'): raise HTTPException(404, 'Document not found')
        if doc.get('publication_state') not in (None, 'Ready'): raise HTTPException(409, 'This document requires administrator recovery before another change')
        if 'category' in body and body['category'] != doc.get('category') and body['category'] not in await _get_categories():
            raise HTTPException(422, 'Choose a configured document category')
        proposed = {**doc, **body}
        if proposed.get('expiry_date') and proposed.get('effective_date') and proposed['expiry_date'] < proposed['effective_date']:
            raise HTTPException(422, 'Expiry cannot precede the effective date')
        if _restricted(doc) or _restricted(proposed): body.update(restricted=True, confidential=True, visibility='hr_only')
        await db.employee_documents.update_one({'_id': doc['_id']}, {'$set': {**body, 'publication_state': 'Pending_Audit', 'updated_at': datetime.now(timezone.utc).isoformat()}})
        await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user), 'document_id': str(doc.get('id') or doc['_id']),
                                            'employee_id': employee_key(employee), 'action': 'changed', 'by_user_id': user['id'], 'by_role': user['role'],
                                            'before': {key: doc.get(key) for key in body}, 'changes': body, 'timestamp': datetime.now(timezone.utc).isoformat()})
        await db.employee_documents.update_one({'_id': doc['_id']}, {'$set': {'publication_state': 'Ready'}})
    return _metadata({**doc, **body, 'publication_state': 'Ready'}, employee, user)


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    doc = await find_linked_record(db.employee_documents, doc_id, user)
    if doc.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Document not found")
    if not await _can_view_employee_docs(user, doc["employee_id"]):
        raise HTTPException(status_code=403, detail="No access")
    employee = await _find_employee(db, doc["employee_id"], tenant_of(user))
    if not employee or not _visible(doc, employee, user): raise HTTPException(403, "Document visibility does not permit access")
    if doc.get('publication_state') not in (None, 'Ready'):
        raise HTTPException(503, 'This document requires administrator review before download')
    try:
        stored_path = doc.get('stored_path')
        if not isinstance(stored_path, str) or not stored_path: raise ValueError()
        path = Path(stored_path).resolve()
    except (ValueError, OSError, RuntimeError):
        raise HTTPException(404, 'File missing on disk')
    if not path.is_relative_to(UPLOAD_ROOT.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")
    await db.document_audit.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "document_id": str(doc.get('id') or doc['_id']),
                                        "employee_id": employee_key(employee), "action": "downloaded", "by_user_id": user["id"],
                                        "by_role": user["role"], "timestamp": datetime.now(timezone.utc).isoformat()})
    return FileResponse(path, media_type=MIME.get(path.suffix.lower(), 'application/octet-stream'),
                        filename=_display_name(doc.get("file_name")), headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    if not _can_write(user):
        raise HTTPException(status_code=403, detail="Only HR can delete documents")
    db = get_db()
    async with integrity_write(db):
        doc = await find_linked_record(db.employee_documents, doc_id, user)
        if doc.get("deleted_at"):
            raise HTTPException(status_code=404, detail="Document not found")
        await authorize_employee(db, user, doc["employee_id"], "M01", write=True)
        now = datetime.now(timezone.utc).isoformat()
        await db.employee_documents.update_one(
            {"_id": doc["_id"]},
            {"$set": {"deleted_at": now, "deleted_by": user["id"], "deleted_by_name": user.get("full_name") or user.get("email")}}
        )
        # Preserve the file as history; retention/recycle-bin administration is separate.
        await db.document_audit.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_of(user),
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
    personal_grant(user, 'M01')
    if not 1 <= limit <= 500: raise HTTPException(422, 'Audit limit must be between 1 and 500')
    q = tenant_query(tenant_of(user))
    if employee_id:
        employee = await authorize_employee(db, user, employee_id, 'M01')
        q = {'$and': [q, {'employee_id': {'$in': [*reference_ids(employee), employee['_id']]}}]}
    rows = await db.document_audit.find(q).sort("timestamp", -1).to_list(min(limit, 500))
    output = []
    fields = {'id', 'document_id', 'employee_id', 'action', 'by_user_id', 'by_user_name', 'by_role', 'category', 'timestamp'}
    metadata_fields = {'title', 'category', 'category_label', 'visibility', 'confidential', 'issued_date', 'effective_date', 'expiry_date', 'restricted'}
    for row in rows:
        try:
            await authorize_employee(db, user, row.get('employee_id'), 'M01')
        except HTTPException as error:
            if error.status_code in (403, 404): continue
            raise
        item = {key: str(value) if isinstance(value, ObjectId) else value for key, value in row.items() if key in fields and isinstance(value, (str, int, bool, ObjectId))}
        if row.get('file_name'): item['file_name'] = _display_name(row['file_name'])
        for key in ('changes', 'before'):
            if isinstance(row.get(key), dict): item[key] = {field: value for field, value in row[key].items() if field in metadata_fields and (value is None or isinstance(value, (str, bool)))}
        output.append(item)
    return output
