"""Synthetic Solver directory, evidence, assessment and document regressions."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from bson import ObjectId
from routes import solvers, onboarding, forms, solver_intake
from utils import solver_workflows as service, solver_documents as documents
from utils import solver_access as access, administrative_reporting as reporting
from utils.access_matrix import RUNTIME_OVERRIDES
from .test_solver_security import solver, database, actor, request, run
from .integrity_fakes import Collection, employee, account
from .test_notification_centre import Receipts


def fixture():
    record = solver(lifecycle_state='Registering', region='Coast', area_covered='Test area')
    db = database([record, solver('two', phone_number='+254700000002', county='Central')])
    for name in ('onboarding_tasks', 'solver_verifications', 'form_submissions', 'solver_documents', 'document_audit', 'notifications', 'solver_assessment_reviews'):
        setattr(db, name, Collection())
    db.notifications = Receipts(); db.notification_receipts = Receipts()
    return db, actor(), record


def evidence(db, record, gate):
    category = dict(zip(service.GATES, documents.CATEGORIES))[gate]
    row = {'_id': ObjectId(), 'id': gate, 'tenant_id': 'solvit', 'solver_id': access.solver_key(record),
           'category': category, 'publication_state': 'Ready', 'scan_status': 'Clean',
           'visibility': 'hr_only', 'confidential': True}
    db.solver_documents.docs.append(row)
    return {'gate': gate, 'document_id': gate, 'reference': 'Verified synthetic evidence',
            **({'score': 8, 'maximum': 10} if gate == 'code_quiz' else {'outcome': 'Pass'} if gate == 'vehicle_assessment' else {})}


def routes(db, user):
    return patch.multiple(solvers, get_db=lambda: db, get_current_user=AsyncMock(return_value=user))


@pytest.mark.parametrize('department,allowed', [('Operations', True), ('Account Management', True), ('IT Support', False), ('Valuation', False), ('Leadership', False)])
def test_contact_directory_is_department_scoped_and_redacted(department, allowed):
    db, _, record = fixture()
    person = employee('staff', department=department, employment_type='FTE')
    owner = account(employee_id='staff')
    db.employees.docs.append(person); db.users.docs.append(owner)
    user = {**owner, 'id': str(owner['_id'])}
    record.update(bank_account_number='PRIVATE', national_id_number='PRIVATE', accuracy_score=90)
    db.solvers.docs[0] = deepcopy(record)
    with routes(db, user):
        if not allowed:
            with pytest.raises(HTTPException): run(solvers.list_solvers(request()))
            return
        rows = run(solvers.list_solvers(request()))
        assert len(rows) == 2 and 'PRIVATE' not in str(rows) and 'accuracy_score' not in rows[0]
        assert rows[0]['phone_number'] == record['phone_number']
        assert run(solvers.get_solver_stats(request()))['can_manage'] is False
        with pytest.raises(HTTPException): run(solvers.get_solver('one', request()))
        with pytest.raises(HTTPException): run(solvers.initiate_induction('one', request()))


def test_directory_filters_use_actual_legacy_regions_without_rewriting():
    db, user, _ = fixture(); before = deepcopy(db.solvers.docs)
    db.solvers.docs[0]['vehicle_categories_certified'] = ['SUV']
    before = deepcopy(db.solvers.docs)
    with routes(db, user):
        assert len(run(solvers.list_solvers(request(), region='coast', category='SUV', search='TEST AREA'))) == 1
        assert len(run(solvers.list_solvers(request(), region='Central'))) == 1
        assert run(solvers.list_solvers(request(), search='.*')) == []
        assert run(solvers.directory_options(request()))['regions'] == ['Central', 'Coast']
    assert db.solvers.docs == before


def test_directory_explicit_revocation_and_exited_staff_are_denied():
    db, _, _ = fixture(); emp = employee('staff', department='Operations', employment_type='Full_Time')
    db.employees.docs.append(emp); user = actor('employee', employee_id='staff')
    with patch.dict(RUNTIME_OVERRIDES, {('M02', 'employee'): None}):
        with pytest.raises(HTTPException): run(service.directory_access(db, user))
    db.employees.docs[0]['lifecycle_state'] = 'Exited'
    with pytest.raises(HTTPException): run(service.directory_access(db, user))


@pytest.mark.parametrize('state', ['Suspended', 'Deactivated', 'Inactive', 'Unknown'])
def test_ineligible_solver_cannot_use_self_service(state):
    db, _, _ = fixture(); db.solvers.docs[0]['lifecycle_state'] = state
    with routes(db, actor('solver', solver_id='one')):
        with pytest.raises(HTTPException): run(solvers.my_solver(request()))


def test_legacy_projection_preserves_contacts_lists_and_scores():
    row = solver(county='Central', sub_county='Area', vehicle_categories_certified=['SUV'],
                 nairobi_zones_covered='Zone 1', overall_performance_tier='Elite', accuracy_score=0)
    before = deepcopy(row); out = access.solver_view(row, actor('solver'))
    assert out['region'] == 'Central' and out['area_covered'] == 'Area'
    assert out['zones_covered'] == ['Zone 1'] and out['accuracy_score'] == 0
    assert row == before


def test_induction_get_is_read_only_and_explicit_start_is_idempotent():
    db, user, _ = fixture()
    with patch.multiple(onboarding, get_db=lambda: db, get_current_user=AsyncMock(return_value=user)):
        assert run(onboarding.get_solver_onboarding('one', request())) == []
    assert db.onboarding_tasks.writes == 0
    with routes(db, user):
        run(solvers.initiate_induction('one', request())); run(solvers.initiate_induction('one', request()))
    assert len(db.onboarding_tasks.docs) == 6 and len(db.notifications.docs) == 3
    assert all(task['entity_id'] == 'one' for task in db.onboarding_tasks.docs)


def test_activation_fails_closed_until_every_gate_and_never_changes_scores():
    db, user, record = fixture(); original = deepcopy(db.solvers.docs[0])
    with routes(db, user):
        with pytest.raises(HTTPException): run(solvers.activate_solver('one', request()))
        assert db.solvers.docs[0] == original
        for gate in service.GATES:
            run(solvers.verify_induction(str(record['_id']), request(evidence(db, record, gate))))
        with patch('utils.email_triggers.fire_and_forget', AsyncMock()):
            result = run(solvers.activate_solver('one', request()))
        assert result['lifecycle_state'] == 'Active'
        assert all(result.get(key) is None for key in ('accuracy_score', 'performance_tier'))
        with pytest.raises(HTTPException): run(solvers.activate_solver('one', request()))
    assert any(row['event'] == 'solver.activated' for row in db.audit_logs.docs)


def test_failed_quiz_foreign_evidence_and_wrong_category_cannot_satisfy_gates():
    db, user, record = fixture(); body = evidence(db, record, 'code_quiz'); body['score'] = 7
    with routes(db, user):
        assert run(solvers.verify_induction('one', request(body)))['verified'] is False
        body['score'] = 8; db.solver_documents.docs[-1]['solver_id'] = 'two'
        with pytest.raises(HTTPException): run(solvers.verify_induction('one', request(body)))
        db.solver_documents.docs[-1]['solver_id'] = 'one'; body['gate'] = 'agreement'; body.pop('score'); body.pop('maximum')
        with pytest.raises(HTTPException): run(solvers.verify_induction('one', request(body)))


def test_activation_cannot_be_forged_through_generic_update_or_task_completion():
    db, user, _ = fixture()
    with routes(db, user):
        with pytest.raises(HTTPException): run(solvers.update_solver('one', solvers.SolverUpdate(lifecycle_state='Active'), request()))
        with pytest.raises(HTTPException): run(solvers.update_solver('one', solvers.SolverUpdate(accuracy_score=100), request()))
    task = {'_id': ObjectId(), 'id': 'task', 'entity_type': 'solver', 'entity_id': 'one', 'task_key': 'S04', 'assigned_role': 'solver', 'tenant_id': 'solvit'}
    db.onboarding_tasks.docs.append(task)
    with patch.multiple(onboarding, get_db=lambda: db, get_current_user=AsyncMock(return_value=actor('solver', solver_id='one'))):
        with pytest.raises(HTTPException): run(onboarding.update_task('task', onboarding.TaskUpdate(status='Completed'), request()))
    assert db.solvers.writes == db.onboarding_tasks.writes == 0


def test_review_is_subject_scoped_idempotent_and_preserves_historical_answers():
    db, user, record = fixture()
    sub = {'_id': ObjectId(), 'id': 'assessment', 'tenant_id': 'solvit', 'subject_solver_id': str(record['_id']),
           'form_id': 'form-02', 'status': 'Submitted', 'score': 16, 'passed': False, 'data': {'q1': 'Historical'}}
    db.form_submissions.docs.append(sub); before = deepcopy(db.form_submissions.docs)
    with routes(db, user):
        run(solvers.review_solver_assessment('one', 'assessment', request()))
        run(solvers.review_solver_assessment('one', 'assessment', request()))
        with pytest.raises(HTTPException): run(solvers.review_solver_assessment('two', 'assessment', request()))
        assert run(solvers.solver_workflow('one', request()))['assessments'][0]['reviewed']
    assert len(db.solver_assessment_reviews.docs) == 1 and db.form_submissions.docs == before


def test_code_quiz_own_answers_and_seven_day_retry_no_answer_key_exposure():
    db, _, _ = fixture(); user = actor('solver', solver_id='one')
    schema = forms.FORM_SCHEMAS['form-03']
    answers = {field['id']: field['correct_answer'] for section in schema['sections'] for field in section['fields']}
    with patch.multiple(forms, get_db=lambda: db, get_current_user=AsyncMock(return_value=user)):
        public = run(forms.get_form_schema('form-03', request()))
        assert 'correct_answer' not in str(public)
        with pytest.raises(HTTPException): run(forms.submit_form('form-03', request({'solver_id': 'two', 'data': answers})))
        result = run(forms.submit_form('form-03', request({'data': answers})))
        assert result['score'] == 10 and result['passed']
        with pytest.raises(HTTPException): run(forms.submit_form('form-03', request({'data': answers})))
    assert db.form_submissions.docs[0]['subject_solver_id'] == 'one'


@pytest.mark.parametrize('age,count', [(1, 1), (8, 3)])
def test_failed_code_quiz_requires_cooling_off_and_three_failure_review(age, count):
    db, _, _ = fixture(); schema = forms.FORM_SCHEMAS['form-03']
    answers = {field['id']: field['correct_answer'] for section in schema['sections'] for field in section['fields']}
    db.form_submissions.docs = [{'_id': ObjectId(), 'subject_solver_id': 'one', 'form_id': 'form-03', 'tenant_id': 'solvit', 'passed': False,
        'submitted_at': (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()} for _ in range(count)]
    with pytest.raises(HTTPException): run(service.submit_code_quiz(db, actor('solver', solver_id='one'), {'data': answers}, schema))
    assert len(db.form_submissions.docs) == count


@pytest.mark.parametrize('role', ['employee', 'solver', 'executive', 'finance', 'it_admin'])
def test_non_managers_cannot_review_or_verify_any_solver(role):
    db, _, record = fixture(); body = evidence(db, record, 'contact')
    with routes(db, actor(role, solver_id='one')):
        with pytest.raises(HTTPException): run(solvers.verify_induction('one', request(body)))
        with pytest.raises(HTTPException): run(solvers.review_solver_assessment('one', 'forged', request()))
    assert db.solver_verifications.writes == db.solver_assessment_reviews.writes == 0


def test_private_document_default_and_cross_solver_download_authorization():
    db, user, record = fixture(); evidence(db, record, 'contact')
    assert run(documents.listing(db, actor('solver', solver_id='one'), 'one')) == []
    with pytest.raises(HTTPException): run(documents.download(db, actor('solver', solver_id='one'), 'two', 'contact'))
    with pytest.raises(HTTPException): run(documents.download(db, actor('solver', solver_id='one'), 'one', 'contact'))
    assert 'stored_path' not in str(run(documents.listing(db, user, 'one')))


def test_hr_document_upload_uses_private_storage_validation_and_audit(tmp_path):
    from routes import documents as employee_docs
    db, user, _ = fixture()
    file = UploadFile(filename='proof.pdf', file=BytesIO(b'%PDF-1.4\n%%EOF'), headers=Headers({'content-type': 'application/pdf'}))
    with patch.object(employee_docs, 'UPLOAD_ROOT', tmp_path), patch.object(documents, 'scan_content', AsyncMock()), patch.object(documents, 'validate_content'):
        result = run(documents.upload(db, user, 'one', file, documents.CATEGORIES[0], 'hr_only', True))
        assert result['visibility'] == 'hr_only' and 'stored_path' not in result
        response = run(documents.download(db, user, 'one', result['id']))
        assert response.headers['cache-control'] == 'no-store'
        assert [row['action'] for row in db.document_audit.docs] == ['uploaded', 'downloaded']
        db.solver_documents.docs[0]['stored_path'] = str(tmp_path.parent / 'foreign.pdf')
        with pytest.raises(HTTPException): run(documents.download(db, user, 'one', result['id']))


def test_document_scanner_failure_publishes_nothing(tmp_path):
    db, user, _ = fixture()
    file = UploadFile(filename='proof.pdf', file=BytesIO(b'%PDF-1.4\n%%EOF'), headers=Headers({'content-type': 'application/pdf'}))
    with patch.object(documents, 'scan_content', AsyncMock(side_effect=HTTPException(503, 'Scanner unavailable'))), patch.object(documents, 'validate_content'):
        with pytest.raises(HTTPException): run(documents.upload(db, user, 'one', file, documents.CATEGORIES[0], 'hr_only', True))
    assert db.solver_documents.writes == db.document_audit.writes == 0


def test_solver_report_preserves_executive_aggregates_and_excludes_contacts():
    db, user, _ = fixture(); db.solvers.docs[0].update(bank_account='PRIVATE', medical_notes='PRIVATE')
    result = run(reporting.report_data(db, user, 'solvers', export=True))
    assert result['total'] == 2 and 'PRIVATE' not in str(result) and 'phone_number' not in str(result)
    result = run(reporting.report_data(db, actor('executive'), 'solvers', export=True))
    assert result['summary_only'] and 'solver_name' not in str(result)


@pytest.mark.parametrize('role', ['executive', 'it_admin', 'employee', 'solver'])
def test_applicant_details_not_exposed_to_aggregate_or_technical_roles(role):
    db, _, _ = fixture()
    with patch.multiple(solver_intake, get_db=lambda: db, get_current_user=AsyncMock(return_value=actor(role, solver_id='one'))):
        with pytest.raises(HTTPException): run(solver_intake.get_eligible_detail('forged', request()))


def test_duplicate_identity_never_silently_disappears_from_directory():
    db, user, _ = fixture(); db.solvers.docs.append(solver('one', phone_number='+254700000003'))
    with routes(db, user):
        with pytest.raises(HTTPException) as error: run(solvers.list_solvers(request()))
    assert error.value.status_code == 409


def test_verification_audit_failure_cannot_publish_activation_evidence():
    db,user,record=fixture(); body=evidence(db,record,'contact')
    db.audit_logs.insert_one=AsyncMock(side_effect=RuntimeError('synthetic unavailable audit'))
    with routes(db,user):
        with pytest.raises(HTTPException):run(solvers.verify_induction('one',request(body)))
    assert not run(service.verification(db,user,record))['contact']['verified']


def test_conflicting_legacy_status_cannot_restore_access():
    db,_,_=fixture(); db.solvers.docs[0].update(lifecycle_state='Active',status='Suspended')
    with routes(db,actor('solver',solver_id='one')):
        with pytest.raises(HTTPException):run(solvers.my_solver(request()))


def test_repeated_job_rating_is_rejected_without_overwriting_existing():
    db,user,_=fixture();payload={'job_id':'synthetic-job','accuracy':80,'timeliness':90,'overall':85}
    with routes(db,user):
        run(solvers.submit_client_rating('one',request(payload)))
        before=deepcopy(db.solver_ratings.docs)
        with pytest.raises(HTTPException):run(solvers.submit_client_rating('one',request(payload)))
    assert db.solver_ratings.docs==before


def test_report_catalogue_exposes_solver_scope_without_undefined_variables():
    for role in ('hr_admin','executive'):
        rows=reporting.catalogue(actor(role))['reports']
        row=next(item for item in rows if item['id']=='solvers')
        assert row['summary_only']==(role=='executive')


def test_activation_audit_failure_cannot_grant_application_access():
    db,user,record=fixture()
    with routes(db,user):
        for gate in service.GATES:run(solvers.verify_induction('one',request(evidence(db,record,gate))))
        db.audit_logs.insert_one=AsyncMock(side_effect=RuntimeError('synthetic unavailable audit'))
        with pytest.raises(HTTPException):run(solvers.activate_solver('one',request()))
    assert service.view(db.solvers.docs[0])['lifecycle_state']=='Requires review'
    with routes(db,actor('solver',solver_id='one')):
        with pytest.raises(HTTPException):run(solvers.my_solver(request()))


def test_workflow_notifications_are_idempotent_private_and_recipient_isolated():
    from utils.notification_centre import list_inbox, read_notification
    db,user,record=fixture()
    run(service.notify(db,record,'initiated','initial')); run(service.notify(db,record,'initiated','initial'))
    assert len(db.notifications.docs)==3
    own=actor('solver',solver_id='one'); other=actor('solver',solver_id='two')
    inbox=run(list_inbox(db,own))
    assert inbox['unread_count']==1 and inbox['items'][0]['link']=='/solvers'
    assert run(list_inbox(db,other))['total']==0
    reference=inbox['items'][0]['id']
    with pytest.raises(HTTPException):run(read_notification(db,other,reference))
    run(read_notification(db,own,reference))
    assert run(list_inbox(db,own))['unread_count']==0
    assert 'phone_number' not in str(inbox) and 'score' not in str(inbox)


def test_real_local_mongo_solver_duplicate_prevention_and_notification_retry():
    from .test_employee_integrity_mongo import local_database
    async def check():
        async with local_database() as db:
            user=actor()
            with routes(db,user),patch('automation.engine.automation_engine.fire_event',AsyncMock()):
                results=await asyncio.gather(
                    solvers.create_solver(solvers.SolverCreate(full_name='Synthetic first',phone_number='0700000001'),request()),
                    solvers.create_solver(solvers.SolverCreate(full_name='Synthetic second',phone_number='+254700000001'),request()),return_exceptions=True)
            assert await db.solvers.count_documents({})==1
            assert sum(isinstance(result,HTTPException) and result.status_code==409 for result in results)==1
            record=await db.solvers.find_one({})
            await service.notify(db,record,'initiated','initial');await service.notify(db,record,'initiated','initial')
            assert await db.notifications.count_documents({})==3
            assert await db.audit_logs.count_documents({'event':'solver.created'})==1
    run(check())


def test_solver_document_audit_requires_m02_permission():
    db,user,_=fixture()
    db.document_audit.docs.append({'_id':ObjectId(),'tenant_id':'solvit','solver_id':'one','document_id':'proof',
                                  'action':'uploaded','timestamp':'2026-10-01T10:00:00Z','by_user_id':user['id']})
    assert reporting.audit_module('document_audit',db.document_audit.docs[0])=='M02'
    assert 'solver_id' in reporting.AUDIT_FIELDS
    for name in reporting.AUDIT_SOURCES:
        if not hasattr(db,name):setattr(db,name,Collection())
    with patch.dict(RUNTIME_OVERRIDES,{('M02','hr_admin'):None}):
        assert run(reporting.audit_feed(db,user))['items']==[]
