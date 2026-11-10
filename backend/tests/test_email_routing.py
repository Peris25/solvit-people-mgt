import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch
import pytest
from utils import email_routing as routing
from automation.engine import AutomationEngine
from .test_profile_self_service import fixture as base_fixture
from .integrity_fakes import Collection, account


def run(coro): return asyncio.run(coro)


def fixture():
    db, users = base_fixture(); db.email_log = Collection()
    db.users.docs.extend([
        account('inactive@example.com', role='hr_admin', is_active=False),
        account('foreign@example.com', role='hr_admin', tenant_id='foreign'),
        account('it@example.com', role='it_admin'),
        account('other-manager@example.com', role='line_manager', employee_id='other'),
        account('hr@example.com', role='hr_admin')])
    return db, users


@pytest.fixture(autouse=True)
def enabled(monkeypatch): monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'true')


def calls(send): return [call.kwargs for call in send.await_args_list]


@pytest.mark.parametrize('event,status', [('submitted','Pending_Manager'), ('decision','Pending_HR')])
def test_hr_leave_actions_are_scoped_and_deduplicated(event, status):
    db, _ = fixture(); row = {'id': 'leave', 'tenant_id': 'solvit', 'status': status, 'line_manager_id': 'manager', 'approval_history': []}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(routing.leave_action(db, db.employees.docs[0], row, event))
        run(routing.leave_action(db, db.employees.docs[0], row, event))
    assert [call['to'] for call in calls(send)] == ['hr@example.com']
    assert '/leave?view=team&amp;request=leave' in calls(send)[0]['html']
    assert 'medical' not in calls(send)[0]['html']


def test_withdrawal_alerts_only_hr_and_actual_manager():
    db, _ = fixture(); row = {'id':'leave', 'tenant_id':'solvit', 'line_manager_id':str(db.employees.docs[4]['_id'])}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(routing.leave_action(db, db.employees.docs[0], row, 'withdrawn'))
    assert {call['to'] for call in calls(send)} == {'hr@example.com', 'manager@example.com'}


@pytest.mark.parametrize('event,expected', [('created', {'staff@example.com'}),
    ('performance.assessment.manager:version', {'hr@example.com'}),
    ('performance.meeting.proposed:version', {'hr@example.com'}),
    ('performance.meeting.scheduled:version', {'staff@example.com','manager@example.com'}),
    ('performance.goal.update:version', set())])
def test_performance_action_flow(event, expected):
    db, _ = fixture(); row = {'id':'review', 'tenant_id':'solvit'}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(routing.performance_action(db, db.employees.docs[0], db.employees.docs[4], row, event))
    assert {call['to'] for call in calls(send)} == expected
    assert all('/performance?review=review' in call['html'] for call in calls(send))
    assert all('score' not in call['html'] and 'assessment answers' not in call['html'] for call in calls(send))


@pytest.mark.parametrize('eligible', [True, False])
def test_solver_acknowledgement_is_separate_from_hr_alert_and_not_sent_to_it(eligible):
    db, _ = fixture(); row = {'id':'applicant', 'tenant_id':'solvit', 'email':'applicant@example.com'}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(routing.solver_application(db, row, {'id':'requisition'}, eligible))
    by_address = {call['to']:call for call in calls(send)}
    assert set(by_address) == {'hr@example.com','applicant@example.com'}
    assert by_address['hr@example.com']['subject'] == 'New Solver application received'
    assert 'Thank you for applying' in by_address['applicant@example.com']['html']
    assert ('/solver-eligible' if eligible else '/solver-ineligible') in by_address['hr@example.com']['html']


def test_two_workers_claim_only_one_email_and_disabled_policy_creates_no_claim(monkeypatch):
    db, _ = fixture()
    async def dispatch():
        return await asyncio.gather(*(routing.action_email(db,'solvit','event','staff@example.com','Action','Please review.','https://people.solvit.co.ke/leave') for _ in range(2)))
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(dispatch())
    assert send.await_count == 1
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','false')
    run(routing.action_email(db,'solvit','disabled','staff@example.com','Action','Please review.','https://people.solvit.co.ke'))
    assert len(db.email_log.docs) == 1


def test_legacy_automation_emails_only_actual_manager_and_never_role_broadcast():
    db, _ = fixture(); engine = AutomationEngine(); engine.db = db
    rule = {'rule_id':'synthetic', 'category':'Onboarding', 'notification_recipients_json':['line_manager']}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(engine._send_notification_action(rule, {'employee_id':'staff'}, {'message':'An action is required.'}))
        run(engine._send_notification_action(rule, {}, {'message':'An action is required.'}))
    assert [call['to'] for call in calls(send)] == ['manager@example.com']
    assert all('recipient_id' in row for row in db.notifications.docs)


def test_routine_automation_checks_stay_in_portal_and_inactive_employee_not_emailed():
    db, _ = fixture(); engine = AutomationEngine(); engine.db = db
    db.employees.docs[4]['lifecycle_state']='Exited'
    rule = {'rule_id':'synthetic', 'category':'Onboarding', 'notification_recipients_json':['line_manager']}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(engine._send_notification_action(rule, {'employee_id':'staff'}, {'message':'An action is required.'}))
        run(engine._send_notification_action(rule, {'employee_id':'staff'}, {'check':'routine'}))
    assert send.await_count == 0


