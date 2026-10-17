"""Task 08: synthetic uploads, ownership, scanning and private-store boundaries."""
import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

import pytest
from bson import ObjectId
from fastapi import HTTPException, UploadFile
from PIL import Image

from routes import documents, policies
from utils import document_uploads as validation
from utils.employee_access import find_linked_record
from .test_profile_self_service import fixture, run
from .integrity_fakes import Collection

PDF = b'%PDF-1.7\nSynthetic test document\n%%EOF'


def image(kind):
    content = BytesIO(); Image.new('RGB', (2, 2), 'white').save(content, kind); return content.getvalue()


def office(ext, extra=None):
    content = BytesIO()
    folder, part, kind = ('word', 'document', 'wordprocessingml.document') if ext == '.docx' else ('xl', 'workbook', 'spreadsheetml.sheet')
    with ZipFile(content, 'w') as archive:
        archive.writestr('[Content_Types].xml', f'<Types><Override ContentType="application/vnd.openxmlformats-officedocument.{kind}.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships/>')
        archive.writestr(f'{folder}/{part}.xml', f'<{part}/>')
        for name, value in (extra or {}).items(): archive.writestr(name, value)
    return content.getvalue()


@pytest.mark.parametrize('name,content,mime', [('contract.pdf', PDF, 'application/pdf'), ('image.jpg', image('JPEG'), 'image/jpeg'), ('image.png', image('PNG'), 'image/png'), ('letter.docx', office('.docx'), validation.MIME['.docx']), ('record.xlsx', office('.xlsx'), validation.MIME['.xlsx'])])
def test_supported_files_are_validated_scanned_assigned_privately_and_audited(tmp_path, name, content, mime):
    db, actors = fixture()
    file = UploadFile(BytesIO(content), filename=name, headers={'content-type': mime})
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(documents, 'UPLOAD_ROOT', tmp_path), patch.object(documents, '_get_categories', AsyncMock(return_value=['Other'])), patch.object(documents, 'scan_content', AsyncMock()) as scan:
        result = run(documents.upload_document(str(db.employees.docs[0]['_id']), None, file, 'Other', None, 'hr_only', True))
    saved = db.employee_documents.docs[0]
    assert saved['employee_id'] == 'staff' and saved['publication_state'] == 'Ready' and saved['scan_status'] == 'Clean'
    assert saved['confidential'] is True and saved['visibility'] == 'hr_only'
    assert 'stored_path' not in result and db.document_audit.docs[0]['action'] == 'uploaded'
    assert len(list(tmp_path.rglob('*.*'))) == 1
    scan.assert_awaited_once_with(content)


@pytest.mark.parametrize('name', ['../secret.pdf', '..\\secret.pdf', 'C:secret.pdf', 'bad\r\n.pdf', 'malware.exe', ''])
def test_unsafe_filenames(name):
    with pytest.raises(HTTPException): validation.filename(name)


@pytest.mark.parametrize('ext,content,mime', [('.pdf', b'<html>spoof</html>', 'application/pdf'), ('.pdf', PDF, 'text/html'), ('.png', image('JPEG'), 'image/png'), ('.docx', office('.xlsx'), validation.MIME['.docx']), ('.xlsx', b'PKinvalid', validation.MIME['.xlsx']), ('.docx', office('.docx', {'../evil': b'bad'}), validation.MIME['.docx']), ('.docx', office('.docx', {'word/vbaProject.bin': b'macro'}), validation.MIME['.docx']), ('.docx', office('.docx', {'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="file:///private"/></Relationships>'}), validation.MIME['.docx'])])
def test_spoofed_and_unsafe_content(ext, content, mime):
    with pytest.raises(HTTPException) as error: validation.validate_content(content, ext, mime)
    assert error.value.status_code == 400


def test_exact_20mb_boundary_and_empty_oversized_uploads():
    assert len(run(validation.read_bounded(UploadFile(BytesIO(b'x' * validation.MAX_BYTES), filename='file.pdf')))) == validation.MAX_BYTES
    for content, status in [(b'', 400), (b'x' * (validation.MAX_BYTES + 1), 413)]:
        with pytest.raises(HTTPException) as error: run(validation.read_bounded(UploadFile(BytesIO(content), filename='file.pdf')))
        assert error.value.status_code == status


