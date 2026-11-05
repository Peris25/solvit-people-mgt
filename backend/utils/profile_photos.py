"""Self-only profile photos using scanned private document storage."""
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
import os
import uuid
from PIL import Image, ImageOps
from fastapi import HTTPException
from utils.document_uploads import filename, validate_content, scan_content
from utils.profile_self_service import self_employee
from utils.employee_integrity import employee_key, tenant_of, integrity_write

MAX_PHOTO_BYTES = 2 * 1024 * 1024


async def upload(db, user, file, consent, root):
    employee = await self_employee(db, user)
    if consent is not True:
        raise HTTPException(422, 'Confirm that you want to use this image as your private profile photo')
    _, ext = filename(file.filename)
    if ext not in {'.jpg', '.jpeg', '.png'}:
        raise HTTPException(400, 'Choose a JPG or PNG photo')
    content = await file.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(413, 'Profile photos must be 2 MB or smaller')
    validate_content(content, ext, file.content_type)
    with Image.open(BytesIO(content)) as dimensions:
        if dimensions.width * dimensions.height > 4_000_000:
            raise HTTPException(400, 'Choose a photo no larger than 4 megapixels')
    await scan_content(content)
    # Re-encode a bounded image, removing original metadata and active payloads.
    with Image.open(BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((512, 512))
        output = BytesIO()
        image.save(output, format='JPEG', quality=85)
    root = Path(root).resolve()
    folder = root / 'profile_photos'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    reference = str(uuid.uuid4())
    path = (folder / (reference + '.jpg')).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(409, 'Photo storage needs administrator review')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as target:
        target.write(output.getvalue())
    now = datetime.now(timezone.utc).isoformat()
    row = {'id': reference, 'tenant_id': tenant_of(user), 'employee_id': employee_key(employee),
           'category': 'Profile photo', 'file_name': 'Profile photo.jpg', 'stored_path': str(path),
           'content_type': 'image/jpeg', 'size_bytes': len(output.getvalue()), 'scan_status': 'Clean',
           'publication_state': 'Pending_Audit', 'visibility': 'hr_employee', 'confidential': False,
           'uploaded_at': now, 'uploaded_by': user['id'], 'photo_consent_at': now, 'deleted_at': None}
    async with integrity_write(db):
        await self_employee(db, user)
        await db.employee_documents.insert_one(row)
        await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
            'document_id': reference, 'employee_id': employee_key(employee), 'action': 'profile_photo_uploaded',
            'by_user_id': user['id'], 'timestamp': now})
        await db.employee_documents.update_one({'id': reference, 'tenant_id': tenant_of(user)}, {'$set': {'publication_state': 'Ready'}})
    return {'id': reference}


async def current(db, user, root):
    employee = await self_employee(db, user)
    rows = await db.employee_documents.find({'tenant_id': tenant_of(user), 'employee_id': employee_key(employee),
        'category': 'Profile photo', 'uploaded_by': user['id'], 'publication_state': 'Ready',
        'scan_status': 'Clean', 'deleted_at': None}).sort('uploaded_at', -1).to_list(1)
    if not rows:
        raise HTTPException(404, 'No profile photo uploaded')
    path = Path(rows[0]['stored_path']).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise HTTPException(404, 'Profile photo unavailable')
    await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
        'document_id': rows[0]['id'], 'employee_id': employee_key(employee),
        'action': 'profile_photo_viewed', 'by_user_id': user['id'],
        'timestamp': datetime.now(timezone.utc).isoformat()})
    return path


async def remove(db, user):
    employee = await self_employee(db, user)
    scope = {'tenant_id': tenant_of(user), 'employee_id': employee_key(employee),
             'category': 'Profile photo', 'uploaded_by': user['id'], 'deleted_at': None}
    async with integrity_write(db):
        await self_employee(db, user)
        rows = await db.employee_documents.find(scope).to_list(None)
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            await db.document_audit.insert_one({'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user),
                'document_id': row['id'], 'employee_id': employee_key(employee),
                'action': 'profile_photo_removed', 'by_user_id': user['id'], 'timestamp': now})
            await db.employee_documents.update_one({**scope, 'id': row['id']},
                {'$set': {'deleted_at': now, 'deleted_by': user['id']}})
    return {'removed': True}
