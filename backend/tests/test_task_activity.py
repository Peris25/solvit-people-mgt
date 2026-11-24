from copy import deepcopy
from datetime import datetime
from utils.task_activity import current,current_checklist
from utils.my_task_queue import queue
from .test_my_task_queue import setup,task
from .test_performance_workflows import run


def test_boundary_uses_monday_midnight_nairobi_not_utc_midnight():
    assert not current({'created_at':'2026-11-22T20:59:59Z'})
    assert current({'created_at':'2026-11-22T21:00:00Z'})
    assert current({'created_at':datetime(2026,11,22,21,0)})
    assert current({'created_at':'2026-11-23'})


def test_old_future_due_or_recently_updated_task_is_not_revived():
    assert not current({'created_at':'2026-10-01','due_date':'2026-12-04','updated_at':'2026-11-24T09:00:00Z'})
    assert not current({'due_date':'2026-12-04'})
    assert current({'created_at':'2026-10-01','assigned_at':'2026-11-23T09:00:00Z'})


def test_retrospectively_generated_checklist_uses_employee_start_not_creation_date():
    assert not current_checklist({'created_at':'2026-11-24'}, {'start_date':'2026-10-05'})
    assert current_checklist({'created_at':'2026-11-20'}, {'start_date':'2026-11-23'})
    assert current_checklist({'assigned_at':'2026-11-24'}, {'start_date':'2026-10-05'})


def test_queue_keeps_monday_work_and_preserves_older_records_without_completing_them():
    db,users=setup();db.tasks.docs=[task('old',assigned_to='staff',created_at='2026-11-01',due_date='2026-12-04'),task('current',assigned_to='staff')]
    original=deepcopy(db.tasks.docs)
    result=run(queue(db,users['staff']))
    assert result['errors']==[] and result['count']==1 and result['items'][0]['reference']=='current'
    assert result['active_since']=='2026-11-23' and db.tasks.docs==original


def test_old_induction_with_future_checkin_does_not_enter_the_manager_queue():
    db,users=setup();db.employees.docs[0]['start_date']='2026-10-05'
    db.onboarding_tasks.docs=[{'_id':'old-checkin','tenant_id':'solvit','entity_type':'employee','entity_id':'staff','assigned_role':'line_manager','title':'60-day check-in','created_at':'2026-11-24','due_date':'2026-12-04','status':'Pending'}]
    result=run(queue(db,users['manager']))
    assert result['errors']==[] and not any(item['reference']=='old-checkin' for item in result['items'])
    assert db.onboarding_tasks.docs[0]['status']=='Pending'
