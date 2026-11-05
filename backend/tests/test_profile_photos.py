from io import BytesIO
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from PIL import Image
from utils import profile_photos as service
from .test_profile_self_service import fixture, run


def photo(content=None, name='photo.png', mime='image/png'):
    if content is None:
        out = BytesIO(); Image.new('RGB', (20, 30), 'red').save(out, 'PNG'); content = out.getvalue()
    return UploadFile(filename=name, file=BytesIO(content), headers=Headers({'content-type': mime}))


def test_photo_upload_scans_audits_and_isolates_employee(tmp_path):
    db, users = fixture()
    with patch.object(service, 'scan_content', new=AsyncMock()) as scan:
        result = run(service.upload(db, users['staff'], photo(), True, tmp_path))
    assert result['id'] and scan.await_count == 1
    path = run(service.current(db, users['staff'], tmp_path))
    assert path.suffix == '.jpg' and Image.open(path).format == 'JPEG'
    assert db.document_audit.docs[0]['action'] == 'profile_photo_uploaded'
    with pytest.raises(HTTPException) as error: run(service.current(db, users['other'], tmp_path))
    assert error.value.status_code == 404
    assert db.employees.writes == 0


@pytest.mark.parametrize('file,consent,status', [(lambda: photo(), False, 422),
    (lambda: photo(b'x' * (service.MAX_PHOTO_BYTES + 1)), True, 413),
    (lambda: photo(b'not an image'), True, 400),
    (lambda: photo(b'%PDF-1.4\n%%EOF', 'file.pdf', 'application/pdf'), True, 400)])
def test_photo_validation_does_not_publish(file, consent, status, tmp_path):
    db, users = fixture()
    with pytest.raises(HTTPException) as error: run(service.upload(db, users['staff'], file(), consent, tmp_path))
    assert error.value.status_code == status and not db.employee_documents.docs


def test_scanner_failure_stores_no_photo(tmp_path):
    db, users = fixture()
    with patch.object(service, 'scan_content', new=AsyncMock(side_effect=HTTPException(503, 'Scanner unavailable'))):
        with pytest.raises(HTTPException): run(service.upload(db, users['staff'], photo(), True, tmp_path))
    assert not db.employee_documents.docs and not list(tmp_path.rglob('*.jpg'))


def test_legacy_employee_link_and_storage_escape(tmp_path):
    db, users = fixture(); users['staff']['employee_id'] = str(db.employees.docs[0]['_id'])
    with patch.object(service, 'scan_content', new=AsyncMock()): run(service.upload(db, users['staff'], photo(), True, tmp_path))
    assert run(service.current(db, users['staff'], tmp_path)).is_file()
    db.employee_documents.docs[0]['stored_path'] = str(tmp_path.parent / 'outside.jpg')
    with pytest.raises(HTTPException): run(service.current(db, users['staff'], tmp_path))


def test_audit_failure_keeps_photo_unpublished(tmp_path):
    db, users = fixture()
    with patch.object(service, 'scan_content', new=AsyncMock()), patch.object(db.document_audit, 'insert_one', side_effect=RuntimeError('Synthetic audit outage')):
        with pytest.raises(RuntimeError): run(service.upload(db, users['staff'], photo(), True, tmp_path))
    assert db.employee_documents.docs[0]['publication_state'] == 'Pending_Audit'
    with pytest.raises(HTTPException): run(service.current(db, users['staff'], tmp_path))


def test_oversized_dimensions_rejected_before_scan(tmp_path):
    db, users = fixture(); out = BytesIO(); Image.new('RGB', (2100, 2100)).save(out, 'PNG')
    with patch.object(service, 'scan_content', new=AsyncMock()) as scan:
        with pytest.raises(HTTPException) as error: run(service.upload(db, users['staff'], photo(out.getvalue()), True, tmp_path))
    assert error.value.status_code == 400 and scan.await_count == 0