def test_mail_failure_does_not_raise_into_saved_business_workflow():
    db, _ = fixture()
    with patch.object(db.users, 'find', side_effect=RuntimeError('Synthetic lookup outage')):
        assert run(routing.leave_action(db, db.employees.docs[0], {'id':'leave','tenant_id':'solvit'}, 'submitted'))['status']=='failed'


def test_reminder_uses_saved_legacy_manager_and_filters_inactive_role_accounts():
    from reminders.engine import ReminderEngine
    db, _ = fixture(); engine = ReminderEngine(); engine.db = db
    db.employees.docs[0]['line_manager_id'] = str(db.employees.docs[4]['_id'])
    rule = {'template_key':'synthetic', 'recipients':['line_manager','hr_admin']}
    target = {'employee_id':str(db.employees.docs[0]['_id']), 'line_manager_id':'other'}
    with patch('utils.email_triggers.trigger', new=AsyncMock(return_value={'status':'sent'})) as send:
        assert run(engine._fire(rule, target)) is True
    assert {call.kwargs['to_override'] for call in send.await_args_list} == {'manager@example.com','hr@example.com'}


def test_reminder_does_not_claim_success_for_blocked_email():
    from reminders.engine import ReminderEngine
    db, _ = fixture(); engine = ReminderEngine(); engine.db = db
    with patch('utils.email_triggers.trigger', new=AsyncMock(return_value={'status':'skipped'})):
        assert run(engine._fire({'template_key':'missing','recipients':['employee']}, {'employee_id':'staff'})) is False


def test_leave_employee_and_manager_messages_and_decisions_are_once_per_event():
    from utils.leave_workflow import email_existing
    db, _ = fixture(); row = {'id':'leave', 'tenant_id':'solvit', 'status':'Pending_Manager', 'line_manager_id':'manager', 'approval_history':[]}
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status':'sent'})) as send:
        run(email_existing(db, db.employees.docs[0], row, 'submitted'))
        run(email_existing(db, db.employees.docs[0], row, 'submitted'))
        assert {call['to'] for call in calls(send)} == {'staff@example.com','manager@example.com'}
        assert send.await_count == 2
        row.update(status='Approved', approval_history=[{'stage':'manager'},{'stage':'hr'}])
        run(email_existing(db, db.employees.docs[0], row, 'decision'))
        assert send.await_count == 3 and calls(send)[-1]['to'] == 'staff@example.com'
        assert calls(send)[-1]['subject'] == 'Your leave request was approved'


def test_linked_system_hr_account_can_receive_actions_but_not_exited_staff():
    db, _ = fixture(); db.users.docs[2]['account_type'] = 'system'
    assert run(routing.role_addresses(db, {'hr_admin'}, 'solvit')) == ['hr@example.com']
    db.employees.docs[2]['lifecycle_state'] = 'Exited'
    # The unlinked duplicate HR fixture account remains authorized; remove it to test the linked identity.
    db.users.docs = [row for row in db.users.docs if row.get('employee_id')]
    assert run(routing.role_addresses(db, {'hr_admin'}, 'solvit')) == []


def test_email_log_does_not_count_claim_as_a_second_delivery():
    from routes import email_delivery
    db, users = fixture(); db.email_send_log = Collection()
    run(db.email_log.insert_one({'tenant_id':'solvit','status':'sent','delivery_claim':True,'subject':'claim'}))
    run(db.email_log.insert_one({'tenant_id':'solvit','status':'sent','subject':'actual','to':'staff@example.com','sent_at':'2026-11-10'}))
    with patch.object(email_delivery,'get_db',return_value=db), patch.object(email_delivery,'get_current_user',new=AsyncMock(return_value={**users['hr'],'role':'it_admin'})):
        result = run(email_delivery.get_email_log(None))
    assert len(result) == 1


def test_two_retry_workers_do_not_send_the_same_pending_attempt():
    from utils import email_service
    db, _ = fixture(); db.email_retry_queue = Collection()
    run(db.email_retry_queue.insert_one({'tenant_id':'solvit','status':'pending','next_attempt_at':'2000-01-01',
        'to':'staff@example.com','subject':'Action','html':'Please review.','retry_count':1}))
    async def exercise():
        return await asyncio.gather(email_service.process_retry_queue(db), email_service.process_retry_queue(db))
    with patch.object(email_service,'send_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        results = run(exercise())
    assert send.await_count == 1 and sum(results) == 1
    assert db.email_retry_queue.docs[0]['status'] == 'sent'


def test_old_role_broadcast_retry_is_held_for_recipient_review():
    from utils import email_service
    db, _ = fixture(); db.email_retry_queue = Collection()
    run(db.email_retry_queue.insert_one({'tenant_id':'solvit','status':'pending','next_attempt_at':'2000-01-01',
        'to':'other-manager@example.com','subject':'Legacy action','html':'<p>Private legacy message</p><small>Sent by Solvit People Platform automation</small>','retry_count':1}))
    with patch.object(email_service,'send_email',new=AsyncMock()) as send:
        assert run(email_service.process_retry_queue(db)) == 1
    assert send.await_count == 0
    assert db.email_retry_queue.docs[0]['status'] == 'blocked'
    assert db.email_log.docs[-1]['status'] == 'skipped'
