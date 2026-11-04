import pytest
from copy import deepcopy
from fastapi import HTTPException
from utils import performance_workflows as flow
from .test_performance_workflows import fixture, run, self_body


def body(**changes):
    return {"employee_id":"staff","cycle_type":"Year_End","cycle_year":2099,"starts_on":"2099-01-01",
        "self_due_on":"2099-01-07","manager_due_on":"2099-01-14","review_due_on":"2099-01-28",
        "policy":"handbook_frd","policy_confirmed":True,**changes}


def test_hr_creates_individual_review_with_all_dates_without_global_cycle():
    db, users = fixture(); before=deepcopy(db.employees.docs)
    result=run(flow.create_review(db,users['hr'],body()))
    assert result['self_due_on']=='2099-01-07' and result['review_due_on']=='2099-01-28'
    assert result['review_scope']=='individual' and not db.performance_cycles.docs
    assert result['scoring_policy']['approved_by']==users['hr']['id']
    assert db.employees.docs==before and db.notifications.docs
    with pytest.raises(HTTPException): run(flow.create_review(db,users['hr'],body()))
    assert len(db.performance_reviews.docs)==1


@pytest.mark.parametrize('actor',['staff','manager','other','finance'])
def test_only_hr_can_create_individual_review(actor):
    db,users=fixture()
    with pytest.raises(HTTPException):run(flow.create_review(db,users[actor],body()))
    assert not db.performance_reviews.docs


@pytest.mark.parametrize('changes',[{'policy_confirmed':False},{'policy':'invented'},{'self_due_on':'2098-01-01'},
    {'manager_due_on':'2099-01-01'},{'review_due_on':'2099-02-28'},{'starts_on':'bad'},{'employee_id':'foreign'}])
def test_validation_rejects_unapproved_policy_invalid_dates_and_identity(changes):
    db,users=fixture()
    with pytest.raises(HTTPException):run(flow.create_review(db,users['hr'],body(**changes)))
    assert not db.performance_reviews.docs


def probation(db,users,month=1):
    db.employees.docs[0]['lifecycle_state']='Onboarding'
    return run(flow.create_review(db,users['hr'],body(cycle_type='Probation',review_month=month,policy=None,policy_confirmed=False)))


def test_probation_months_distinct_eligible_and_no_scoring_or_status_mutation():
    db,users=fixture()
    with pytest.raises(HTTPException):run(flow.create_review(db,users['hr'],body(cycle_type='Probation',review_month=1,policy=None,policy_confirmed=False)))
    one=probation(db,users,1); two=probation(db,users,2)
    assert one['id']!=two['id'] and one['review_month']==1
    assert one['scoring_policy']['source']=='probation_form_08' and 'weights' not in one['scoring_policy']
    assert db.employees.docs[0]['lifecycle_state']=='Onboarding'
    with pytest.raises(HTTPException):probation(db,users,1)


def test_probation_self_manager_hr_release_and_meeting_flow_has_no_numeric_scores():
    db,users=fixture(); row=probation(db,users,3); ref=row['id']
    run(flow.assess(db,users['staff'],ref,'self',self_body()))
    assessment={'summary':'Verified review','delivery_rating':'Meets','values_rating':'Strong',
        'specific_examples':'Recorded work evidence','areas_for_improvement':'None','recommendation':'Confirm'}
    with pytest.raises(HTTPException):run(flow.assess(db,users['staff'],ref,'manager',assessment))
    run(flow.assess(db,users['manager'],ref,'manager',assessment))
    run(flow.propose_meeting(db,users['manager'],ref,{'scheduled_at':'2099-01-20T10:00:00+03:00'}))
    run(flow.schedule_meeting(db,users['hr'],ref,{'scheduled_at':'2099-01-20T10:00:00+03:00','location':'Meeting room'}))
    with pytest.raises(HTTPException):run(flow.assess(db,users['hr'],ref,'hr',{'summary':'Verified','overall_score':1}))
    run(flow.assess(db,users['hr'],ref,'hr',{'summary':'Discussed manager recommendation and next steps'}))
    result=run(flow.assess(db,users['hr'],ref,'release',{}))
    assert result['status']=='Completed' and result.get('overall_score') is None
    assert db.employees.docs[0]['lifecycle_state']=='Onboarding'
    assert any(n.get('data',{}).get('performance_event')=='performance.meeting.scheduled' for n in db.notifications.docs)


def test_probation_rejects_final_recommendation_before_final_month():
    db,users=fixture(); row=probation(db,users,1)
    run(flow.assess(db,users['staff'],row['id'],'self',self_body()))
    with pytest.raises(HTTPException):run(flow.assess(db,users['manager'],row['id'],'manager',{
        'summary':'Verified','delivery_rating':'Meets','values_rating':'Strong','specific_examples':'Evidence',
        'areas_for_improvement':'None','recommendation':'Confirm'}))
    assert db.performance_reviews.docs[0]['status']=='Self_Submitted'
