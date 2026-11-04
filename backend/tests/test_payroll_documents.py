import asyncio
from io import BytesIO
from copy import deepcopy
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from openpyxl import Workbook
from utils import payroll_documents as service
from utils.document_uploads import MIME
from .test_profile_self_service import fixture

def run(coro): return asyncio.run(coro)

def workbook(name='payroll.xlsx', content=None):
    if content is None:
        output = BytesIO(); book = Workbook(); book.active.append(['Synthetic employee', 'Amount']); book.save(output); content = output.getvalue()
    return UploadFile(filename=name, file=BytesIO(content), headers=Headers({'content-type': MIME['.xlsx']}))

@pytest.mark.parametrize('actor', ['staff', 'manager', 'other', 'finance'])
def test_payroll_files_are_hr_only_for_all_operations(actor, tmp_path):
    db, users = fixture()
    for operation in (service.listing(db, users[actor]), service.upload(db, users[actor], workbook(), tmp_path), service.download(db, users[actor], 'forged', tmp_path)):
        with pytest.raises(HTTPException) as error: run(operation)
        assert error.value.status_code == 403
    assert not list(tmp_path.iterdir()) and db.employee_documents.writes == 0

def test_scanned_workbook_upload_preserves_all_employees_and_is_never_shared(tmp_path):
    db, users = fixture(); before = deepcopy(db.employees.docs)
    with patch('utils.document_uploads.scan_content', new=AsyncMock()) as scanner:
        result = run(service.upload(db, users['hr'], workbook(), tmp_path))
    assert scanner.await_count == 1
    assert result['download_allowed'] and 'stored_path' not in result
    stored = db.employee_documents.docs[0]
    assert stored['employee_id'] is None and stored['confidential'] is True
    assert stored['visibility'] == 'hr_only' and stored['scan_status'] == 'Clean'
    assert db.employees.docs == before and db.employees.writes == db.users.writes == 0
    assert run(service.listing(db, users['hr']))[0]['id'] == result['id']
    path, name = run(service.download(db, users['hr'], result['id'], tmp_path))
    assert path.is_file() and name == 'payroll.xlsx'
    assert {r['action'] for r in db.document_audit.docs} == {'payroll_workbook.uploaded', 'payroll_workbook.downloaded'}

@pytest.mark.parametrize('name,content,status', [('bad.xlsm', b'bad', 400), ('bad.xlsx', b'bad', 400), ('../payroll.xlsx', b'bad', 400), ('huge.xlsx', b'0' * (5 * 1024 * 1024 + 1), 413)], ids=['macro', 'invalid', 'path', 'oversized'])
def test_unsafe_or_oversized_files_are_rejected_without_storage(name, content, status, tmp_path):
    db, users = fixture()
    with pytest.raises(HTTPException) as error: run(service.upload(db, users['hr'], workbook(name, content), tmp_path))
    assert error.value.status_code == status
    assert not list(tmp_path.iterdir()) and db.employee_documents.writes == 0

def test_scanner_outage_fails_closed_and_does_not_store_file(tmp_path):
    db, users = fixture()
    with patch('utils.document_uploads.scan_content', new=AsyncMock(side_effect=HTTPException(503, 'Scanner unavailable'))):
        with pytest.raises(HTTPException) as error: run(service.upload(db, users['hr'], workbook(), tmp_path))
    assert error.value.status_code == 503
    assert db.employee_documents.writes == 0 and not list(tmp_path.iterdir())

def test_wrong_tenant_employee_document_and_storage_escape_cannot_download(tmp_path):
    db, users = fixture()
    with patch('utils.document_uploads.scan_content', new=AsyncMock()):
        result = run(service.upload(db, users['hr'], workbook(), tmp_path))
    with pytest.raises(HTTPException): run(service.download(db, {**users['hr'], 'tenant_id': 'other'}, result['id'], tmp_path))
    stored = db.employee_documents.docs[0]
    stored['stored_path'] = str(tmp_path.parent / 'outside.xlsx')
    with pytest.raises(HTTPException) as error: run(service.download(db, users['hr'], result['id'], tmp_path))
    assert error.value.status_code == 404
    stored['document_kind'] = 'employee_document'
    with pytest.raises(HTTPException): run(service.download(db, users['hr'], result['id'], tmp_path))

def test_unpublished_upload_never_downloads_when_audit_fails(tmp_path):
    db, users = fixture()
    with patch('utils.document_uploads.scan_content', new=AsyncMock()), patch.object(db.document_audit, 'insert_one', side_effect=RuntimeError('synthetic audit outage')):
        with pytest.raises(HTTPException): run(service.upload(db, users['hr'], workbook(), tmp_path))
    assert db.employee_documents.docs[0]['publication_state'] == 'Pending_Audit'
    assert run(service.listing(db, users['hr']))[0]['download_allowed'] is False

def test_employee_document_endpoint_cannot_expose_payroll_workbook(tmp_path):
    from routes import documents
    db, users = fixture()
    with patch('utils.document_uploads.scan_content', new=AsyncMock()):
        result = run(service.upload(db, users['hr'], workbook(), tmp_path))
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', new=AsyncMock(return_value=users['staff'])):
        with pytest.raises(HTTPException) as error: run(documents.download_document(result['id'], None))
    assert error.value.status_code == 403
