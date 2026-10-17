"""Synthetic L&D catalogue, approvals, evidence and employee isolation regressions."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import learning_workflows as service
from routes import lnd, ai_actions
from .test_profile_self_service import fixture as base_fixture
from .test_notification_centre import Receipts
from .integrity_fakes import Collection

def run(coro): return asyncio.run(coro)

def fixture():
    db, users=base_fixture()
    for name in ('training_programmes','idps','skills_matrix','notification_receipts','form_submissions','tasks','onboarding_tasks'):
        setattr(db,name,Collection())
    db.notifications=Receipts(); db.notification_receipts=Receipts()
    return db,users

def course_body(**changes):
    return {'title':'Synthetic course','kind':'Course','description':'Approved course description','provider':'Synthetic provider',
        'delivery_method':'Internal','starts_on':'2020-01-01','ends_on':'2020-01-03','due_on':'2020-01-10',
        'completion_requirements':'Attend and demonstrate the agreed skills','evidence_required':False,'departments':[],
        'employment_types':[],'cost_kes':1000,'duration_days':1,'status':'Published',**changes}

def assignment(db,users,**course_changes):
    course=run(service.save_programme(db,users['hr'],course_body(**course_changes)))
    row=run(service.prepare_request(db,users['hr'],{'employee_id':'staff','programme_id':course['id'],'business_justification':'Agreed development need'}))
    with patch('utils.email_triggers.fire_and_forget',new_callable=AsyncMock): run(service.persist_request(db,users['hr'],row))
    return db.training_requests.docs[0],course

def approve(db,users,row):
    run(service.decide(db,users['manager'],row['id'],{'decision':'Approve'}))
    if row['status']=='Pending_HR_Approval': run(service.decide(db,users['hr'],row['id'],{'decision':'Approve'}))

def declaration(**changes): return {'action':'submit','completed_on':'2020-01-03','evidence':'Actual attendance and practice evidence',**changes}

def evidence_document(db,employee_id='staff',**changes):
    row={'id':'evidence','tenant_id':'solvit','employee_id':employee_id,'category':'Academic Certificates',
         'confidential':False,'visibility':'hr_employee','publication_state':'Ready','file_path':'private/path',**changes}
    run(db.employee_documents.insert_one(row)); return row['id']


@pytest.mark.parametrize('actor',['staff','manager','finance','other'])
def test_catalogue_management_is_hr_only(actor):
    db,users=fixture()
    with pytest.raises(HTTPException): run(service.save_programme(db,users[actor],course_body()))
    assert db.training_programmes.writes==0


@pytest.mark.parametrize('changes',[{'title':''},{'kind':[]},{'status':'Unknown'},{'cost_kes':-1},{'cost_kes':float('nan')},
    {'duration_days':True},{'duration_days':1.5},{'ends_on':'2019-01-01'},{'due_on':'2020-01-01'},
    {'departments':{}},{'evidence_required':'yes'},{'location':{}},{'parent_id':{'$ne':None}}])
def test_invalid_catalogue_fields_fail_before_writes(changes):
    db,users=fixture()
    with pytest.raises(HTTPException): run(service.save_programme(db,users['hr'],course_body(**changes)))
    assert db.training_programmes.writes==0


def test_parent_hierarchy_and_eligibility_cannot_be_bypassed_by_a_session():
    db,users=fixture(); parent=run(service.save_programme(db,users['hr'],course_body(departments=['Finance'])))
    session=run(service.save_programme(db,users['hr'],course_body(title='Synthetic session',kind='Session',parent_id=parent['id'])))
    with pytest.raises(HTTPException): run(service.prepare_request(db,users['staff'],{'employee_id':'staff','programme_id':session['id'],'business_justification':'Nomination'}))
    with pytest.raises(HTTPException): run(service.save_programme(db,users['hr'],course_body(kind='Programme',parent_id=parent['id'])))


def test_catalogue_updates_preserve_assignment_snapshot_and_archival_prevents_new_assignments():
    db,users=fixture(); row,course=assignment(db,users); before=deepcopy(row)
    result=run(service.save_programme(db,users['hr'],{'title':'Changed for future cohorts','status':'Archived'},course['id']))
    assert result['version']==2 and row==before
    with pytest.raises(HTTPException): run(service.prepare_request(db,users['hr'],{'employee_id':'staff','programme_id':course['id'],'business_justification':'New nomination'}))
    assert len(db.training_requests.docs)==1


@pytest.mark.parametrize('worker_type',['FTE','Full_Time','full-time'])
def test_worker_type_aliases_and_legacy_employee_identity(worker_type):
    db,users=fixture(); db.employees.docs[0]['employment_type']=worker_type
    course=run(service.save_programme(db,users['hr'],course_body(employment_types=['Full_Time'])))
    row=run(service.prepare_request(db,users['staff'],{'employee_id':str(db.employees.docs[0]['_id']),'programme_id':course['id'],'business_justification':'Agreed nomination'}))
    assert row['employee_id']=='staff' and row['line_manager_id']=='manager'


def test_duplicates_and_missing_manager_or_exited_employee_are_safe():
    db,users=fixture(); row,course=assignment(db,users)
    with pytest.raises(HTTPException): run(service.prepare_request(db,users['hr'],{'employee_id':'staff','programme_id':course['id'],'business_justification':'Repeat'}))
    db.employees.docs[0]['line_manager_id']=None
    with pytest.raises(HTTPException): run(service.prepare_request(db,users['staff'],{'employee_id':'staff','training_name':'Another course','provider':'Internal','delivery_method':'Online','business_justification':'Development'}))
    db.employees.docs[0].update(line_manager_id='manager',lifecycle_state='Exited')
    with pytest.raises(HTTPException): run(service.prepare_request(db,users['staff'],{'employee_id':'staff','programme_id':course['id'],'business_justification':'Development'}))
    assert len(db.training_requests.docs)==1


def test_scoped_manager_and_hr_approvals_cannot_be_skipped_replayed_or_self_approved():
    db,users=fixture(); row,_=assignment(db,users,cost_kes=6000)
    with pytest.raises(HTTPException): run(service.decide(db,users['hr'],row['id'],{'decision':'Approve'}))
    with pytest.raises(HTTPException): run(service.decide(db,{**users['hr'],'employee_id':'staff'},row['id'],{'decision':'Approve'}))
    with pytest.raises(HTTPException): run(service.decide(db,users['other'],row['id'],{'decision':'Approve'}))
    run(service.decide(db,users['manager'],row['id'],{'decision':'Approve','requires_hr_approval':False}))
    assert row['status']=='Pending_HR_Approval'
    with pytest.raises(HTTPException): run(service.decide(db,users['manager'],row['id'],{'decision':'Approve'}))
    run(service.decide(db,users['hr'],row['id'],{'decision':'Approve'})); assert row['status']=='Approved'
    with pytest.raises(HTTPException): run(service.decide(db,users['hr'],row['id'],{'decision':'Approve'}))


@pytest.mark.parametrize('cost,days,expected',[(5000,2,'Approved'),(5001,2,'Pending_HR_Approval'),(0,3,'Pending_HR_Approval')])
def test_documented_training_approval_threshold(cost,days,expected):
    db,users=fixture(); row,_=assignment(db,users,cost_kes=cost,duration_days=days)
    run(service.decide(db,users['manager'],row['id'],{'decision':'Approve'})); assert row['status']==expected


def test_changed_manager_and_forged_identity_cannot_approve():
    db,users=fixture(); row,_=assignment(db,users)
    with pytest.raises(HTTPException): run(service.decide(db,users['manager'],row['id'],{'decision':'Approve','employee_id':'other'}))
    db.employees.docs[0]['line_manager_id']='other'
    with pytest.raises(HTTPException): run(service.decide(db,users['manager'],row['id'],{'decision':'Approve'}))
    assert row['status']=='Pending_Manager_Approval'


def test_completion_requires_approval_owner_and_hr_verification_with_audit_history():
    db,users=fixture(); row,_=assignment(db,users)
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration()))
    approve(db,users,row)
    with pytest.raises(HTTPException): run(service.complete(db,users['manager'],row['id'],declaration()))
    run(service.complete(db,users['staff'],row['id'],declaration())); assert row['status']=='Completion_Submitted'
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],{'action':'verify','requirements_met':True}))
    run(service.complete(db,users['hr'],row['id'],{'action':'return','reason':'Provide additional evidence'}))
    run(service.complete(db,users['staff'],row['id'],declaration(evidence='Additional verified evidence')))
    run(service.complete(db,users['hr'],row['id'],{'action':'verify','requirements_met':True}))
    assert row['status']=='Completed' and len(row['completion_submissions'])==2
    assert any(a['event']=='learning.completion.verify' for a in db.audit_logs.docs)
    with pytest.raises(HTTPException): run(service.complete(db,users['hr'],row['id'],{'action':'return','reason':'Reopen'}))


@pytest.mark.parametrize('changes',[{'completed_on':'2099-01-01'},{'completed_on':'2019-01-01'},{'evidence':''},
    {'status':'Completed'},{'employee_id':'other'},{'document_id':{'$ne':None}}])
def test_invalid_completion_payload_is_rejected(changes):
    db,users=fixture(); row,_=assignment(db,users); approve(db,users,row)
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration(**changes)))
    assert row['status']=='Approved'


def test_evidence_uses_same_employee_documents_and_preserves_sharing_controls():
    db,users=fixture(); row,_=assignment(db,users,evidence_required=True); approve(db,users,row)
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration()))
    evidence_document(db,employee_id='other')
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration(document_id='evidence')))
    db.employee_documents.docs.clear(); evidence_document(db)
    run(service.complete(db,users['staff'],row['id'],declaration(document_id='evidence')))
    run(service.complete(db,users['hr'],row['id'],{'action':'verify','requirements_met':True}))
    manager=run(service.projection(db,users['manager'],row,db.employees.docs[0]))
    assert 'document_id' not in manager['completion_submission'] and 'private/path' not in str(manager)
    employee=run(service.projection(db,users['staff'],row,db.employees.docs[0]))
    assert employee['completion_submission']['document_id']=='evidence'
    assert db.employee_documents.docs[0]['visibility']=='hr_employee'


@pytest.mark.parametrize('document_change',[{'deleted_at':'2020-01-01'},{'publication_state':'Pending_Audit'},
    {'visibility':'hr_only'},{'confidential':True},{'category':'Medical Certificate'}])
def test_unavailable_or_private_documents_cannot_be_used_by_employee(document_change):
    db,users=fixture(); row,_=assignment(db,users,evidence_required=True); approve(db,users,row)
    evidence_document(db,**document_change)
    with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration(document_id='evidence')))


def test_hr_external_certificate_is_verified_without_automatic_employee_sharing():
    db,users=fixture(); row,_=assignment(db,users); approve(db,users,row)
    evidence_document(db,visibility='hr_only',confidential=True)
    run(service.complete(db,users['hr'],row['id'],declaration(action='record',document_id='evidence',requirements_met=True)))
    assert row['status']=='Completed'
    visible=run(service.projection(db,users['staff'],row,db.employees.docs[0]))
    assert 'document_id' not in visible['completion_submission']


def test_training_list_is_isolated_and_supports_native_legacy_reference_without_raw_notes():
    db,users=fixture(); row,_=assignment(db,users); row['employee_id']=db.employees.docs[0]['_id']; row['notes']='confidential HR notes'
    with patch.object(lnd,'get_db',return_value=db),patch.object(lnd,'get_current_user',return_value=users['other']):
        assert run(lnd.list_training_requests(None))==[]
    with patch.object(lnd,'get_db',return_value=db),patch.object(lnd,'get_current_user',return_value=users['manager']):
        result=run(lnd.list_training_requests(None,employee_id='staff'))
    assert result[0]['employee_id']=='staff' and 'confidential HR notes' not in str(result)


def test_deadline_notifications_are_recipient_scoped_and_idempotent():
    from utils.notification_centre import list_inbox
    db,users=fixture(); row,_=assignment(db,users); approve(db,users,row)
    run(service.remind_due(db)); count=len(db.notifications.docs); run(service.remind_due(db))
    assert len(db.notifications.docs)==count
    inbox=run(list_inbox(db,users['staff']))
    assert inbox['items'] and all(item['link']=='/lnd?training='+row['id'] for item in inbox['items'])
    assert run(list_inbox(db,users['other']))['items']==[]
    assert 'business_justification' not in str(inbox)


def test_ai_nomination_does_not_create_an_approved_record_or_bypass_manager_link():
    db,users=fixture()
    with patch('utils.email_triggers.fire_and_forget',new_callable=AsyncMock):
        run(ai_actions.execute_assign_training(db,{'employee_id':'staff','training_name':'AI-nominated course'},users['hr']))
    assert db.training_requests.docs[0]['status']=='Pending_Manager_Approval'
    assert any(row['event']=='learning.request.created' for row in db.audit_logs.docs)


def test_programme_batch_is_validated_before_any_employee_write():
    db,users=fixture(); course=run(service.save_programme(db,users['hr'],course_body()))
    request=SimpleNamespace(json=AsyncMock(return_value={'employee_ids':['staff','other']}))
    with patch.object(lnd,'get_db',return_value=db),patch.object(lnd,'get_current_user',return_value=users['hr']):
        with pytest.raises(HTTPException): run(lnd.assign_programme(course['id'],request))
    assert db.training_requests.writes==0


def test_module_readonly_and_failed_audit_do_not_allow_completion_writes():
    from utils.access_matrix import RUNTIME_OVERRIDES
    db,users=fixture(); row,_=assignment(db,users); approve(db,users,row)
    with patch.dict(RUNTIME_OVERRIDES,{('M08','employee'):{'level':'Read','scope':'own_record'}}):
        with pytest.raises(HTTPException): run(service.complete(db,users['staff'],row['id'],declaration()))
    request=SimpleNamespace(json=AsyncMock(return_value=declaration()))
    with patch.object(lnd,'get_db',return_value=db),patch.object(lnd,'get_current_user',return_value=users['staff']),patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('synthetic interruption')):
        with pytest.raises(RuntimeError): run(lnd.complete_training(row['id'],request))
    assert row['status']=='Approved' and len(db.integrity_locks.docs)==1


def test_idp_partial_updates_preserve_existing_goals_and_are_audited():
    db,users=fixture(); run(db.idps.insert_one({'id':'idp','tenant_id':'solvit','employee_id':'staff','goals':[{'goal':'Preserved'}]}))
    with patch.object(lnd,'get_db',return_value=db),patch.object(lnd,'get_current_user',return_value=users['staff']):
        run(lnd.create_or_update_idp(lnd.IDPCreate(employee_id='staff',career_aspiration='Updated aspiration'),None))
    assert db.idps.docs[0]['goals']==[{'goal':'Preserved'}]
    assert db.audit_logs.docs[-1]['event']=='learning.idp.updated'


def test_real_mongo_concurrent_assignments_are_serialized_and_notifications_are_idempotent():
    from .test_employee_integrity_mongo import local_database
    from utils.employee_integrity import integrity_write
    async def exercise():
        async with local_database() as db:
            seed, users = fixture()
            await db.employees.insert_many(deepcopy(seed.employees.docs))
            await db.users.insert_many(deepcopy(seed.users.docs))
            async with integrity_write(db):
                course = await service.save_programme(db, users['hr'], course_body())
            async def attempt():
                try:
                    async with integrity_write(db):
                        row = await service.prepare_request(db, users['hr'], {'employee_id':'staff','programme_id':course['id'],'business_justification':'Agreed development'})
                        with patch('utils.email_triggers.fire_and_forget', new_callable=AsyncMock):
                            await service.persist_request(db, users['hr'], row)
                        return row
                except HTTPException as error: return error.status_code
            results = await asyncio.gather(attempt(), attempt())
            assert 409 in results and await db.training_requests.count_documents({}) == 1
            row = await db.training_requests.find_one({})
            await service.notify(db, row, 'created')
            assert await db.notifications.count_documents({}) == 4
            assert await db.integrity_locks.count_documents({}) == 0
    run(exercise())


def test_profile_cannot_bypass_revoked_learning_permissions_for_idp_or_training():
    from routes import employees
    from utils.access_matrix import RUNTIME_OVERRIDES
    db, users = fixture()
    row, _ = assignment(db, users)
    run(db.idps.insert_one({'id':'private-idp','employee_id':'staff','tenant_id':'solvit','career_aspiration':'Private development plan'}))
    with patch.dict(RUNTIME_OVERRIDES, {('M08','hr_admin'):None}), patch.object(employees,'get_db',return_value=db), patch.object(employees,'get_current_user',return_value=users['hr']):
        result = run(employees.get_employee_profile('staff', None))
    assert result['trainings'] == [] and result['idp'] is None
    assert not any(item['type']=='training' for item in result['timeline'])
