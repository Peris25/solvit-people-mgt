"""Requested 50/30/20, manager scores, selected peers and release boundaries."""
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process, performance_v3_peers as peers
from utils import performance_v3_reviews as reviews, performance_v3_scoring as scoring
from .test_performance_v3_peers import configured as peer_fixture, payload
from .test_performance_v3_reviews import review, self_payload
from .test_performance_v3_end_to_end import configured
from .test_profile_self_service import fixture, run


def test_self_submission_requires_no_evidence_and_rejects_an_unapproved_score():
    db, users = fixture(); row=review(); body=self_payload()
    body['assessment']['actuals']['quality'].pop('evidence')
    async def save(db,user,row,update,event): return {**row,**update}
    with patch.object(process,'record',AsyncMock(return_value=(row,db.employees.docs[0]))), patch.object(process,'today',return_value=date(2026,11,2)), patch.object(process,'evidence',AsyncMock(return_value=[])), patch.object(process,'save',side_effect=save), patch.object(process,'notice',AsyncMock()):
        result=run(reviews.self_assessment(db,users['staff'],row['id'],body))
        assert result['status']=='Self_Submitted'
        body['assessment']['actuals']['quality']['self_score']=1.2
        with pytest.raises(HTTPException): run(reviews.self_assessment(db,users['staff'],row['id'],body))


def test_manager_scores_not_actuals_determine_weighted_section_a_and_draft_stays_open():
    db,users=fixture(); row={**review(),'status':'Self_Submitted','self_assessment':self_payload()['assessment']}
    async def save(db,user,row,update,event): return {**row,**update}
    with patch.object(process,'record',AsyncMock(return_value=(row,db.employees.docs[0]))), patch.object(process,'today',return_value=date(2026,11,9)), patch.object(process,'save',side_effect=save), patch.object(process,'hr_notice',AsyncMock()) as notice:
        draft=run(reviews.manager_assessment(db,users['manager'],row['id'],{'expected_version':'original','submit':False,'actuals':{'quality':{'comment':'Draft'}}}))
        assert draft['status']=='Self_Submitted' and draft['section_a_score'] is None
        notice.assert_not_awaited()
        with pytest.raises(HTTPException): run(reviews.manager_assessment(db,users['manager'],row['id'],{'expected_version':'original','actuals':{'quality':{'score':2,'comment':''}}}))
        result=run(reviews.manager_assessment(db,users['manager'],row['id'],{'expected_version':'original','actuals':{'quality':{'score':2,'comment':'Explained difference'}}}))
        assert result['section_a_score']==2 and result['manager_assessment']['actuals']['quality']['actual']==90
        assert notice.await_count==1
    goals=[{'id':'a','weight':60},{'id':'b','weight':40}]
    assert scoring.weighted_kpi_scores(goals,{'a':1,'b':2})['score']==1.4


def test_five_chosen_colleagues_and_two_anonymous_comments_are_enforced():
    db,users=peer_fixture()
    body={**payload(),'strengthens_team':'Helps teammates','more_effective':'Share updates earlier'}
    with patch.object(process,'cycle',AsyncMock(return_value={'status':'Open','starts_on':'2026-11-01'})), patch.object(process,'today',return_value=date(2026,11,2)):
        removed=db.performance_peer_tasks.docs.pop()
        with pytest.raises(HTTPException):run(peers.submit(db,users['other'],'task',body))
        assert not db.performance_peer_responses.docs
        db.performance_peer_tasks.docs.append(removed)
        assert run(peers.submit(db,users['other'],'task',body))['status']=='Submitted'
    response=db.performance_peer_responses.docs[0]
    assert response['strengthens_team']=='Helps teammates' and response['more_effective']=='Share updates earlier'
    assert not {'reviewer_employee_id','user_id','actor_id','submitted_at','task_id'} & set(response)


