from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from utils import probation_reviews as probation, performance_workflows as flow, performance_v3 as process
from .test_performance_workflows import fixture, run
from .test_individual_reviews import body


def assign(db):
    values=deepcopy(next(v for v in process.library.catalogue() if v['role_id']=='it-support'))
    values['scope']='Probation'
    for goal in values['goals']: goal['direction']='Rated';goal['target_value']=None
    db.system_settings.docs.append({'_id':process.key(process.ASSIGNMENT,'solvit','staff'),'tenant_id':'solvit','values':values,'version':'assignment-v1'})
    return values


def setup(month=3):
    db,users=fixture();db.employees.docs[0]['lifecycle_state']='Probation';assign(db)
    row=run(flow.create_review(db,users['hr'],body(cycle_type='Probation',review_month=month,policy=None,policy_confirmed=False)))
    return db,users,row['id']


def payload(db,ref,submit=True):
    row=next(r for r in db.performance_reviews.docs if r['id']==ref)
    return {'expected_version':probation.version(row),'submit':submit,'kpis':{g['id']:{'m1':'Ramp up','m2':'Verified Month 2 result','m3':'Verified Month 3 result','score':1.5,'evidence':'Verified source record'} for g in row['section_a_kpis']},
            'values':[{'score':1.5,'evidence':'Observed work example','concerns':''} for _ in range(5)],'summary':'Manager assessment','strengths':'Observed strengths','development_actions':'Weekly coaching','recommendation':'Confirm' if row['review_month']==3 else 'Continue probation'}


def act(db,users,ref,actor,stage,values):
    row=next(r for r in db.performance_reviews.docs if r['id']==ref)
    return run(flow.assess(db,users[actor],ref,stage,{'expected_version':probation.version(row),**values}))


def submitted():
    db,users,ref=setup();run(flow.assess(db,users['manager'],ref,'manager',payload(db,ref)))
    return db,users,ref


def completed_meeting(db,users,ref):
    run(flow.schedule_meeting(db,users['hr'],ref,{'scheduled_at':'2099-01-20T10:00:00+03:00','location':'Meeting room'}))
    with patch.object(probation,'datetime',wraps=datetime) as clock:
        clock.now.return_value=datetime(2099,1,21,tzinfo=timezone.utc)
        return act(db,users,ref,'manager','meeting-complete',{'discussion':'Results discussed with the employee','agreed_actions':'Weekly coaching and agreed targets'})


def test_full_manager_first_meeting_hr_release_employee_acknowledgement_without_status_change():
    db,users,ref=setup();people=deepcopy(db.employees.docs)
    view=run(flow.record(db,users['staff'],ref))
    assert not flow.projection(view[0],users['staff'],view[1])['can_self_assess']
    with pytest.raises(HTTPException): act(db,users,ref,'staff','self',{'summary':'Not required'})
    result=run(flow.assess(db,users['manager'],ref,'manager',payload(db,ref)))
    assert result['status']=='Manager_Submitted' and result['section_a_score']==1.5 and result['section_b_score']==1.5
    act(db,users,ref,'staff','employee-comments',{'comments':'I would like more coaching'})
    with pytest.raises(HTTPException): act(db,users,ref,'hr','hr',{'summary':'Approve','outcome':'Confirm'})
    with pytest.raises(HTTPException): act(db,users,ref,'manager','meeting-complete',{'discussion':'Not yet','agreed_actions':'Not yet'})
    completed_meeting(db,users,ref)
    act(db,users,ref,'hr','hr',{'summary':'Meeting complete; approve confirmation','outcome':'Confirm'})
    result=act(db,users,ref,'hr','release',{})
    assert result['status']=='Completed' and result['probation_outcome']['outcome']=='Confirm'
    result=act(db,users,ref,'staff','acknowledge',{'acknowledged':True,'comments':'Received; I disagree with one rating'})
    assert result['probation_acknowledgement']['receipt_only'] is True
    assert 'disagree' in result['probation_acknowledgement']['comments']
    assert db.employees.docs==people
    with pytest.raises(HTTPException): act(db,users,ref,'manager','manager',payload(db,ref))


def test_manager_draft_is_private_and_started_work_cannot_be_deleted():
    db,users,ref=setup();data=payload(db,ref,False)
    result=run(flow.assess(db,users['manager'],ref,'manager',data))
    assert result['status']=='Draft' and result['probation_manager_draft']['kpis']
    row,employee=run(flow.record(db,users['staff'],ref));view=flow.projection(row,users['staff'],employee)
    assert 'probation_manager_draft' not in view and not view.get('manager_assessment')
    from utils.review_deletion import removable
    assert not removable(row)
    with pytest.raises(HTTPException): run(flow.assess(db,users['manager'],ref,'manager',data))


@pytest.mark.parametrize('actor',['staff','other','hr'])
def test_only_reporting_manager_can_score(actor):
    db,users,ref=setup()
    with pytest.raises(HTTPException): run(flow.assess(db,users[actor],ref,'manager',payload(db,ref)))
    assert not db.performance_reviews.docs[0].get('manager_assessment')


def test_month_one_and_two_do_not_allow_final_outcomes():
    db,users,ref=setup(1);data=payload(db,ref);data['recommendation']='Confirm'
    with pytest.raises(HTTPException): run(flow.assess(db,users['manager'],ref,'manager',data))
    data['recommendation']='Continue probation'
    assert run(flow.assess(db,users['manager'],ref,'manager',data))['status']=='Manager_Submitted'


