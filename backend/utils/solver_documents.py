"""Solver ownership adapter for the existing private Document Centre storage."""
from pathlib import Path
import os
import uuid
from fastapi import HTTPException
from fastapi.responses import FileResponse
from utils.document_uploads import filename, read_bounded, validate_content, scan_content, MIME
from utils.employee_access import find_linked_record
from utils.employee_integrity import tenant_query, tenant_of, integrity_write
from utils.solver_access import authorize_solver, solver_key, solver_aliases, HR_ROLES
from utils.solver_workflows import now

CATEGORIES = ('Contact and statutory form', 'Induction video confirmation', 'Code quiz result',
              'Signed Solver agreement', 'Vehicle assessment', 'Other')


def visible(doc, user):
    if user.get('role') in HR_ROLES:
        return True
    return doc.get('confidential') is False and doc.get('visibility') in (
        {'hr_solver', 'hr_assessment'} if user.get('role') == 'solver' else {'hr_manager'})


def metadata(doc):
    return {key: doc.get(key) for key in ('id', 'category', 'file_name', 'uploaded_at', 'size_bytes', 'visibility', 'confidential')}


async def listing(db, user, reference):
    record = await authorize_solver(db, user, reference)
    rows = await db.solver_documents.find({'$and': [tenant_query(tenant_of(user)),
        {'solver_id': {'$in': solver_aliases(record)}, 'deleted_at': None}]}).to_list(None)
    return [metadata(row) for row in rows if row.get('publication_state') == 'Ready' and visible(row, user)]


async def upload(db, user, reference, file, category, visibility, confidential):
    if user.get('role') not in HR_ROLES:
        raise HTTPException(403, 'Only authorized HR may assign Solver documents')
    record = await authorize_solver(db, user, reference, write=True)
    if category not in CATEGORIES or visibility not in {'hr_only', 'hr_manager', 'hr_solver', 'hr_assessment'}:
        raise HTTPException(422, 'Choose an approved document category and visibility')
    if confidential and visibility != 'hr_only':
        raise HTTPException(422, 'Confidential Solver documents must remain HR-only')
    name, ext = filename(file.filename)
    content = await read_bounded(file)
    validate_content(content, ext, file.content_type)
    await scan_content(content)
    from routes.documents import UPLOAD_ROOT
    folder = (UPLOAD_ROOT / 'solvers' / str(record['_id'])).resolve()
    if not folder.is_relative_to(UPLOAD_ROOT.resolve()):
        raise HTTPException(409, 'Document storage requires review')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = str(uuid.uuid4())
    path = folder / (key + ext)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(content)
    row = {'id': key, 'tenant_id': tenant_of(user), 'solver_id': solver_key(record),
           'file_name': name, 'stored_path': str(path), 'category': category,
           'visibility': visibility, 'confidential': confidential, 'uploaded_at': now(),
           'size_bytes': len(content), 'scan_status': 'Clean', 'publication_state': 'Pending_Audit', 'deleted_at': None}
    inserted = False
    try:
        async with integrity_write(db):
            await authorize_solver(db, user, reference, write=True)
            await db.solver_documents.insert_one(row)
            inserted = True
            await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
                'document_id': key, 'solver_id': solver_key(record), 'action': 'uploaded',
                'by_user_id': user['id'], 'by_role': user['role'], 'timestamp': now()})
            await db.solver_documents.update_one({'id': key, 'tenant_id': tenant_of(user)}, {'$set': {'publication_state': 'Ready'}})
    except HTTPException:
        if not inserted:
            path.unlink(missing_ok=True)
        raise
    except Exception:
        raise HTTPException(503, 'Solver document upload requires administrator recovery; refresh before retrying')
    return metadata(row)


async def download(db, user, reference, document_id):
    record = await authorize_solver(db, user, reference)
    doc = await find_linked_record(db.solver_documents, document_id, user)
    if doc.get('solver_id') not in solver_aliases(record) or doc.get('deleted_at'):
        raise HTTPException(404, 'Document not found')
    if not visible(doc, user):
        raise HTTPException(403, 'This document has not been shared with your role')
    return await download_authorized_file(db, user, record, doc)


async def download_authorized_file(db, user, record, doc):
    # Internal storage adapter. Callers must establish document ownership/visibility.
    if doc.get('publication_state') != 'Ready' or doc.get('scan_status') != 'Clean':
        raise HTTPException(503, 'Document requires administrator review')
    from routes.documents import UPLOAD_ROOT
    try:
        if not isinstance(doc.get('stored_path'), str) or not doc['stored_path']:
            raise ValueError()
        path = Path(doc['stored_path']).resolve()
    except (ValueError, OSError, RuntimeError):
        raise HTTPException(404, 'Document file unavailable')
    if not path.is_relative_to((UPLOAD_ROOT / 'solvers' / str(record['_id'])).resolve()) or not path.is_file():
        raise HTTPException(404, 'Document file unavailable')
    await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
        'document_id': str(doc.get('id') or doc['_id']), 'solver_id': solver_key(record),
        'action': 'downloaded', 'by_user_id': user['id'], 'by_role': user['role'], 'timestamp': now()})
    return FileResponse(path, media_type=MIME.get(path.suffix.lower(), 'application/octet-stream'),
                        filename=doc.get('file_name') or 'Document', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
