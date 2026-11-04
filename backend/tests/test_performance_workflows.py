"""Synthetic performance policy, workflow, confidentiality and integrity tests."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import performance_workflows as service
from routes import performance, employees
from .test_profile_self_service import fixture as base_fixture
from .integrity_fakes import Collection
from .test_notification_centre import Receipts

def run(coro): return asyncio.run(coro)

def fixture():
    db, users = base_fixture()
    for name in ('performance_cycles', 'notification_receipts', 'tasks', 'form_submissions', 'public_holidays', 'onboarding_tasks'):
        setattr(db, name, Collection())
    db.notifications = Receipts()
    db.notification_receipts = Receipts()
    return db, users

def cycle_body(policy='handbook_frd'):
    return {'cycle_type':'Year_End', 'cycle_year':2026, 'starts_on':'2026-10-01', 'self_due_on':'2026-10-07',
            'manager_due_on':'2026-10-14', 'policy':policy, 'approval_reference':'synthetic-policy-approval'}

def create(db, users, policy='handbook_frd'):
    run(service.create_cycle(db, users['hr'], cycle_body(policy)))
    return run(service.create_review(db, users['hr'], {'employee_id':'staff', 'cycle_type':'Year_End','cycle_year':2026}))

def assign(db, users, reference):
    for i in range(3):
        run(service.goals(db, users['manager'], reference, {'action':'assign', 'objective':f'Synthetic objective {i}',
            'metric':'Verified measurement', 'target':'Agreed target', 'due_on':'2026-10-20'}))
    run(service.goals(db, users['staff'], reference, {'action':'acknowledge'}))
    return db.performance_reviews.docs[0]['section_a_kpis']

def self_body(): return {'summary':'Actual self-assessment','achievements':'Recorded results','support_needed':'No additional support','submit':True}

def manager_body(goals): return {'summary':'Evidence-based assessment', 'kpi_scores':[{'goal_id':g['id'],'score':1,'evidence':'Verified result'} for g in goals]}

def assessed(policy='handbook_frd'):
    db, users = fixture(); row = create(db, users, policy); goals = assign(db, users, row['id'])
    run(service.assess(db, users['staff'], row['id'], 'self', self_body()))
    run(service.assess(db, users['manager'], row['id'], 'manager', manager_body(goals)))
    return db, users, row['id']


@pytest.mark.parametrize('actor', ['staff','manager','finance','other'])
def test_cycle_configuration_is_hr_only(actor):
    db, users = fixture()
    with pytest.raises(HTTPException): run(service.create_cycle(db, users[actor], cycle_body()))
    assert not db.performance_cycles.docs


@pytest.mark.parametrize('change', [{'approval_reference':''}, {'policy':'invented'}, {'policy':[]}, {'cycle_type':[]},
    {'cycle_year':True}, {'starts_on':'bad'}, {'self_due_on':'2026-09-01'}, {'manager_due_on':'2026-12-01'}])
def test_cycle_policy_dates_and_types_are_validated(change):
    db, users = fixture()
    with pytest.raises(HTTPException): run(service.create_cycle(db, users['hr'], {**cycle_body(), **change}))
    assert db.performance_cycles.writes == 0


def test_cycle_is_four_weeks_immutable_duplicate_and_overlap_prevented():
    db, users = fixture(); cycle = run(service.create_cycle(db, users['hr'], cycle_body()))
    assert cycle['ends_on'] == '2026-10-28' and cycle['scoring_policy']['weights'] == [50,30,20]
    with pytest.raises(HTTPException): run(service.create_cycle(db, users['hr'], cycle_body()))
    with pytest.raises(HTTPException): run(service.create_cycle(db, users['hr'], {**cycle_body(), 'cycle_type':'Mid_Year'}))
    assert len(db.performance_cycles.docs) == 1 and db.audit_logs.docs[0]['event'] == 'performance.cycle.configured'


def test_review_needs_configured_cycle_and_duplicate_legacy_identity_is_prevented():
    db, users = fixture(); body = {'employee_id':'staff','cycle_type':'Year_End','cycle_year':2026}
    with pytest.raises(HTTPException): run(service.create_review(db, users['hr'], body))
    row = create(db, users)
    db.performance_reviews.docs[0]['employee_id'] = db.employees.docs[0]['_id']
    with pytest.raises(HTTPException): run(service.create_review(db, users['hr'], body))
    assert len(db.performance_reviews.docs) == 1
    db.performance_reviews.docs[0].pop('cycle_type')
    with pytest.raises(HTTPException): run(service.create_review(db, users['hr'], body))


def test_cycle_policy_is_snapshotted_and_not_affected_by_later_master_changes():
    db, users = fixture(); create(db, users)
    db.performance_cycles.docs[0]['scoring_policy']['weights'] = [60,25,15]
    assert db.performance_reviews.docs[0]['scoring_policy']['weights'] == [50,30,20]


@pytest.mark.parametrize('actor', ['staff','other','finance'])
def test_only_authorized_manager_or_hr_assigns_goals(actor):
    db, users = fixture(); row = create(db, users)
    with pytest.raises(HTTPException): run(service.goals(db, users[actor], row['id'], {'action':'assign','objective':'Forged'}))
    assert db.performance_reviews.docs[0]['section_a_kpis'] == []


def test_goal_progress_requires_owner_evidence_and_separate_completion_review():
    db, users = fixture(); row = create(db, users); goals = assign(db, users, row['id'])
    body = {'action':'progress','goal_id':goals[0]['id'],'progress':100,'evidence':'Verified delivery'}
    with pytest.raises(HTTPException): run(service.goals(db, users['other'], row['id'], body))
    result = run(service.goals(db, users['staff'], row['id'], body))
    assert result['section_a_kpis'][0]['status'] == 'Pending_Review'
    with pytest.raises(HTTPException): run(service.goals(db, users['staff'], row['id'], {'action':'review','goal_id':goals[0]['id']}))
    result = run(service.goals(db, users['manager'], row['id'], {'action':'review','goal_id':goals[0]['id']}))
    assert result['section_a_kpis'][0]['status'] == 'Completed'


@pytest.mark.parametrize('change', [{'progress':101}, {'progress':float('nan')}, {'progress':True}, {'target':'forged'}, {'evidence':''}])
def test_progress_validation_and_target_injection(change):
    db, users = fixture(); row = create(db, users); goal = assign(db, users, row['id'])[0]
    with pytest.raises(HTTPException): run(service.goals(db, users['staff'], row['id'], {'action':'progress','goal_id':goal['id'],'progress':10,'evidence':'Actual evidence',**change}))


def test_self_assessment_is_owned_and_cannot_set_scores_or_signatures():
    db, users = fixture(); row = create(db, users); assign(db, users, row['id'])
    for actor in ('other','manager','hr'):
        with pytest.raises(HTTPException): run(service.assess(db, users[actor], row['id'], 'self', self_body()))
    for field in ('overall_score','section_a_score','manager_signature','hr_signature','status'):
        with pytest.raises(HTTPException): run(service.assess(db, users['staff'], row['id'], 'self', {**self_body(), field:1}))
    run(service.assess(db, users['staff'], row['id'], 'self', self_body()))
    with pytest.raises(HTTPException): run(service.goals(db, users['manager'], row['id'], {'action':'assign','objective':'Changed after submission'}))
    assert db.performance_reviews.docs[0]['status'] == 'Self_Submitted'


def test_manager_requires_current_direct_report_three_goals_and_valid_scores():
    db, users = fixture(); row = create(db, users); goals = assign(db, users, row['id'])
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], row['id'], 'manager', manager_body(goals)))
    run(service.assess(db, users['staff'], row['id'], 'self', self_body()))
    forged = manager_body(goals); forged['kpi_scores'][0]['score'] = float('inf')
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], row['id'], 'manager', forged))
    forged = manager_body(goals); forged['kpi_scores'][0]['goal_id'] = 'other'
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], row['id'], 'manager', forged))
    db.employees.docs[0]['line_manager_id'] = 'other'
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], row['id'], 'manager', manager_body(goals)))


@pytest.mark.parametrize('policy,expected', [('handbook_frd',1.7), ('developer_brief',1.6)])
def test_approved_policy_calculation_hr_release_and_audit(policy, expected):
    db, users, reference = assessed(policy)
    body = {'section_b_score':2,'section_c_score':3,'summary':'Approved employee-facing summary','evidence_reference':'Verified source records'}
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], reference, 'hr', body))
    result = run(service.assess(db, users['hr'], reference, 'hr', body))
    assert result['overall_score'] == expected and result['status'] == 'HR_Reviewed'
    employee = db.employees.docs[0]; stored = db.performance_reviews.docs[0]
    assert service.projection(stored, users['staff'], employee)['overall_score'] is None
    with patch('utils.email_triggers.fire_and_forget', new_callable=AsyncMock) as email:
        run(service.assess(db, users['hr'], reference, 'release', {})); assert email.await_count == 1
    visible = service.projection(stored, users['staff'], employee)
    assert visible['overall_score'] == expected and visible['status'] == 'Completed'
    assert 'hr_evidence_reference' not in visible
    assert any(row['event'] == 'performance.assessment.hr' for row in db.audit_logs.docs)
    assert any(row['event'] == 'performance.assessment.release' for row in db.audit_logs.docs)
    with pytest.raises(HTTPException): run(service.assess(db, users['manager'], reference, 'manager', {}))


def test_missing_policy_evidence_cannot_calculate_or_release():
    db, users, reference = assessed()
    db.performance_reviews.docs[0]['scoring_policy'].pop('approval_reference')
    with pytest.raises(HTTPException): run(service.assess(db, users['hr'], reference, 'hr', {'section_b_score':2,'section_c_score':3}))
    with pytest.raises(HTTPException): run(service.assess(db, users['hr'], reference, 'release', {}))
    assert not db.performance_reviews.docs[0].get('overall_score')


def test_notification_recipients_are_private_and_creation_deduplicated():
    db, users = fixture(); row = create(db, users); stored = db.performance_reviews.docs[0]
    count = len(db.notifications.docs); run(service.notify(db, stored, 'created'))
    assert len(db.notifications.docs) == count == 1
    assert {r.get('recipient_id') for r in db.notifications.docs if r.get('recipient_type') == 'employee'} == {'staff'}
    assert all('summary' not in row and 'overall_score' not in row for row in db.notifications.docs)


def test_cycle_distribution_is_retry_safe_and_reports_missing_managers():
    db, users = fixture(); before = deepcopy(db.employees.docs)
    cycle = run(service.create_cycle(db, users['hr'], cycle_body()))
    first = run(service.launch_cycle(db, users['hr'], cycle['id']))
    assert [row['employee_id'] for row in first['created']] == ['staff']
    assert first['needs_review']
    second = run(service.launch_cycle(db, users['hr'], cycle['id']))
    assert second['created'] == [] and len(second['existing']) == 1
    assert len(db.performance_reviews.docs) == 1 and db.employees.docs == before


@pytest.mark.parametrize('actor', ['staff', 'manager', 'finance', 'other'])
def test_only_hr_can_distribute_a_cycle(actor):
    db, users = fixture(); cycle = run(service.create_cycle(db, users['hr'], cycle_body()))
    with pytest.raises(HTTPException): run(service.launch_cycle(db, users[actor], cycle['id']))
    assert not db.performance_reviews.docs


def test_workflow_notifications_follow_next_responsible_person_and_meeting_link():
    from utils.notification_centre import list_inbox
    db, users = fixture(); review = create(db, users); goals = assign(db, users, review['id'])
    before = len(db.notifications.docs)
    run(service.assess(db, users['staff'], review['id'], 'self', {**self_body(), 'submit': False}))
    assert len(db.notifications.docs) == before
    run(service.assess(db, users['staff'], review['id'], 'self', self_body()))
    rows = [n for n in db.notifications.docs if n['data'].get('performance_event') == 'performance.assessment.self']
    assert len(rows) == 1 and rows[0]['recipient_id'] == 'manager'
    run(service.assess(db, users['manager'], review['id'], 'manager', manager_body(goals)))
    rows = [n for n in db.notifications.docs if n['data'].get('performance_event') == 'performance.assessment.manager']
    assert {n['recipient_role'] for n in rows} == {'hr_admin', 'hr_manager', 'general_manager'}
    inbox = run(list_inbox(db, users['hr']))
    assert inbox['items'][0]['title'] == 'Arrange performance review meeting'
    assert inbox['items'][0]['link'] == '/performance?review=' + review['id']
    assert 'kpi_scores' not in str(inbox) and 'summary' not in str(inbox)


def test_hr_meeting_requires_manager_approval_and_preserves_scores():
    from datetime import datetime, timedelta, timezone
    db, users = fixture(); review = create(db, users)
    body = {'scheduled_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), 'location': 'Meeting room'}
    with pytest.raises(HTTPException): run(service.schedule_meeting(db, users['hr'], review['id'], body))
    goals = assign(db, users, review['id'])
    run(service.assess(db, users['staff'], review['id'], 'self', self_body()))
    run(service.assess(db, users['manager'], review['id'], 'manager', manager_body(goals)))
    stored = db.performance_reviews.docs[0]; before = deepcopy(stored)
    for actor in ('staff', 'manager', 'other', 'finance'):
        with pytest.raises(HTTPException): run(service.schedule_meeting(db, users[actor], review['id'], body))
    result = run(service.schedule_meeting(db, users['hr'], review['id'], body))
    assert {key: result['review_meeting'][key] for key in body} == body
    assert result['review_meeting']['participant_employee_ids'] == ['staff', 'manager']
    assert stored['status'] == before['status'] == 'Manager_Submitted'
    assert stored['section_a_score'] == before['section_a_score']
    count = len(db.notifications.docs)
    run(service.schedule_meeting(db, users['hr'], review['id'], body))
    assert len(db.notifications.docs) == count
    notices = [n for n in db.notifications.docs if n['data'].get('performance_event') == 'performance.meeting.scheduled']
    assert {n.get('recipient_id') for n in notices} == {'staff', 'manager'}
    assert not service.projection(stored, users['staff'], db.employees.docs[0])['scores_released']
    from utils.notification_centre import list_inbox
    assert not any(n['title'] == 'Arrange performance review meeting' for n in run(list_inbox(db, users['hr']))['items'])


@pytest.mark.parametrize('body', [{'scheduled_at': '2020-01-01T10:00:00+00:00', 'location': 'Room'}, {'scheduled_at': '2099-01-01T10:00:00', 'location': 'Room'}, {'scheduled_at': '2099-01-01T10:00:00+00:00', 'location': 'Room', 'overall_score': 3}])
def test_meeting_rejects_past_ambiguous_time_and_forged_scores(body):
    db, users, reference = assessed()
    with pytest.raises(HTTPException): run(service.schedule_meeting(db, users['hr'], reference, body))
    assert 'review_meeting' not in db.performance_reviews.docs[0]


def test_self_submission_emails_only_the_saved_manager_once_without_review_answers():
    db, users = fixture(); review = create(db, users); assign(db, users, review['id'])
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(service.assess(db, users['staff'], review['id'], 'self', {**self_body(), 'submit': False}))
        send.assert_not_awaited()
        run(service.assess(db, users['staff'], review['id'], 'self', self_body()))
        with pytest.raises(HTTPException): run(service.assess(db, users['staff'], review['id'], 'self', self_body()))
    assert send.await_count == 1
    payload = send.await_args.kwargs
    assert payload['to'] == db.employees.docs[4]['work_email']
    assert payload['template_key'] == 'performance.self_review_submitted'
    assert '/performance?review=' in payload['context']['platform_link']
    assert 'Actual self-assessment' not in str(payload) and 'kpi_scores' not in str(payload)
    assert db.performance_reviews.docs[0]['manager_email_status'] == 'sent'


def test_email_disabled_policy_is_preserved_and_submission_is_not_lost():
    db, users = fixture(); review = create(db, users); assign(db, users, review['id'])
    with patch.dict('os.environ', {'OUTBOUND_EMAIL_ENABLED': 'false'}), patch('utils.email_service._attempt_send', new=AsyncMock()) as transport:
        run(service.assess(db, users['staff'], review['id'], 'self', self_body()))
    transport.assert_not_awaited()
    assert db.performance_reviews.docs[0]['status'] == 'Self_Submitted'
    assert db.performance_reviews.docs[0]['manager_email_status'] == 'skipped'


def test_calendar_options_exclude_holidays_and_participant_leave_without_booking():
    from datetime import datetime, timedelta, timezone
    db, users, reference = assessed()
    tomorrow = (datetime.now(timezone(timedelta(hours=3))).date() + timedelta(days=1)).isoformat()
    run(db.public_holidays.insert_one({'tenant_id': 'solvit', 'date': tomorrow, 'name': 'Synthetic holiday'}))
    leave_date = (datetime.now(timezone(timedelta(hours=3))).date() + timedelta(days=2)).isoformat()
    run(db.leave_requests.insert_one({'tenant_id': 'solvit', 'employee_id': 'manager', 'status': 'Approved', 'start_date': leave_date, 'end_date': leave_date, 'medical_notes': 'PRIVATE'}))
    result = run(service.meeting_date_options(db, users['hr'], reference))
    assert tomorrow not in result['dates'] and leave_date not in result['dates']
    assert result['dates'] and len(result['dates']) <= 10
    assert 'manually' in result['notice'] and 'PRIVATE' not in str(result)
    assert 'review_meeting' not in db.performance_reviews.docs[0]
    for actor in ('staff', 'finance', 'other'):
        with pytest.raises(HTTPException): run(service.meeting_date_options(db, users[actor], reference))


def test_notification_centre_links_only_authorized_review_and_contains_no_scores():
    from utils.notification_centre import list_inbox
    db, users = fixture(); row = create(db, users)
    inbox = run(list_inbox(db, users['staff']))
    assert len(inbox['items']) == 1 and inbox['items'][0]['link'] == '/performance?review=' + row['id']
    assert run(list_inbox(db, users['other']))['items'] == []
    assert 'approval_reference' not in str(inbox) and 'overall_score' not in str(inbox)


def test_historical_scores_are_not_recalculated_and_require_explicit_publication():
    db, users = fixture(); old = {'id':'legacy', 'tenant_id':'solvit', 'employee_id':str(db.employees.docs[0]['_id']),
        'status':'Completed', 'overall_score':2.2, 'section_a_score':2, 'section_b_score':2.3, 'section_c_score':2.5,
        'form_data_json':{'anonymous_peer_identity':'private'}}
    run(db.performance_reviews.insert_one(old)); stored = db.performance_reviews.docs[0]; before = deepcopy(stored)
    with pytest.raises(HTTPException): run(service.assess(db, users['hr'], 'legacy', 'hr', {}))
    assert stored == before
    assert service.projection(stored, users['staff'], db.employees.docs[0])['overall_score'] is None
    result = run(service.assess(db, users['hr'], 'legacy', 'legacy-release', {'approval_reference':'synthetic-publication-approval'}))
    assert result['overall_score'] == 2.2 and stored['section_c_score'] == 2.5
    assert 'anonymous_peer_identity' not in str(service.projection(stored, users['staff'], db.employees.docs[0]))


def test_unreleased_profile_timeline_and_history_do_not_disclose_scores():
    db, users = fixture(); run(db.performance_reviews.insert_one({'id':'legacy','tenant_id':'solvit','employee_id':'staff','overall_score':1.7,'rating':'Exceeded','created_at':'2026-01-01'}))
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', return_value=users['staff']):
        data = run(employees.get_employee_profile('staff', SimpleNamespace()))
    assert data['performance_history'][0]['score'] is None
    assert '1.7' not in str(data['timeline'])


def test_board_only_employee_is_excluded_from_hr_reviews():
    db, users = fixture(); db.employees.docs[0]['board_only'] = True
    with pytest.raises(HTTPException): run(service.employee_access(db, users['hr'], 'staff'))


def test_self_approval_and_direct_legacy_update_bypass_are_blocked():
    db, users, reference = assessed(); self_hr = {**users['hr'], 'employee_id':'staff'}
    with pytest.raises(HTTPException): run(service.assess(db, self_hr, reference, 'hr', {}))
    with patch.object(performance,'get_db', return_value=db), patch.object(performance,'get_current_user',return_value=users['hr']):
        with pytest.raises(HTTPException): run(performance.update_review(reference, performance.ReviewUpdate(status='Completed'), None))


def test_legacy_review_forms_cannot_bypass_scoring_or_leak_manager_assessments():
    from routes import forms
    db, users = fixture()
    db.form_submissions = Collection([{'id':'legacy-form', 'tenant_id':'solvit', 'form_id':'form-06',
        'subject_employee_id':'staff', 'data':{'employee_id':'staff','overall_score':1.2,'private_manager_notes':'secret'},
        'status':'InProgress', 'next_required_role':'employee', 'current_step_index':0}])
    request = SimpleNamespace(json=AsyncMock(return_value={'employee_id':'staff','data':{'overall_score':1}}))
    with patch.object(forms,'get_db',return_value=db), patch.object(forms,'get_current_user',return_value=users['staff']):
        for action in (lambda:forms.start_form_submission('form-06',request), lambda:forms.submit_form('form-06',request), lambda:forms.sign_form_step('legacy-form',request)):
            with pytest.raises(HTTPException) as error: run(action())
            assert error.value.status_code == 409
        visible = run(forms.get_submissions('staff',request))
        assert 'overall_score' not in str(visible) and 'secret' not in str(visible)
        assert run(forms.my_form_tasks(request)) == []
    assert db.form_submissions.writes == 0


def test_real_mongo_serializes_duplicate_review_creation_and_preserves_notification_payloads():
    from .test_employee_integrity_mongo import local_database
    from utils.employee_integrity import integrity_write
    async def exercise():
        async with local_database() as db:
            seed, users = fixture()
            await db.employees.insert_many(deepcopy(seed.employees.docs))
            await db.users.insert_many(deepcopy(seed.users.docs))
            async with integrity_write(db): await service.create_cycle(db, users['hr'], cycle_body())
            async def attempt():
                try:
                    async with integrity_write(db):
                        return await service.create_review(db, users['hr'], {'employee_id':'staff','cycle_type':'Year_End','cycle_year':2026})
                except HTTPException as error: return error.status_code
            results = await asyncio.gather(attempt(), attempt())
            assert 409 in results and await db.performance_reviews.count_documents({}) == 1
            rows = await db.notifications.find({}).to_list(None)
            assert len(rows) == 4 and sum(row.get('recipient_type') == 'employee' for row in rows) == 2
            assert await db.integrity_locks.count_documents({}) == 0
    run(exercise())


def test_goals_require_employee_signoff_before_assessment_and_cannot_change_afterwards():
    db, users = fixture(); row = create(db, users)
    with pytest.raises(HTTPException): run(service.assess(db, users['staff'], row['id'], 'self', self_body()))
    assign(db, users, row['id'])
    with pytest.raises(HTTPException): run(service.goals(db, users['manager'], row['id'], {'action':'assign','objective':'Late target'}))
    assert db.performance_reviews.docs[0]['goals_acknowledged_by'] == users['staff']['id']


def test_named_nine_box_is_hr_only_and_other_tenant_scores_are_not_exposed():
    db, users = fixture(); row = create(db, users)
    stored = db.performance_reviews.docs[0]; stored.update(nine_box_placement='Stars', overall_score=1.2)
    with patch.object(performance,'get_db', return_value=db), patch.object(performance,'get_current_user',return_value={**users['hr'], 'tenant_id':'different-tenant'}):
        assert all(not items for items in run(performance.get_nine_box_matrix(None,2026)).values())
    with patch.object(performance,'get_db', return_value=db), patch.object(performance,'get_current_user',return_value={**users['manager'], 'role':'executive'}):
        with pytest.raises(HTTPException): run(performance.get_nine_box_matrix(None,2026))


def test_staff_home_contains_only_own_performance_action_and_no_unreleased_score():
    from .test_staff_home import fixture as home_fixture, load
    db, user, _ = home_fixture()
    db.performance_reviews = Collection([{'id':'own-review','employee_id':'staff','tenant_id':'solvit',
        'workflow_version':1,'status':'Draft','self_due_on':'2026-10-20','overall_score':1.2},
        {'id':'other-review','employee_id':'other','tenant_id':'solvit','workflow_version':1,'status':'Draft'}])
    data = load(db,user)
    assert data['reviews'][0]['overall_score'] is None
    assert [task['id'] for task in data['tasks'] if task['kind'] == 'performance'] == ['own-review']
    assert any(link['path'] == '/performance' for link in data['quick_links'])


def test_failed_audit_does_not_save_assessment_and_retains_integrity_lock_for_review():
    db, users = fixture(); row = create(db, users); assign(db, users, row['id'])
    request = SimpleNamespace(json=AsyncMock(return_value=self_body()))
    with patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('synthetic audit interruption')), patch.object(performance,'get_db',return_value=db), patch.object(performance,'get_current_user',return_value=users['staff']):
        with pytest.raises(RuntimeError): run(performance.submit_assessment(row['id'],'self',request))
    assert db.performance_reviews.docs[0]['status'] == 'Draft'
    assert len(db.integrity_locks.docs) == 1


@pytest.mark.parametrize('grant', [{'level':'Read','scope':'own_record'}, None])
def test_explicit_module_readonly_or_revocation_blocks_self_service_writes(grant):
    from utils.access_matrix import RUNTIME_OVERRIDES
    db, users = fixture(); row = create(db, users); assign(db, users, row['id'])
    with patch.dict(RUNTIME_OVERRIDES, {('M05','employee'):grant}):
        with pytest.raises(HTTPException): run(service.assess(db, users['staff'], row['id'], 'self', self_body()))
        with pytest.raises(HTTPException): run(service.goals(db, users['staff'], row['id'], {'action':'acknowledge'}))
        assert not service.projection(db.performance_reviews.docs[0],users['staff'],db.employees.docs[0])['can_self_assess']
    assert db.performance_reviews.docs[0]['status'] == 'Draft'


def test_hr_own_unpublished_placement_is_not_leaked_by_matrix():
    db, users = fixture(); create(db, users)
    db.performance_reviews.docs[0].update(nine_box_placement='Stars',overall_score=1.2)
    actor = {**users['hr'],'employee_id':'staff'}
    with patch.object(performance,'get_db',return_value=db), patch.object(performance,'get_current_user',return_value=actor):
        assert all(not items for items in run(performance.get_nine_box_matrix(None,2026)).values())
        db.performance_reviews.docs[0].update(released_at=service.now(),released_by='another-authorized-hr')
        assert run(performance.get_nine_box_matrix(None,2026))['Stars'][0]['score'] == 1.2


def test_manager_proposal_notifies_hr_and_employee_then_hr_confirms_both_participants():
    db, users, reference = assessed()
    body = {'scheduled_at':'2099-11-05T10:00:00+03:00'}
    before = len(db.notifications.docs)
    result = run(service.propose_meeting(db, users['manager'], reference, body))
    assert result['meeting_proposal']['scheduled_at'] == body['scheduled_at']
    assert 'review_meeting' not in result
    messages = db.notifications.docs[before:]
    assert any(n.get('recipient_id') == 'staff' for n in messages)
    assert any(n.get('recipient_role') == 'hr_admin' for n in messages)
    count = len(db.notifications.docs)
    run(service.propose_meeting(db, users['manager'], reference, body))
    assert len(db.notifications.docs) == count
    run(service.schedule_meeting(db, users['hr'], reference, {**body,'location':'Review room'}))
    confirmed = [n for n in db.notifications.docs if n.get('data',{}).get('performance_event') == 'performance.meeting.scheduled']
    assert {n['recipient_id'] for n in confirmed} == {'staff','manager'}
    with pytest.raises(HTTPException): run(service.propose_meeting(db, users['manager'], reference, body))


@pytest.mark.parametrize('actor',['staff','other','finance','hr'])
def test_only_direct_manager_can_propose_review_date(actor):
    db, users, reference = assessed()
    with pytest.raises(HTTPException):
        run(service.propose_meeting(db, users[actor], reference, {'scheduled_at':'2099-11-05T10:00:00Z'}))
    assert not db.performance_reviews.docs[0].get('meeting_proposal')


@pytest.mark.parametrize('body',[{'scheduled_at':'2020-01-01T10:00:00Z'}, {'scheduled_at':'2099-01-01T10:00:00'}, {'scheduled_at':'bad'}, {'scheduled_at':'2099-01-01T10:00:00Z','employee_id':'other'}])
def test_proposal_rejects_past_naive_invalid_and_forged_fields(body):
    db, users, reference = assessed()
    with pytest.raises(HTTPException): run(service.propose_meeting(db, users['manager'], reference, body))
    assert not db.performance_reviews.docs[0].get('meeting_proposal')


def test_manager_gets_portal_date_options_without_hr_schedule_permission():
    db, users, reference = assessed()
    assert 'dates' in run(service.meeting_date_options(db, users['manager'], reference))
    with pytest.raises(HTTPException):
        run(service.schedule_meeting(db, users['manager'], reference, {'scheduled_at':'2099-01-01T10:00:00Z','location':'Room'}))


def test_proposal_requires_manager_assessment_and_never_changes_scores():
    db, users = fixture(); row = create(db, users)
    with pytest.raises(HTTPException):
        run(service.propose_meeting(db, users['manager'], row['id'], {'scheduled_at':'2099-01-01T10:00:00Z'}))
    assert not db.performance_reviews.docs[0].get('meeting_proposal')


def test_proposed_and_confirmed_notification_previews_link_to_review():
    from utils.notification_centre import list_inbox
    db, users, reference = assessed()
    body = {'scheduled_at':'2099-11-05T10:00:00Z'}
    run(service.propose_meeting(db, users['manager'], reference, body))
    for actor in ('staff','hr'):
        items = run(list_inbox(db, users[actor]))['items']
        proposal = [n for n in items if n['title'] == 'Review meeting date proposed']
        assert proposal and reference in proposal[0]['link']
        assert 'HR confirmation is pending' in proposal[0]['message']
    run(service.schedule_meeting(db, users['hr'], reference, {**body,'location':'Meeting room'}))
    for actor in ('staff','manager'):
        items = run(list_inbox(db, users[actor]))['items']
        assert any(n['title'] == 'Performance review meeting scheduled' and reference in n['link'] for n in items)
        assert not any(n['title'] == 'Review meeting date proposed' for n in items)