@pytest.mark.parametrize('reply,status', [(b'stream: OK\0', None), (b'stream: Synthetic-Test FOUND\0', 422), (b'stream: ERROR\0', 503)])
def test_scanner_protocol_verdicts_fail_closed(monkeypatch, reply, status):
    monkeypatch.setenv('DOC_SCANNER_HOST', 'synthetic-scanner.invalid')
    reader = SimpleNamespace(readuntil=AsyncMock(return_value=reply))
    writer = MagicMock(); writer.drain = AsyncMock(); writer.wait_closed = AsyncMock()
    with patch.object(validation.asyncio, 'open_connection', AsyncMock(return_value=(reader, writer))):
        if status:
            with pytest.raises(HTTPException) as error: run(validation.scan_content(PDF))
            assert error.value.status_code == status
        else: run(validation.scan_content(PDF))
    assert writer.write.call_args_list[0].args[0] == b'zINSTREAM\0'
    assert writer.write.call_args_list[-1].args[0] == b'\0\0\0\0'
    writer.close.assert_called_once()


def test_missing_scanner_blocks_upload_without_writes(tmp_path, monkeypatch):
    monkeypatch.delenv('DOC_SCANNER_HOST', raising=False)
    db, actors = fixture()
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(documents, 'UPLOAD_ROOT', tmp_path), patch.object(documents, '_get_categories', AsyncMock(return_value=['Other'])):
        with pytest.raises(HTTPException) as error: run(documents.upload_document('staff', None, UploadFile(BytesIO(PDF), filename='file.pdf'), 'Other', None, 'hr_only', True))
    assert error.value.status_code == 503 and db.employee_documents.writes == 0 and list(tmp_path.iterdir()) == []


def doc(db, **values):
    record = {'_id': ObjectId(), 'id': 'doc', 'tenant_id': 'solvit', 'employee_id': 'staff', 'category': 'Other', 'file_name': 'document.pdf', 'publication_state': 'Ready', 'visibility': 'hr_employee', 'confidential': False, **values}
    db.employee_documents.docs.append(record); return record


def test_metadata_changes_are_hr_scoped_audited_and_cannot_change_ownership():
    db, actors = fixture(); doc(db)
    request = SimpleNamespace(json=AsyncMock(return_value={'title': 'Approved title', 'visibility': 'hr_employee'}))
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])):
        result = run(documents.update_document('doc', request))
        request.json.return_value = {'employee_id': 'other'}
        with pytest.raises(HTTPException): run(documents.update_document('doc', request))
    assert result['title'] == 'Approved title' and db.employee_documents.docs[0]['employee_id'] == 'staff'
    assert db.document_audit.docs[0]['action'] == 'changed'
    assert db.document_audit.docs[0]['before']['title'] is None
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        with pytest.raises(HTTPException): run(documents.update_document('doc', request))


def test_sensitive_classification_cannot_be_removed_to_publish_a_medical_document():
    db, actors = fixture(); doc(db, category='Medical letter')
    request = SimpleNamespace(json=AsyncMock(return_value={'category': 'Other', 'confidential': False, 'visibility': 'hr_employee'}))
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(documents, '_get_categories', AsyncMock(return_value=['Other'])):
        run(documents.update_document('doc', request))
    record = db.employee_documents.docs[0]
    assert record['restricted'] is True and record['confidential'] is True
    assert documents._visible(record, db.employees.docs[0], actors['staff']) is False


@pytest.mark.parametrize('reference', ['native-id', 'storage-id', 'string-storage'])
def test_legacy_document_ids_resolve_without_rewrites(reference):
    db, actors = fixture(); storage = ObjectId(); canonical = ObjectId()
    record = doc(db, _id=str(storage) if reference == 'string-storage' else storage, id=canonical if reference == 'native-id' else 'canonical')
    key = str(canonical) if reference == 'native-id' else str(storage)
    found = run(find_linked_record(db.employee_documents, key, actors['staff']))
    assert found == record and db.employee_documents.writes == 0


def test_me_endpoint_never_accepts_client_employee_and_redacts_paths():
    db, actors = fixture(); doc(db, stored_path='PRIVATE', file_name='C:\\private\\document.pdf'); doc(db, id='foreign', employee_id='other')
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        result = run(documents.my_documents(None))
    assert len(result) == 1 and result[0]['employee_id'] == 'staff' and result[0]['file_name'] == 'document.pdf'
    assert 'PRIVATE' not in str(result) and 'stored_path' not in str(result)


def test_interrupted_metadata_write_blocks_publication_and_retains_lock():
    db, actors = fixture(); doc(db)
    request = SimpleNamespace(json=AsyncMock(return_value={'title': 'Updated'}))
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(db.document_audit, 'insert_one', AsyncMock(side_effect=RuntimeError('Synthetic failure'))):
        with pytest.raises(RuntimeError): run(documents.update_document('doc', request))
    assert db.employee_documents.docs[0]['publication_state'] == 'Pending_Audit' and len(db.integrity_locks.docs) == 1
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        assert run(documents.list_employee_documents('staff', None)) == []
        with pytest.raises(HTTPException): run(documents.download_document('doc', None))