def test_private_partial_peer_draft_cannot_be_removed_after_starting():
    db,users=peer_fixture()
    with patch.object(process,'cycle',AsyncMock(return_value={'status':'Open','starts_on':'2026-11-01'})), patch.object(process,'today',return_value=date(2026,11,2)):
        assert run(peers.draft(db,users['other'],'task',{'scores':[8,'','','',''],'strengthens_team':'Private draft'}))['status']=='Draft saved'
        visible=run(peers.listing(db,users['other']))
        assert visible[0]['draft']['strengthens_team']=='Private draft' and not visible[0]['can_remove']
        with pytest.raises(HTTPException):run(peers.remove(db,users['other'],'task',{}))
        with pytest.raises(HTTPException):run(peers.draft(db,users['staff'],'task',{}))
    assert not db.performance_peer_responses.docs


def test_company_wide_selection_and_manager_privacy_until_release():
    db,users,cycle,row=configured()
    with patch.object(process,'today',return_value=date(2026,11,30)):
        assert not db.performance_peer_tasks.docs
        options=run(peers.choices(db,users['other']))
        assert any(option['review_id']==row['id'] for option in options)
        assert run(peers.choose(db,users['other'],row['id'],{}))['status']=='Selected'
        assert len(db.performance_peer_tasks.docs)==1
        with pytest.raises(HTTPException):run(peers.choose(db,users['staff'],row['id'],{}))
    row['peer_summary']={'response_count':3,'averages':[8]*5,'score':2,'retention_average':10,'strengthens_team':['Anonymous strength']}
    with patch.object(process,'today',return_value=date(2026,12,7)):
        assert 'peer_summary' not in process.projection(row,users['manager'],db.employees.docs[0])
        row.update(released_at='2026-12-07T12:00:00Z',released_by='hr')
        released=process.projection(row,users['manager'],db.employees.docs[0])
        assert released['peer_summary']['averages']==[8]*5
        assert 'retention_average' not in released['peer_summary']
        row['peer_summary']['response_count']=2
        assert 'peer_summary' not in process.projection(row,users['manager'],db.employees.docs[0])


def test_configuring_a_future_cycle_does_not_send_staff_notifications():
    db,users,cycle,row=configured(); db.notifications.docs.clear()
    db.performance_cycles.docs.clear(); db.performance_reviews.docs.clear()
    with patch.object(process,'today',return_value=date(2027,1,1)):
        prepared=run(process.create_cycle(db,users['hr'],{'cycle_type':'Year_End','cycle_year':2027,'starts_on':'2027-01-04','approval_reference':'Synthetic approved policy','alignment_confirmed':True}))
        assert prepared['status']=='Configured' and not db.notifications.docs
    with patch.object(process,'today',return_value=date(2027,1,4)):
        run(process.open_cycle(db,users['hr'],prepared['id'],['staff']))
        count=len(db.notifications.docs)
        run(process.open_cycle(db,users['hr'],prepared['id'],['staff']))
        assert count>0 and len(db.notifications.docs)==count


def test_company_talent_density_uses_50_30_20_and_all_fte_coverage():
    from utils import performance_v3_alignment as alignment
    db,users,cycle,row=configured()
    workforce=[employee for employee in db.employees.docs if process.enabled(employee) and process.fte(employee)]
    db.performance_reviews.docs=[]
    for index,employee in enumerate(workforce):
        db.performance_reviews.docs.append({**deepcopy(row),'id':f'company-review-{index}','employee_id':employee['id'],'released_at':'2026-12-07T12:00:00Z','released_by':'hr','section_b_score':1.8,'nine_box_placement':'Stars' if index<4 else 'Exit_Track'})
    for _ in range(3):
        run(db.survey_responses.insert_one({'tenant_id':'solvit','cycle_id':cycle['id'],'performance_workflow_version':3,'overall_alignment_score':76}))
    with patch.object(process,'today',return_value=date(2026,12,7)):
        result=run(alignment.report(db,users['hr'],cycle['id']))
        assert result['weights']==[50,30,20] and result['talent_density']==73.2
        assert result['components']=={'primary_stars_core_pct':80,'secondary_values_avg_pct':60,'alignment_survey_pct':76}
        db.performance_reviews.docs.pop()
        assert 'talent_density' not in run(alignment.report(db,users['hr'],cycle['id']))
