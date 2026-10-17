"""Task 07 synthetic profile, approval and document isolation regressions."""
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
from utils import profile_self_service as service
from routes import employees, documents
from .integrity_fakes import Database, Collection, employee, account


def run(coro): return asyncio.run(coro)


def fixture():
    records = [employee(key, key + '@example.com', start_date='2020-01-01', department='Operations',
                        line_manager_id='manager' if key == 'staff' else None)
               for key in ('staff', 'other', 'hr', 'finance', 'manager')]
    users = [account(row['work_email'], employee_id=row['id'], role={'hr': 'hr_admin', 'finance': 'finance', 'manager': 'line_manager'}.get(row['id'], 'employee')) for row in records]
    db = Database(records, users)
    for name in ('employee_profile_changes', 'employee_documents', 'document_audit', 'performance_reviews', 'leave_requests', 'recognitions', 'training_requests', 'idps', 'disciplinary_cases', 'notifications', 'benefit_schemes', 'benefit_requests'):
        setattr(db, name, Collection())
    actors = {u['employee_id']: {**u, 'id': str(u['_id'])} for u in users}
    return db, actors


@pytest.mark.parametrize('field', ['department', 'current_salary_kes', 'role', 'role_title', 'role_level', 'line_manager_id', 'employment_type', 'lifecycle_state', 'work_email', 'password_hash', 'tenant_id', 'employee_id', 'profile_photo_url'])
def test_restricted_fields_cannot_be_requested(field):
    db, actors = fixture()
    with pytest.raises(HTTPException) as error: run(service.submit(db, actors['staff'], {field: 'forged'}))
    assert error.value.status_code == 422 and db.employees.writes == db.employee_profile_changes.writes == 0


@pytest.mark.parametrize('changes', [{'personal_email': 'bad-address'}, {'phone_number': '-------'}, {'date_of_birth': '2099-01-01'}, {'full_name': ''}, {'preferred_name': 'unsafe\nline'}, {'next_of_kin': {'password': 'secret'}}, {'education': [{'year': 'yesterday'}]}, {'phone_number': None}])
def test_field_validation(changes):
    with pytest.raises(HTTPException): service.validate_changes(changes)


def test_request_preserves_employee_until_hr_approval_and_keeps_history():
    db, actors = fixture(); saved = deepcopy(db.employees.docs[0])
    row = run(service.submit(db, actors['staff'], {'personal_email': '  personal@example.com  '}))
    assert row['status'] == 'Pending_HR' and db.employees.docs[0] == saved
    with pytest.raises(HTTPException): run(service.decide(db, actors['staff'], row['id'], 'Approve'))
    with pytest.raises(HTTPException): run(service.decide(db, actors['manager'], row['id'], 'Approve'))
    result = run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    assert result['status'] == 'Approved' and db.employees.docs[0]['personal_email'] == 'personal@example.com'
    assert db.employees.docs[0]['work_email'] == saved['work_email']
    assert db.employee_profile_changes.docs[0]['before']['personal_email'] is None
    assert run(service.list_changes(db, actors['other'])) == []


def test_bank_changes_wait_for_independent_finance_and_finance_sees_only_bank_fields():
    db, actors = fixture()
    row = run(service.submit(db, actors['staff'], {'bank_account_number': '0012345', 'personal_email': 'personal@example.com'}))
    with pytest.raises(HTTPException): run(service.decide(db, actors['finance'], row['id'], 'Approve'))
    assert run(service.decide(db, actors['hr'], row['id'], 'Approve'))['status'] == 'Pending_Finance'
    assert 'bank_account_number' not in db.employees.docs[0]
    visible = run(service.list_changes(db, actors['finance'], 'staff'))
    assert visible[0]['changes'] == {'bank_account_number': '0012345'}
    result = run(service.decide(db, actors['finance'], row['id'], 'Approve'))
    assert result['status'] == 'Approved' and db.employees.docs[0]['bank_account_number'] == '0012345'
    assert '0012345' not in str(db.audit_logs.docs)


def test_stale_changes_cannot_overwrite_hr_edit_but_can_be_rejected():
    db, actors = fixture(); row = run(service.submit(db, actors['staff'], {'phone_number': '+254700000001'}))
    db.employees.docs[0]['phone_number'] = '+254700000002'
    with pytest.raises(HTTPException) as error: run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    assert error.value.status_code == 409
    result = run(service.decide(db, actors['hr'], row['id'], 'Reject', 'Saved contact has changed'))
    assert result['status'] == 'Rejected' and db.employees.docs[0]['phone_number'] == '+254700000002'


def test_legacy_identity_resolution_and_no_duplicate_pending_request():
    db, actors = fixture(); actor = {**actors['staff'], 'employee_id': str(db.employees.docs[0]['_id'])}
    row = run(service.submit(db, actor, {'preferred_name': 'Ada'}))
    assert row['employee_id'] == 'staff'
    with pytest.raises(HTTPException): run(service.submit(db, actors['staff'], {'preferred_name': 'Other'}))
    assert len(db.employee_profile_changes.docs) == 1


