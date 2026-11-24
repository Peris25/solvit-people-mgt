from copy import deepcopy
from unittest.mock import patch,AsyncMock
from utils.my_task_queue import queue
from utils import performance_workflows as flow
from .test_performance_workflows import fixture,run
from .integrity_fakes import Collection


def setup():
    db,users=fixture()
    for name in ('training_requests','performance_peer_tasks','survey_windows','survey_responses'):
        if not hasattr(db,name):setattr(db,name,Collection())
    return db,users


def task(reference,**extra):
    return {'_id':reference,'id':reference,'tenant_id':'solvit','title':'Assigned '+reference,'status':'Pending','created_at':'2026-11-23T09:00:00Z',**extra}


def test_queue_contains_account_and_employee_assignments_but_not_global_or_foreign_tasks():
    db,users=setup();user=users['staff']
    db.tasks.docs=[task('mine',assigned_to=user['id']),task('my-employee',assigned_to='staff'),
                   task('someone-else',assigned_to='other'),task('foreign',assigned_to='staff',tenant_id='foreign'),task('closed',assigned_to='staff',status='Completed')]
    before=deepcopy(db.tasks.docs)
    result=run(queue(db,user))
    assert result['errors']==[] and result['count']==2
    assert {item['reference'] for item in result['items']}=={'mine','my-employee'}
    assert db.tasks.docs==before


def test_hr_does_not_see_another_persons_tasks_in_their_personal_count():
    db,users=setup();db.tasks.docs=[task('other',assigned_to='staff'),task('hr-shared',assigned_role='hr_admin')]
    result=run(queue(db,users['hr']))
    assert result['errors']==[] and result['count']==1
    assert result['items'][0]['reference']=='hr-shared'


def test_role_assignment_does_not_override_an_explicit_different_assignee():
    db,users=setup();db.tasks.docs=[task('other',assigned_to='other',assigned_role='hr_admin')]
    result=run(queue(db,users['hr']))
    assert result['count']==0 and result['items']==[]


def test_forms_and_review_actions_appear_in_same_list_with_correct_links():
    db,users=setup()
    db.form_submissions.docs=[{'_id':'form','id':'form','tenant_id':'solvit','form_id':'form-15','form_title':'Sign form','status':'InProgress','subject_employee_id':'staff','next_required_role':'employee','created_at':'2026-11-23T09:00:00Z'}]
    db.performance_cycles.docs=[{'_id':'cycle','id':'cycle','tenant_id':'solvit','workflow_version':3,'status':'Configured','cycle_type':'Year_End','cycle_year':2099,'starts_on':'2099-01-01','self_due_on':'2099-01-07'}]
    db.performance_reviews.docs=[{'_id':'review','id':'review','tenant_id':'solvit','workflow_version':3,'cycle_id':'cycle','cycle_type':'Year_End','cycle_year':2099,'employee_id':'staff','status':'Self_Draft','section_a_kpis':[],'starts_on':'2099-01-01','self_due_on':'2099-01-07'}]
    result=run(queue(db,users['staff']))
    assert result['errors']==[] and result['count']==2
    assert {item['path'] for item in result['items']}=={'/forms?submission=form','/performance?review=review'}


def test_manager_probation_assessment_is_a_task_without_employee_self_submission():
    from .test_probation_manager_led import setup as probation_setup
    db,users,reference=probation_setup()
    for name in ('training_requests','performance_peer_tasks','survey_windows','survey_responses'):
        if not hasattr(db,name):setattr(db,name,Collection())
    result=run(queue(db,users['manager']))
    assert result['errors']==[]
    assert any(item['reference']==reference and item['title']=='Complete probation manager assessment' for item in result['items'])
    own=run(queue(db,users['staff']))
    assert not any(item['kind']=='review' for item in own['items'])


def test_failed_source_is_reported_not_misrepresented_as_zero_tasks():
    db,users=setup();db.tasks.docs=[task('mine',assigned_to='staff')]
    with patch.object(db.form_submissions,'find',side_effect=RuntimeError('Synthetic database outage')):
        result=run(queue(db,users['staff']))
    assert result['count'] is None and 'Forms' in result['errors']
    assert any(item['reference']=='mine' for item in result['items'])


def test_native_employee_alias_and_account_assignment_are_actionable_without_identity_conflicts():
    from utils.task_access import authorize_task
    db,users=setup();native=db.employees.docs[0]['_id'];user=users['staff']
    db.tasks.docs=[task('native',assigned_to=native),task('account',assigned_to_user_id=user['id']),
                   task('conflict',assigned_to='other',assigned_to_user_id=user['id'])]
    result=run(queue(db,user))
    assert result['errors']==[] and {row['reference'] for row in result['items']}=={'native','account'}
    assert all(row['can_complete'] for row in result['items'])
    for row in db.tasks.docs[:2]:run(authorize_task(db,user,row,write=True))


def test_queue_does_not_silently_truncate_assigned_work_to_old_limits():
    db,users=setup();db.tasks.docs=[task(str(index),assigned_to='staff') for index in range(205)]
    result=run(queue(db,users['staff']))
    assert result['count']==205 and len(result['items'])==205