def test_final_month_requires_month_two_actuals_and_both_section_scores():
    db,users,ref=setup();data=payload(db,ref)
    first=next(iter(data['kpis']));data['kpis'][first]['m2']=''
    with pytest.raises(HTTPException): run(flow.assess(db,users['manager'],ref,'manager',data))
    data['kpis'][first]['m2']='Verified';data['values'][2]['score']=float('nan')
    with pytest.raises(HTTPException): run(flow.assess(db,users['manager'],ref,'manager',data))


def test_existing_unstarted_reviews_reuse_approved_kpis_without_writing_on_read():
    db,users,ref=setup();row=db.performance_reviews.docs[0];row['section_a_kpis']=[];row.pop('probation_workflow_version',None)
    before=deepcopy(db.performance_reviews.docs)
    loaded,employee=run(flow.record(db,users['manager'],ref))
    assert loaded['section_a_kpis'] and db.performance_reviews.docs==before
    assert flow.projection(loaded,users['manager'],employee)['manager_led_probation']


def test_completed_existing_assessment_is_not_rewritten_or_recalculated():
    db,users,ref=setup();row=db.performance_reviews.docs[0]
    row.update(status='Completed',manager_assessment={'summary':'Legacy completed assessment'},section_a_score=1.77)
    before=deepcopy(row)
    loaded,employee=run(flow.record(db,users['hr'],ref))
    assert loaded['manager_assessment']==before['manager_assessment'] and loaded['section_a_score']==1.77
    with pytest.raises(HTTPException): run(flow.assess(db,users['manager'],ref,'manager',payload(db,ref)))
    assert db.performance_reviews.docs[0]==before


def test_pdf_workings_answer_key_and_decimal_scores():
    weights=[20,10,15,15,10,10,5,5,10];scores=[1.02,3,1.94,1,2,1.5,1.5,1.5,1]
    row={'review_month':3,'section_a_kpis':[{'id':str(i),'weight':weight,'direction':'Rated'} for i,weight in enumerate(weights)]}
    data={'kpis':{str(i):{'m2':'Source Month 2','m3':'Source Month 3','score':value,'evidence':'Manager verified source'} for i,value in enumerate(scores)},'values':[{'score':value,'evidence':'Observed example'} for value in [1.5,1.5,1,1.5,1.5]],'summary':'Summary','strengths':'Strengths','development_actions':'Support','recommendation':'Confirm'}
    result=probation.assessment(row,data,True)
    assert result['section_a_score']==1.55 and result['section_b_score']==1.4


def test_measured_kpi_scores_are_calculated_and_override_requires_explanation():
    row={'review_month':3,'section_a_kpis':[{'id':'rate','weight':100,'direction':'Higher','target_value':95}]}
    data={'kpis':{'rate':{'m2':'94.6%','m3':'94.8%','combined_actual':94.7,'evidence':'870 / 919 from source totals'}},'values':[{'score':1.5,'evidence':'Example'} for _ in range(5)],'summary':'Summary','strengths':'Strengths','development_actions':'Support','recommendation':'Confirm'}
    assert probation.assessment(row,data,True)['section_a_score']==1.02
    data['kpis']['rate']['score']=1.5
    with pytest.raises(HTTPException): probation.assessment(row,data,True)
    data['kpis']['rate']['score_reason']='Manager explanation based on verified context'
    assert probation.assessment(row,data,True)['section_a_score']==1.5


def test_extension_needs_written_agreement_and_future_end_date():
    db,users,ref=submitted();completed_meeting(db,users,ref)
    with pytest.raises(HTTPException): act(db,users,ref,'hr','hr',{'summary':'Extend with support','outcome':'Extend','extension_end_date':'2100-01-01'})
    result=act(db,users,ref,'hr','hr',{'summary':'Extend with support','outcome':'Extend','extension_end_date':'2100-01-01','extension_agreement_reference':'Written agreement retained in employee documents'})
    assert result['probation_outcome']['extension_end_date']=='2100-01-01'
    assert db.employees.docs[0]['lifecycle_state']=='Probation'


def test_employee_cannot_acknowledge_before_release_or_hr_acknowledge_for_employee():
    db,users,ref=submitted()
    for actor in ('staff','hr'):
        with pytest.raises(HTTPException): act(db,users,ref,actor,'acknowledge',{'acknowledged':True})


def test_assignment_change_after_opening_an_existing_draft_requires_reload():
    db,users,ref=setup();row=db.performance_reviews.docs[0]
    row['section_a_kpis']=[];row.pop('kpi_assignment_version',None)
    opened,_=run(flow.record(db,users['manager'],ref))
    old_version=probation.version(opened)
    saved=next(r for r in db.system_settings.docs if r.get('version')=='assignment-v1');saved['version']='assignment-v2'
    data=payload(db,ref);data['expected_version']=old_version
    with pytest.raises(HTTPException) as error: run(flow.assess(db,users['manager'],ref,'manager',data))
    assert error.value.status_code==409


def test_new_review_with_missing_kpis_is_not_created_or_sent():
    db,users=fixture();db.employees.docs[0]['lifecycle_state']='Probation'
    with pytest.raises(HTTPException):run(flow.create_review(db,users['hr'],body(cycle_type='Probation',review_month=1,policy=None,policy_confirmed=False)))
    assert not db.performance_reviews.docs and not db.notifications.docs


def test_hr_employee_cannot_see_their_own_unreleased_hr_decision():
    db,users,ref=submitted();row=db.performance_reviews.docs[0]
    row.update(status='HR_Reviewed',probation_outcome={'outcome':'Confirm'},hr_summary='HR draft decision')
    own_hr={**users['hr'],'employee_id':'staff'}
    loaded,employee=run(flow.record(db,own_hr,ref));view=flow.projection(loaded,own_hr,employee)
    assert view.get('probation_outcome') is None and view.get('hr_summary') is None
    assert not view['can_hr_review']
