from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process, performance_v3_alignment as alignment, performance_v3_reminders as reminders
from .test_performance_v3_end_to_end import configured
from .test_grace_kpi_repair import SessionCollection, Session
from .test_profile_self_service import run


def fixture():
    db, users, cycle, review=configured()
    for name in ('performance_cycles','performance_reviews','performance_peer_tasks','performance_peer_responses','survey_windows','survey_responses','notifications','audit_logs'):
        setattr(db,name,SessionCollection(getattr(db,name).docs))
    async def start_session(): return Session(db)
    db.client=SimpleNamespace(start_session=start_session)
    for item in db.notifications.docs:item['v3_email_pending']=True
    return db,users,cycle,review


def test_unused_open_cycle_is_archived_atomically_and_can_be_recreated():
    db,users,cycle,review=fixture(); employee_before=deepcopy(db.employees.docs)
    from bson import ObjectId
    db.performance_peer_tasks.docs.append({'_id':ObjectId(),'cycle_id':cycle['id'],'tenant_id':'solvit','status':'Assigned'})
    result=run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created with incorrect settings'}))
    assert result['status']=='Archived' and result['id']==cycle['id']
    assert all(r['status']=='Archived' for r in db.performance_reviews.docs)
    assert all(w['status']=='Archived' for w in db.survey_windows.docs)
    assert all(t['status']=='Archived' for t in db.performance_peer_tasks.docs)
    assert all(n['cycle_archived'] and not n['v3_email_pending'] for n in db.notifications.docs)
    assert run(alignment.windows(db,users['staff']))==[]
    assert db.employees.docs==employee_before
    assert run(process.archive(db,users['hr'],cycle['id'],{}))['status']=='Archived'
    with patch.object(process,'today',return_value=date(2026,11,30)):
        created=run(process.create_cycle(db,users['hr'],{'cycle_type':'Year_End','cycle_year':2026,'starts_on':'2026-11-30','approval_reference':'Corrected HR cycle settings','alignment_confirmed':True}))
    assert created['id']!=cycle['id'] and created['status']=='Configured'
    assert len(db.performance_reviews.docs)==1


@pytest.mark.parametrize('field,value',[('self_assessment',{}),('manager_assessment',{}),('peer_summary',{}),('review_meeting',{'location':'Office'})])
def test_work_started_blocks_deletion_without_writes(field,value):
    db,users,cycle,review=fixture(); db.performance_reviews.docs[0][field]=value
    before=deepcopy(db.performance_cycles.docs)
    with pytest.raises(HTTPException):run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created with incorrect settings'}))
    assert db.performance_cycles.docs==before and not any(n.get('cycle_archived') for n in db.notifications.docs)


@pytest.mark.parametrize('kind',['peer_response','survey_response','started_peer','peer_draft','submitting_peer'])
def test_anonymous_responses_and_started_peer_tasks_protect_cycle(kind):
    db,users,cycle,review=fixture()
    if kind=='peer_response': db.performance_peer_responses.docs.append({'cycle_id':cycle['id'],'tenant_id':'solvit','scores':[8]*5})
    elif kind=='survey_response': db.survey_responses.docs.append({'survey_window_id':db.survey_windows.docs[0]['id'],'tenant_id':'solvit'})
    else:
        task={'cycle_id':cycle['id'],'tenant_id':'solvit','status':'Assigned'}
        if kind=='started_peer':task['started_at']='2026-11-30'
        if kind=='peer_draft':task['draft']={}
        if kind=='submitting_peer':task['status']='Submitting'
        db.performance_peer_tasks.docs.append(task)
    with pytest.raises(HTTPException):run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created with incorrect settings'}))
    assert db.performance_cycles.docs[0]['status']=='Open'


def test_staff_and_foreign_tenant_cannot_archive_cycle():
    db,users,cycle,review=fixture()
    for actor in (users['staff'],{**users['hr'],'tenant_id':'foreign'}):
        with pytest.raises(HTTPException):run(process.archive(db,actor,cycle['id'],{'reason':'Created with incorrect settings'}))
    assert db.performance_cycles.docs[0]['status']=='Open'


def test_failed_archive_rolls_back_cycle_reviews_notifications_and_audit():
    db,users,cycle,review=fixture(); before=deepcopy(db.audit_logs.docs)
    with patch.object(db.performance_reviews,'update_one',side_effect=RuntimeError('Synthetic transaction failure')):
        with pytest.raises(RuntimeError):run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created with incorrect settings'}))
    assert db.performance_cycles.docs[0]['status']=='Open'
    assert all(n['v3_email_pending'] for n in db.notifications.docs)
    assert db.audit_logs.docs==before


def test_archiving_does_not_send_pending_cycle_emails():
    db,users,cycle,review=fixture()
    run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created with incorrect settings'}))
    with patch.object(reminders,'outbound_email_enabled',return_value=True),patch('utils.email_routing.action_email',new=AsyncMock()) as send:
        run(reminders.deliver(db,'solvit'))
    send.assert_not_awaited()


def test_prepared_cycle_with_no_reviews_can_be_removed():
    db,users,cycle,review=fixture()
    db.performance_reviews.docs=[]; db.survey_windows.docs=[]; db.notifications.docs=[]
    db.performance_cycles.docs[0]['status']='Configured'
    result=run(process.archive(db,users['hr'],cycle['id'],{'reason':'Prepared with wrong cycle dates'}))
    assert result['unused_reviews']==0 and db.performance_cycles.docs[0]['status']=='Archived'


def test_empty_earlier_cycle_setup_is_manageable_but_existing_reviews_protect_it():
    db,users,cycle,review=fixture()
    db.performance_cycles.docs[0].pop('workflow_version')
    db.performance_cycles.docs[0]['status']='Active'
    with pytest.raises(HTTPException):run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created the earlier setup incorrectly'}))
    db.performance_reviews.docs=[]
    result=run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created the earlier setup incorrectly'}))
    assert result['status']=='Archived'


def test_hr_setup_includes_earlier_cycles_that_can_block_the_same_period():
    from utils import performance_v3_admin as admin
    db,users,cycle,review=fixture()
    db.performance_cycles.docs[0].pop('workflow_version')
    db.performance_reviews.docs=[]
    with patch.object(process,'setup',new=AsyncMock(return_value={'employees':[],'roles':[]})):
        result=run(admin.dashboard(db,users['hr']))
    assert any(c['id']==cycle['id'] for c in result['cycles'])
    assert result['peer_progress']==[]


def test_earlier_cycle_alias_linked_reviews_are_protected():
    db,users,cycle,review=fixture()
    db.performance_cycles.docs[0].pop('workflow_version')
    db.performance_reviews.docs[0]['cycle_id']=str(db.performance_cycles.docs[0]['_id'])
    with pytest.raises(HTTPException):run(process.archive(db,users['hr'],cycle['id'],{'reason':'Created the earlier setup incorrectly'}))
    assert db.performance_cycles.docs[0]['status']=='Open'