def test_hr_self_approval_and_cross_tenant_review_are_denied():
    db, actors = fixture(); row = run(service.submit(db, actors['hr'], {'preferred_name': 'New name'}))
    with pytest.raises(HTTPException): run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    foreign = {**actors['hr'], 'tenant_id': 'foreign'}
    with pytest.raises(HTTPException): run(service.decide(db, foreign, row['id'], 'Approve'))
    assert db.employees.writes == 0


def test_my_profile_redacts_secrets_and_resolves_legacy_history_with_tenant_scope():
    db, actors = fixture(); emp = db.employees.docs[0]
    emp.update(password_hash='PRIVATE', refresh_token='PRIVATE', medical_notes='PRIVATE', profile_photo_url='https://unapproved.invalid/photo',
               next_of_kin={'name': 'Synthetic contact', 'token': 'PRIVATE'})
    db.leave_requests.docs = [{'id': 'legacy', '_id': ObjectId(), 'employee_id': emp['_id'], 'tenant_id': 'solvit', 'leave_type': 'Annual', 'status': 'Approved'},
                              {'id': 'foreign', '_id': ObjectId(), 'employee_id': 'staff', 'tenant_id': 'foreign', 'leave_type': 'PRIVATE', 'status': 'Approved'}]
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        result = run(employees.get_my_profile(None))
    assert result['employee']['line_manager_name'] == 'manager'
    assert len(result['leave_history']) == 1
    assert 'PRIVATE' not in str(result) and 'profile_photo_url' not in result['employee']


@pytest.mark.parametrize('visibility,confidential,category,allowed', [('hr_employee', False, 'Signed Employment Contract', True), ('hr_only', False, 'Other', False), (None, False, 'Other', False), ('hr_employee', True, 'Other', False), ('hr_employee_manager', False, 'Medical Letter', False), ('hr_employee', False, 'Payslip', False)])
def test_document_visibility_is_conservative(visibility, confidential, category, allowed):
    db, actors = fixture(); doc = {'visibility': visibility, 'confidential': confidential, 'category': category}
    assert documents._visible(doc, db.employees.docs[0], actors['staff']) is allowed
    assert documents._visible(doc, db.employees.docs[0], actors['hr']) is True


def test_document_legacy_ownership_download_scope_and_safe_path(tmp_path):
    db, actors = fixture(); emp = db.employees.docs[0]; path = tmp_path/'document.pdf'; path.write_bytes(b'%PDF-1.7 synthetic')
    db.employee_documents.docs = [{'_id': ObjectId(), 'id': 'doc', 'employee_id': str(emp['_id']), 'tenant_id': 'solvit', 'stored_path': str(path), 'visibility': 'hr_employee', 'confidential': False, 'category': 'Signed Employment Contract'}]
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'UPLOAD_ROOT', tmp_path):
        with patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['staff'])):
            assert len(run(documents.list_employee_documents('staff', None))) == 1
            assert run(documents.download_document('doc', None)).headers['cache-control'] == 'no-store'
            db.employee_documents.docs[0]['stored_path'] = str(tmp_path.parent/'outside.pdf')
            with pytest.raises(HTTPException): run(documents.download_document('doc', None))
        with patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['other'])):
            with pytest.raises(HTTPException): run(documents.download_document('doc', None))
        db.employee_documents.docs[0]['visibility'] = 'hr_employee_manager'
        with patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['manager'])):
            assert len(run(documents.list_employee_documents('staff', None))) == 1
    assert db.document_audit.docs[0]['action'] == 'downloaded'


def test_profile_request_cannot_supply_another_employee_identity():
    db, actors = fixture()
    request = SimpleNamespace(json=AsyncMock(return_value={'employee_id': 'other', 'changes': {'preferred_name': 'Forged'}}))
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value=actors['staff'])):
        with pytest.raises(HTTPException): run(employees.request_profile_change(request))
    assert db.employee_profile_changes.writes == db.employees.writes == 0


@pytest.mark.parametrize('changes', [{'department': 'Other'}, {'role_level': 'L5'}, {'employment_type': 'Consultant'}, {'lifecycle_state': 'Exiting'}, {'current_salary_kes': 999999}])
def test_manager_cannot_change_hr_controlled_fields(changes):
    db, actors = fixture()
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value=actors['manager'])):
        with pytest.raises(HTTPException): run(employees.update_employee('staff', employees.EmployeeUpdate(**changes), None))
    assert db.employees.writes == 0


