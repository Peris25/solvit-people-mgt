"""Private HR payroll attachments, never an employee-data import."""
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from utils import benefits, document_uploads
from utils.employee_integrity import tenant_of, tenant_query, integrity_write
from utils.employee_access import find_linked_record

KIND = 'hr_payroll_workbook'
MAX_BYTES = 5 * 1024 * 1024


def metadata(row):
    return {'id': str(row.get('id') or row['_id']), 'file_name': row['file_name'],
            'size_bytes': row['size_bytes'], 'uploaded_at': row['uploaded_at'],
            'uploaded_by_name': row.get('uploaded_by_name') or 'HR',
            'status': 'Available' if row.get('publication_state') == 'Ready' else 'Needs administrator review',
            'download_allowed': row.get('publication_state') == 'Ready'}


async def audit(db, user, row, action):
    await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
        'document_id': row['id'], 'action': action, 'category': 'Private HR payroll workbook',
        'by_user_id': user['id'], 'by_role': user['role'], 'timestamp': datetime.now(timezone.utc).isoformat()})


async def upload(db, user, file, root):
    benefits.privileged(user, write=True)
    name, ext = document_uploads.filename(file.filename)
    if ext != '.xlsx': raise HTTPException(400, 'Upload an Excel .xlsx workbook')
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_BYTES: raise HTTPException(413, 'Payroll workbook exceeds the 5 MB limit')
        chunks.append(chunk)
    if not size: raise HTTPException(400, 'The workbook is empty')
    content = b''.join(chunks)
    document_uploads.validate_content(content, ext, file.content_type)
    await document_uploads.scan_content(content)
    reference = str(uuid.uuid4())
    directory = Path(root).resolve() / 'payroll' / hashlib.sha256(tenant_of(user).encode()).hexdigest()[:24]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = (directory / (reference + ext)).resolve()
    if not path.is_relative_to(Path(root).resolve()): raise HTTPException(409, 'Private storage needs administrator review')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        output.write(content)
    row = {'id': reference, 'tenant_id': tenant_of(user), 'document_kind': KIND,
           'employee_id': None, 'visibility': 'hr_only', 'confidential': True, 'restricted': True,
           'category': 'Private HR payroll workbook', 'file_name': name, 'stored_path': str(path),
           'content_type': document_uploads.MIME[ext], 'size_bytes': size, 'scan_status': 'Clean',
           'uploaded_at': datetime.now(timezone.utc).isoformat(), 'uploaded_by': user['id'],
           'uploaded_by_name': user.get('full_name') or 'HR', 'publication_state': 'Pending_Audit', 'deleted_at': None}
    inserted = False
    try:
        async with integrity_write(db):
            benefits.privileged(user, write=True)
            await db.employee_documents.insert_one(row)
            inserted = True
            await audit(db, user, row, 'payroll_workbook.uploaded')
            await db.employee_documents.update_one({'id': reference, 'tenant_id': tenant_of(user)}, {'$set': {'publication_state': 'Ready'}})
    except HTTPException:
        if not inserted: path.unlink(missing_ok=True)
        raise
    except Exception:
        raise HTTPException(503, 'Payroll upload needs administrator review. Refresh the file list before retrying.')
    return metadata({**row, 'publication_state': 'Ready'})


async def listing(db, user):
    benefits.privileged(user)
    rows = await db.employee_documents.find({'$and': [tenant_query(tenant_of(user)), {'document_kind': KIND, 'deleted_at': None}]}).sort('uploaded_at', -1).to_list(100)
    return [metadata(row) for row in rows]


async def download(db, user, reference, root):
    benefits.privileged(user)
    row = await find_linked_record(db.employee_documents, reference, user)
    if row.get('document_kind') != KIND or row.get('deleted_at'):
        raise HTTPException(404, 'Payroll workbook not found')
    if row.get('publication_state') != 'Ready' or row.get('scan_status') != 'Clean':
        raise HTTPException(503, 'Payroll workbook requires administrator review')
    try:
        path = Path(row['stored_path']).resolve()
        payroll_root = Path(root).resolve() / 'payroll' / hashlib.sha256(tenant_of(user).encode()).hexdigest()[:24]
        if not path.is_relative_to(payroll_root) or not path.is_file(): raise ValueError()
    except (KeyError, TypeError, ValueError, OSError, RuntimeError):
        raise HTTPException(404, 'Payroll workbook is unavailable')
    await audit(db, user, row, 'payroll_workbook.downloaded')
    return path, row['file_name']