def test_policy_download_cannot_serve_employee_private_files_or_expose_disk_paths(tmp_path):
    db, actors = fixture(); db.policies = Collection(); private = tmp_path/'private.pdf'; private.write_bytes(PDF)
    db.policies.docs = [{'_id': ObjectId(), 'id': 'policy', 'tenant_id': 'solvit', 'status': 'Active', 'applies_to': ['all'], 'file_url': str(private)}]
    with patch.object(policies, 'get_db', return_value=db), patch.object(policies, 'get_current_user', AsyncMock(return_value=actors['staff'])), patch.object(policies, 'UPLOAD_ROOT', tmp_path/'policies'):
        with pytest.raises(HTTPException): run(policies.download_policy_file('policy', None))
        assert 'file_url' not in run(policies.get_policy('policy', None))


def test_policy_metadata_cannot_point_at_a_private_document():
    db, actors = fixture()
    request = SimpleNamespace(json=AsyncMock(return_value={'file_url': '/private/employee.pdf'}))
    with patch.object(policies, 'get_db', return_value=db), patch.object(policies, 'get_current_user', AsyncMock(return_value=actors['hr'])):
        with pytest.raises(HTTPException) as error: run(policies.update_policy('policy', request))
    assert error.value.status_code == 422


@pytest.mark.parametrize('role', ['employee', 'line_manager', 'finance', 'it_admin'])
def test_non_hr_cannot_upload_or_assign_files(role):
    db, actors = fixture(); actor = {**actors['staff'], 'role': role}
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actor)):
        with pytest.raises(HTTPException) as error:
            run(documents.upload_document('other', None, UploadFile(BytesIO(PDF), filename='file.pdf'), 'Other', None, 'hr_only', True))
    assert error.value.status_code == 403 and db.employee_documents.writes == 0


def test_http_download_returns_only_the_authorized_employees_file(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from server import app
    from utils import auth
    db, actors = fixture(); path = tmp_path/'document.pdf'; path.write_bytes(PDF)
    doc(db, stored_path=str(path)); doc(db, id='other-doc', employee_id='other', stored_path=str(path))
    monkeypatch.setenv('JWT_SECRET', 'synthetic-task08-http-signing-key-only')
    token = auth.create_access_token(actors['staff']['id'], actors['staff']['email'], 'employee')
    with patch('database.get_db', return_value=db), patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'UPLOAD_ROOT', tmp_path):
        client = TestClient(app, base_url='http://127.0.0.1:18089')  # No application lifespan/DB connection.
        try:
            headers = {'Authorization': 'Bearer ' + token}
            assert len(client.get('/api/documents/me?employee_id=other', headers=headers).json()) == 1
            response = client.get('/api/documents/doc/download', headers=headers)
            assert response.status_code == 200 and response.content == PDF
            assert 'attachment' in response.headers['content-disposition'] and response.headers['cache-control'] == 'no-store'
            assert client.get('/api/documents/other-doc/download', headers=headers).status_code == 403
        finally: client.close()
    assert db.document_audit.docs[0]['action'] == 'downloaded'


def test_exited_employee_cannot_bypass_me_restriction_using_direct_download():
    db, actors = fixture(); db.employees.docs[0]['lifecycle_state'] = 'Exited'; doc(db)
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        with pytest.raises(HTTPException) as error: run(documents.download_document('doc', None))
        assert error.value.status_code == 403
        with pytest.raises(HTTPException): run(documents.list_employee_documents('staff', None))


@pytest.mark.parametrize('status', [422, 503])
def test_rejected_or_failed_scan_never_creates_a_file_or_document(tmp_path, status):
    db, actors = fixture()
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(documents, 'UPLOAD_ROOT', tmp_path), patch.object(documents, '_get_categories', AsyncMock(return_value=['Other'])), patch.object(documents, 'scan_content', AsyncMock(side_effect=HTTPException(status, 'Synthetic scan denial'))):
        with pytest.raises(HTTPException): run(documents.upload_document('staff', None, UploadFile(BytesIO(PDF), filename='file.pdf'), 'Other', None, 'hr_only', True))
    assert db.employee_documents.writes == 0 and list(tmp_path.iterdir()) == []


def test_legacy_document_without_business_id_downloads_and_missing_file_is_safe(tmp_path):
    db, actors = fixture(); path = tmp_path/'legacy.pdf'; path.write_bytes(PDF)
    record = doc(db, stored_path=str(path)); record.pop('id')
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])), patch.object(documents, 'UPLOAD_ROOT', tmp_path):
        result = run(documents.download_document(str(record['_id']), None))
        assert result.headers['cache-control'] == 'no-store'
        record.pop('stored_path')
        with pytest.raises(HTTPException) as error: run(documents.download_document(str(record['_id']), None))
        assert error.value.status_code == 404
    assert db.document_audit.docs[0]['document_id'] == str(record['_id'])