def test_explicit_runtime_revocation_blocks_profile_read_and_review(monkeypatch):
    from utils.access_matrix import RUNTIME_OVERRIDES
    db, actors = fixture()
    monkeypatch.setitem(RUNTIME_OVERRIDES, ('M01', 'employee'), None)
    with pytest.raises(HTTPException): run(service.self_employee(db, actors['staff']))
    monkeypatch.setitem(RUNTIME_OVERRIDES, ('M01', 'hr_admin'), None)
    with pytest.raises(HTTPException): run(service.reviewer(db, actors['hr'], 'staff'))


def test_interrupted_application_retains_applying_state_and_integrity_lock():
    db, actors = fixture(); row = run(service.submit(db, actors['staff'], {'preferred_name': 'Ada'}))
    with patch.object(db.audit_logs, 'insert_one', AsyncMock(side_effect=RuntimeError('Synthetic audit failure'))):
        with pytest.raises(RuntimeError): run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    assert db.employees.docs[0]['preferred_name'] == 'Ada'
    assert db.employee_profile_changes.docs[0]['status'] == 'Applying'
    assert db.employee_profile_changes.docs[0]['hr_approved_by'] == actors['hr']['id']
    assert len(db.integrity_locks.docs) == 1


def test_hr_removal_preserves_original_document_file(tmp_path):
    db, actors = fixture(); path = tmp_path/'original.pdf'; path.write_bytes(b'Synthetic historical document')
    db.employee_documents.docs = [{'_id': ObjectId(), 'id': 'doc', 'tenant_id': 'solvit', 'employee_id': 'staff', 'stored_path': str(path)}]
    with patch.object(documents, 'get_db', return_value=db), patch.object(documents, 'get_current_user', AsyncMock(return_value=actors['hr'])):
        run(documents.delete_document('doc', None))
    assert path.exists() and db.employee_documents.docs[0]['deleted_at']
    assert len(db.document_audit.docs) == 1


def test_legacy_bank_fields_are_updated_only_after_both_approvals_without_duplicate_fields():
    db, actors = fixture(); db.employees.docs[0]['bank_account'] = '001111'
    assert service.safe_employee(db.employees.docs[0])['bank_account_number'] == '001111'
    row = run(service.submit(db, actors['staff'], {'bank_account_number': '002222'}))
    assert db.employees.docs[0]['bank_account'] == '001111'
    run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    run(service.decide(db, actors['finance'], row['id'], 'Approve'))
    assert db.employees.docs[0]['bank_account'] == '002222' and 'bank_account_number' not in db.employees.docs[0]


def test_education_additions_and_partial_contacts_preserve_saved_details():
    db, actors = fixture(); emp = db.employees.docs[0]
    emp.update(education=[{'institution': 'Existing college', 'qualification': 'Existing diploma'}], next_of_kin={'name': 'Existing contact', 'relationship': 'Sibling'})
    row = run(service.submit(db, actors['staff'], {'education': [{'institution': 'New college', 'qualification': 'Certificate'}], 'next_of_kin': {'phone_number': '+254700000001'}}))
    run(service.decide(db, actors['hr'], row['id'], 'Approve'))
    assert len(db.employees.docs[0]['education']) == 2
    assert db.employees.docs[0]['next_of_kin']['name'] == 'Existing contact'


def test_authenticated_http_profile_cannot_be_retargeted(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app
    from utils import auth
    db, actors = fixture()
    for name in ('user_session_invalidations', 'revoked_refresh_tokens'):
        setattr(db, name, Collection())
    monkeypatch.setenv('JWT_SECRET', 'synthetic-task07-http-signing-secret-only')
    token = auth.create_access_token(actors['staff']['id'], actors['staff']['email'], 'employee')
    with patch('database.get_db', return_value=db), patch.object(employees, 'get_db', return_value=db):
        client = TestClient(app, base_url='http://127.0.0.1:18089')  # No application lifespan/database connection.
        try:
            headers = {'Authorization': 'Bearer ' + token}
            own = client.get('/api/employees/me/profile?employee_id=other', headers=headers)
            assert own.status_code == 200 and own.json()['employee']['id'] == 'staff'
            forged = client.post('/api/employees/me/profile-changes', headers=headers, json={'employee_id': 'other', 'changes': {'preferred_name': 'Forged'}})
            assert forged.status_code == 422
            assert client.get('/api/employees/other/profile', headers=headers).status_code == 403
        finally:
            client.close()


def test_real_mongo_prevents_two_simultaneous_profile_requests():
    from .test_employee_integrity_mongo import local_database
    async def exercise():
        async with local_database() as db:
            fake, actors = fixture()
            await db.employees.insert_many(fake.employees.docs); await db.users.insert_many(fake.users.docs)
            async def submit_one():
                try: return await service.submit(db, actors['staff'], {'preferred_name': 'Ada'})
                except HTTPException as error: return error.status_code
            results = await asyncio.gather(submit_one(), submit_one())
            assert 409 in results and await db.employee_profile_changes.count_documents({}) == 1
            assert (await db.employees.find_one({'id': 'staff'})).get('preferred_name') is None
    run(exercise())
