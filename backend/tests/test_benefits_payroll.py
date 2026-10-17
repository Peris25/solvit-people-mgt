"""Synthetic benefits, payroll confidentiality and preserved bank approvals."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import benefits as service
from routes import benefits, compensation
from .test_profile_self_service import fixture as base_fixture
from .test_notification_centre import Receipts
from .integrity_fakes import Collection

def run(coro): return asyncio.run(coro)
def fixture():
    db,users=base_fixture()
    for name in ('benefit_schemes','benefit_requests','benefit_premiums','salary_reviews'): setattr(db,name,Collection())
    db.notifications=Receipts(); db.notification_receipts=Receipts()
    for employee in db.employees.docs: employee['employment_type']='Full_Time'
    return db,users

def policy(**changes):
    return {'title':'Synthetic cover','insurer':'Synthetic insurer','policy_number':'TEST-POLICY','cover_type':'Medical','cover_levels':['Standard'],
        'starts_on':'2020-01-01','ends_on':'2035-12-31','renewal_on':'2035-12-31','worker_types':['FTE'],'minimum_service_days':0,
        'max_dependants':2,'enrolment_deadline':'2035-01-01','insurer_contact':'Contact HR for verified contacts','claim_instructions':'Contact the insurer directly',
        'approval_reference':'Synthetic approved terms','status':'Published',**changes}

def setup(**changes):
    db,users=fixture(); row=run(service.save_scheme(db,users['hr'],policy(**changes))); return db,users,row

def body(row,**changes): return {'scheme_id':row['id'],'cover_level':'Standard','dependants':[],'beneficiaries':[],'confirm_cover':True,**changes}
def submit(db,users,row,**changes): return run(service.submit(db,users['staff'],body(row,**changes)))
def document(db,**changes):
    run(db.employee_documents.insert_one({'id':'evidence','tenant_id':'solvit','employee_id':'staff','category':'Other','category_label':'Birth certificate','publication_state':'Ready','visibility':'hr_employee','confidential':False,'file_path':'PRIVATE_PATH',**changes}))
    return 'evidence'

@pytest.mark.parametrize('actor',['staff','manager','finance','other'])
def test_only_hr_may_configure_eligibility(actor):
    db,users=fixture()
    with pytest.raises(HTTPException): run(service.save_scheme(db,users[actor],policy()))
    assert db.benefit_schemes.writes==0

@pytest.mark.parametrize('changes',[{'worker_types':[]},{'cover_levels':[]},{'cover_type':'Pension'},{'minimum_service_days':True},
    {'max_dependants':-1},{'ends_on':'2019-01-01'},{'status':'Unknown'},{'approval_reference':''},{'premium_kes':10},{'policy_number':{}},
    {'enrolment_deadline':'2040-01-01'}])
def test_invalid_or_unapproved_scheme_is_not_saved(changes):
    db,users=fixture()
    with pytest.raises(HTTPException): run(service.save_scheme(db,users['hr'],policy(**changes)))
    assert db.benefit_schemes.writes==0

def test_draft_can_be_saved_without_an_approval_but_never_enrolled():
    db,users,row=setup(status='Draft',approval_reference='')
    assert row['status']=='Draft'
    with pytest.raises(HTTPException): submit(db,users,row)

def test_published_terms_cannot_be_changed_even_after_archiving():
    db,users,row=setup()
    with pytest.raises(HTTPException): run(service.save_scheme(db,users['hr'],{'max_dependants':10},row['id']))
    run(service.save_scheme(db,users['hr'],{'status':'Archived'},row['id']))
    with pytest.raises(HTTPException): run(service.save_scheme(db,users['hr'],{'title':'Changed'},row['id']))
    assert db.benefit_schemes.docs[0]['max_dependants']==2

@pytest.mark.parametrize('changes',[{'lifecycle_state':'Exited'},{'board_only':True},{'employment_type':'Contractor'},{'start_date':'2099-01-01'}])
def test_classification_and_eligibility_do_not_assume_coverage(changes):
    db,users,row=setup(); db.employees.docs[0].update(changes)
    with pytest.raises(HTTPException): submit(db,users,row)
    assert db.benefit_requests.writes==0

@pytest.mark.parametrize('field',['employee_id','line_manager_id','status','premium_kes','diagnosis'])
def test_forged_or_sensitive_membership_fields_are_rejected(field):
    db,users,row=setup()
    with pytest.raises(HTTPException): submit(db,users,row,**{field:'forged'})
    assert db.benefit_requests.writes==0

def test_own_request_legacy_identity_isolation_and_duplicate_prevention():
    db,users,row=setup(); users['staff']['employee_id']=str(db.employees.docs[0]['_id'])
    result=submit(db,users,row); assert result['employee_id']=='staff' and result['status']=='Pending_HR'
    with pytest.raises(HTTPException): submit(db,users,row)
    assert run(service.overview(db,users['other']))['memberships']==[]
    assert 'PRIVATE_PATH' not in str(run(service.overview(db,users['staff'])))

@pytest.mark.parametrize('beneficiaries',[[{'name':'Person','relationship':'Sibling','percentage':50}],[],[{'name':'Person','relationship':'Sibling','percentage':float('nan')}],[{'name':'Person','relationship':'Sibling','percentage':True}]])
def test_accident_beneficiary_shares_must_be_valid_and_total_100(beneficiaries):
    db,users,row=setup(cover_type='Accident')
    with pytest.raises(HTTPException): submit(db,users,row,beneficiaries=beneficiaries)

def test_medical_dependent_evidence_hr_approval_and_finance_privacy():
    db,users,row=setup(); document(db)
    result=submit(db,users,row,dependants=[{'name':'Synthetic dependant','date_of_birth':'2020-01-01','relationship':'Child','document_id':'evidence'}])
    request=db.benefit_requests.docs[0]
    with pytest.raises(HTTPException): run(service.decide(db,users['finance'],result['id'],{'decision':'Approve','reason':'Cannot approve'}))
    with pytest.raises(HTTPException): run(service.decide(db,{**users['hr'],'employee_id':'staff'},result['id'],{'decision':'Approve','reason':'Own request'}))
    result=run(service.decide(db,users['hr'],result['id'],{'decision':'Approve','reason':'Verified enrolment evidence'}))
    assert result['status']=='Approved'
    finance=service.request_view(request,db.employees.docs[0],users['finance'])
    assert 'dependants' not in finance and 'beneficiaries' not in finance and 'document_id' not in str(finance)
    assert 'file_path' not in str(result)
    assert any(a['event']=='benefits.membership.decided' for a in db.audit_logs.docs)
    with pytest.raises(HTTPException): run(service.decide(db,users['hr'],result['id'],{'decision':'Reject','reason':'Replay'}))

@pytest.mark.parametrize('changes',[{'employee_id':'other'},{'deleted_at':'2020-01-01'},{'visibility':'hr_only'},{'publication_state':'Pending_Audit'},{'category':'Medical report'}])
def test_dependant_evidence_must_be_available_and_owned(changes):
    db,users,row=setup(); document(db,**changes)
    with pytest.raises(HTTPException): submit(db,users,row,dependants=[{'name':'Person','date_of_birth':'2020-01-01','relationship':'Child','document_id':'evidence'}])
    assert db.benefit_requests.writes==0

def test_changes_preserve_approved_history_and_require_documented_reason_and_support():
    db,users,row=setup(); first=submit(db,users,row)
    run(service.decide(db,users['hr'],first['id'],{'decision':'Approve','reason':'Verified'}))
    before=deepcopy(db.benefit_requests.docs[0])
    with pytest.raises(HTTPException): submit(db,users,row,reason='Marriage')
    document(db); second=submit(db,users,row,reason='Marriage',supporting_document_id='evidence')
    run(service.decide(db,users['hr'],second['id'],{'decision':'Approve','reason':'Verified change'}))
    assert db.benefit_requests.docs[0]==before
    views=run(service.overview(db,users['staff']))['memberships']
    assert next(item for item in views if item['id']==first['id'])['status']=='Superseded (historical)'

@pytest.mark.parametrize('actor',['hr','staff','manager','other'])
def test_premiums_are_finance_only(actor):
    db,users,row=setup()
    with pytest.raises(HTTPException): run(service.premium(db,users[actor],row['id'],{'month':'2026-10','amount_kes':12345,'approval_reference':'Approved'}))
    assert db.benefit_premiums.writes==0

def test_finance_records_approved_premium_with_private_history_and_no_hr_audit_amount():
    db,users,row=setup()
    for amount in (12345,15000): run(service.premium(db,users['finance'],row['id'],{'month':'2026-10','amount_kes':amount,'approval_reference':'Verified'}))
    assert len(db.benefit_premiums.docs)==1 and db.benefit_premiums.docs[0]['history'][0]['amount_kes']==12345
    assert '12345' not in str(db.audit_logs.docs) and '15000' not in str(db.audit_logs.docs)
    assert 'amount_kes' not in str(run(service.overview(db,users['staff'])))


def test_generic_notifications_do_not_expose_households_or_premiums_and_are_idempotent():
    from utils.notification_centre import list_inbox
    db,users,row=setup(); result=submit(db,users,row)
    request=db.benefit_requests.docs[0]; run(service.notify(db,request,'requested'))
    assert len(db.notifications.docs)==3
    inbox=run(list_inbox(db,users['staff']))
    assert inbox['items'][0]['link']=='/benefits'
    assert 'dependants' not in str(inbox) and 'policy_number' not in str(inbox)
    assert run(list_inbox(db,users['other']))['items']==[]


def test_salary_proposals_are_scoped_audited_and_not_emailed_as_approved():
    db,users=fixture(); data={'employee_id':'staff','new_salary_kes':120000,'reason':'Documented proposal'}
    request=SimpleNamespace(json=AsyncMock(return_value=data))
    with patch.object(compensation,'get_db',return_value=db),patch.object(compensation,'get_current_user',return_value=users['hr']),patch('utils.email_triggers.fire_and_forget',new_callable=AsyncMock) as email:
        result=run(compensation.create_salary_review(request))
    assert result['status']=='Pending_Finance_Approval' and email.await_count==0
    assert any(a['event']=='compensation.salary_review.proposed' for a in db.audit_logs.docs)
    assert 'current_salary_kes' not in db.employees.docs[0]


def test_new_write_audit_failure_retains_integrity_lock_and_prevents_membership():
    db,users,row=setup(); request=SimpleNamespace(json=AsyncMock(return_value=body(row)))
    with patch.object(benefits,'get_db',return_value=db),patch.object(benefits,'get_current_user',return_value=users['staff']),patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('Synthetic interruption')):
        with pytest.raises(RuntimeError): run(benefits.request_membership(request))
    assert db.benefit_requests.writes==0 and len(db.integrity_locks.docs)==1


def test_manager_and_finance_cannot_obtain_other_household_data_through_admin_endpoint():
    db,users,row=setup(); submit(db,users,row)
    with patch.object(benefits,'get_db',return_value=db),patch.object(benefits,'get_current_user',return_value=users['manager']):
        with pytest.raises(HTTPException): run(benefits.list_memberships(None))
    with patch.object(benefits,'get_db',return_value=db),patch.object(benefits,'get_current_user',return_value=users['finance']):
        result=run(benefits.list_memberships(None))
    assert 'dependants' not in str(result) and 'beneficiaries' not in str(result)


def test_real_mongo_serializes_duplicate_enrolment_and_keeps_notification_payloads():
    from .test_employee_integrity_mongo import local_database
    from utils.employee_integrity import integrity_write
    async def exercise():
        async with local_database() as db:
            seed,users=fixture(); await db.employees.insert_many(deepcopy(seed.employees.docs)); await db.users.insert_many(deepcopy(seed.users.docs))
            async with integrity_write(db): row=await service.save_scheme(db,users['hr'],policy())
            async def attempt():
                try:
                    async with integrity_write(db): return await service.submit(db,users['staff'],body(row))
                except HTTPException as error: return error.status_code
            results=await asyncio.gather(attempt(),attempt())
            assert 409 in results and await db.benefit_requests.count_documents({})==1
            assert await db.notifications.count_documents({})==3
            assert await db.integrity_locks.count_documents({})==0
    run(exercise())


def test_revoked_module_permissions_are_not_bypassed_by_hr_or_finance_roles():
    from utils.access_matrix import RUNTIME_OVERRIDES
    db,users,row=setup()
    with patch.dict(RUNTIME_OVERRIDES,{('M10','hr_admin'):None}):
        with pytest.raises(HTTPException): run(service.save_scheme(db,users['hr'],policy()))
    with patch.dict(RUNTIME_OVERRIDES,{('M10','finance'):None}):
        with pytest.raises(HTTPException): run(service.premium(db,users['finance'],row['id'],{'month':'2026-10','amount_kes':1,'approval_reference':'Approved'}))
    with patch.dict(RUNTIME_OVERRIDES,{('M01','employee'):None}):
        with pytest.raises(HTTPException): submit(db,users,row)


def test_finance_oversight_never_returns_households_or_hr_notes_even_for_own_membership():
    db,users,row=setup(); record={'id':'request','review_reason':'Private HR reason','dependants':[{'name':'Private dependant'}]}
    visible=service.request_view(record,db.employees.docs[3],users['finance'])
    assert not {'dependants','beneficiaries','review_reason'} & visible.keys()


def test_compensation_read_scopes_tenant_and_redacts_unrelated_hr_fields_for_finance():
    db,users=fixture()
    run(db.salary_reviews.insert_one({'id':'own-tenant','tenant_id':'solvit','employee_id':'staff','new_salary_kes':100,'medical_notes':'Private HR field'}))
    run(db.salary_reviews.insert_one({'id':'foreign','tenant_id':'foreign','employee_id':'staff','new_salary_kes':999}))
    with patch.object(compensation,'get_db',return_value=db),patch.object(compensation,'get_current_user',return_value=users['finance']):
        result=run(compensation.get_salary_reviews(None))
    assert len(result)==1 and result[0]['id']=='own-tenant' and 'medical_notes' not in str(result)


def test_existing_payslip_restrictions_are_not_loosened_for_employee_or_finance():
    from routes.documents import _visible
    db,users=fixture()
    payslip={'category':'Payslip','confidential':False,'visibility':'hr_employee','employee_id':'staff'}
    assert not _visible(payslip,db.employees.docs[0],users['staff'])
    assert not _visible(payslip,db.employees.docs[0],users['finance'])
    assert _visible(payslip,db.employees.docs[0],users['hr'])


def test_staff_home_surfaces_real_eligible_benefit_task_without_membership_writes():
    from .test_staff_home import fixture as home_fixture, load
    db,user,employee=home_fixture(); employee['employment_type']='FTE'; db.employees.docs[0]=deepcopy(employee)
    db.benefit_schemes=Collection([{'id':'scheme','tenant_id':'solvit',**policy()}])
    actions=[row for row in load(db,user)['tasks'] if row.get('kind')=='benefits']
    assert len(actions)==1 and actions[0]['path']=='/benefits' and db.benefit_requests.writes==0


def test_pay_band_updates_validate_range_tenant_and_audit_before_write():
    db,users=fixture()
    db.pay_bands=Collection()
    run(db.pay_bands.insert_many([{'id':'band','tenant_id':'solvit','min_kes':100,'mid_kes':200,'max_kes':300},{'id':'foreign','tenant_id':'foreign','min_kes':100,'mid_kes':200,'max_kes':300}]))
    request=SimpleNamespace(json=AsyncMock(return_value={'mid_kes':250}))
    with patch.object(compensation,'get_db',return_value=db),patch.object(compensation,'get_current_user',return_value=users['hr']):
        result=run(compensation.update_pay_band('band',request)); assert result['mid_kes']==250
        with pytest.raises(HTTPException): run(compensation.update_pay_band('foreign',request))
        request.json=AsyncMock(return_value={'mid_kes':999})
        with pytest.raises(HTTPException): run(compensation.update_pay_band('band',request))
    assert db.pay_bands.docs[0]['mid_kes']==250 and db.pay_bands.docs[1]['mid_kes']==200
    assert any(row['event']=='compensation.pay_band.updated' for row in db.audit_logs.docs)


def test_finance_gate_cannot_forge_record_identity_and_is_audited_without_payment():
    db,users=fixture(); db.gp_gate=Collection()
    request=SimpleNamespace(json=AsyncMock(return_value={'tenant_id':'foreign','gate_open':True}))
    with patch.object(compensation,'get_db',return_value=db),patch.object(compensation,'get_current_user',return_value=users['finance']):
        with pytest.raises(HTTPException): run(compensation.set_gp_gate(request))
        assert db.gp_gate.writes==0
        request.json=AsyncMock(return_value={'gate_open':False})
        result=run(compensation.set_gp_gate(request))
    assert result['gate_open'] is False and result['tenant_id']=='solvit'
    assert any(row['event']=='compensation.gate.recorded' for row in db.audit_logs.docs)
    assert db.employees.writes==0


def test_existing_bonus_read_redacts_numeric_performance_scores_for_finance():
    db,users=fixture(); db.employees.docs[0].update(current_salary_kes=100,last_performance_score=1.2)
    with patch.object(compensation,'get_db',return_value=db),patch.object(compensation,'get_current_user',return_value=users['finance']):
        result=run(compensation.get_bonus_calculator(None))
    assert len(result['employees'])==1 and 'performance_score' not in result['employees'][0]
    assert db.employees.writes==0
