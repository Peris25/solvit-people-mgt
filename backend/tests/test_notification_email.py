import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from utils import notification_email as delivery
from utils.email_routing import action_email
from .test_notification_centre import fixture, notice
from .integrity_fakes import Collection, account


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'true')
    monkeypatch.setenv('ENABLE_BACKGROUND_JOBS', 'true')


def setup():
    db, actors = fixture()
    db.email_log = Collection()
    db.system_settings.docs = [{'_id': delivery.ROLLOUT_ID, 'enabled_at': '2026-10-01T00:00:00+00:00'}]
    row = notice(category='System', recipient_id='staff', recipient_type='employee')
    db.notifications.docs = [row]
    return db, actors, row


def test_only_authorized_active_recipient_gets_safe_summary_without_opening_portal():
    db, _, row = setup()
    db.users.docs.extend([account('foreign@example.com', tenant_id='foreign', employee_id='staff'),
                          account('inactive@example.com', is_active=False, employee_id='other')])
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(delivery.deliver(db))
        run(delivery.deliver(db))
    assert send.await_count == 1
    mail = send.await_args.kwargs
    assert mail['to'] == 'staff@example.com'
    assert row['message'] not in mail['html']
    assert row['title'] not in mail['subject']
    assert '/notifications' in mail['html']
    assert db.notifications.docs[0]['email_delivery_checked'] is True


@pytest.mark.parametrize('flag', ['OUTBOUND_EMAIL_ENABLED', 'ENABLE_BACKGROUND_JOBS'])
def test_deployment_switches_leave_items_pending(monkeypatch, flag):
    db, _, _ = setup()
    monkeypatch.setenv(flag, 'false')
    with patch('utils.email_service.send_email', new=AsyncMock()) as send:
        run(delivery.deliver(db))
    send.assert_not_awaited()
    assert not db.notifications.docs[0].get('email_delivery_checked')
    assert not db.email_log.docs


def test_unconfigured_email_stays_pending_and_retries_after_configuration():
    db, _, _ = setup()
    with patch('utils.email_service.send_email', new=AsyncMock(side_effect=[
        {'status': 'skipped', 'message': 'email delivery not configured'}, {'status': 'sent'}])) as send:
        run(delivery.deliver(db))
        assert not db.notifications.docs[0].get('email_delivery_checked')
        assert not db.email_log.docs
        run(delivery.deliver(db))
    assert send.await_count == 2
    assert db.notifications.docs[0]['email_delivery_checked'] is True


def test_concurrent_workers_claim_one_message():
    db, _, _ = setup()
    async def workers():
        await asyncio.gather(delivery.deliver(db), delivery.deliver(db))
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(workers())
    assert send.await_count == 1


def test_existing_event_claim_prevents_second_workflow_email():
    db, _, row = setup()
    row['email_event_key'] = 'leave:request:submitted:0:employee'
    db.notifications.docs = [row]
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(action_email(db, 'solvit', row['email_event_key'], 'staff@example.com', 'Leave submitted',
                         'Open the request.', 'https://people.solvit.co.ke/leave'))
        run(delivery.deliver(db))
    assert send.await_count == 1


def test_previously_skipped_native_email_claim_is_retried():
    db, _, row = setup()
    row['email_event_key'] = 'existing-skipped-event'
    db.notifications.docs = [row]
    with patch('utils.email_service.send_email', new=AsyncMock(side_effect=[{'status': 'skipped'}, {'status': 'sent'}])) as send:
        run(action_email(db, 'solvit', row['email_event_key'], 'staff@example.com', 'Update',
                         'Open the request.', 'https://people.solvit.co.ke/notifications'))
        run(delivery.deliver(db))
    assert send.await_count == 2
    assert db.notifications.docs[0]['email_delivery_checked'] is True


def test_claim_outage_does_not_discard_pending_notification():
    db, _, _ = setup()
    with patch.object(db.email_log, 'insert_one', new=AsyncMock(side_effect=RuntimeError('Synthetic outage'))):
        run(delivery.deliver(db))
    assert not db.notifications.docs[0].get('email_delivery_checked')


def test_rollout_boundary_survives_restart_and_does_not_replay_history():
    db, _, row = setup()
    db.system_settings.docs = []
    first = run(delivery.initialize(db))
    assert run(delivery.initialize(db)) == first
    assert first <= datetime.now(timezone.utc)
    with patch('utils.email_service.send_email', new=AsyncMock()) as send:
        run(delivery.deliver(db))
    send.assert_not_awaited()


def test_failed_email_alerts_do_not_create_an_email_feedback_loop():
    db, _, row = setup()
    row.update(category='Email', recipient_role='it_admin')
    db.notifications.docs = [row]
    with patch('utils.email_service.send_email', new=AsyncMock()) as send:
        run(delivery.deliver(db))
    send.assert_not_awaited()


def test_role_notifications_use_each_accounts_inbox_access():
    db, _, row = setup()
    row.pop('recipient_id'); row.pop('recipient_type')
    row['recipient_role'] = 'employee'
    db.notifications.docs = [row]
    with patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(delivery.deliver(db))
    assert {call.kwargs['to'] for call in send.await_args_list} == {'staff@example.com', 'other@example.com'}


def test_inactive_linked_employee_is_not_emailed():
    db, _, _ = setup()
    db.employees.docs[0]['lifecycle_state'] = 'Exited'
    with patch('utils.email_service.send_email', new=AsyncMock()) as send:
        run(delivery.deliver(db))
    send.assert_not_awaited()


def test_v3_and_legacy_performance_use_existing_workflow_keys():
    assert delivery.event_key({'_id': 'abc', 'data': {'performance_v3': True}}) == 'performance-v3:abc'
    row = {'_id': 'performance:solvit:review:created:employee:staff', 'tenant_id': 'solvit',
           'data': {'performance_review_id': 'review', 'performance_event': 'created'}}
    assert delivery.event_key(row) == 'performance:review:created'


def test_targeted_notice_does_not_project_every_unrelated_account():
    db, actors, row = setup()
    with patch.object(delivery, 'list_inbox', wraps=delivery.list_inbox) as inbox, patch('utils.email_service.send_email', new=AsyncMock(return_value={'status': 'sent'})) as send:
        run(delivery.deliver(db))
    assert inbox.await_count == 1
    assert send.await_count == 1
    assert inbox.await_args.args[1]['id'] == actors['staff']['id']


def test_candidate_lookup_preserves_legacy_storage_alias_and_email_link():
    db, actors, row = setup()
    row['recipient_id'] = str(db.employees.docs[0]['_id'])
    db.users.docs[0].pop('employee_id')
    result = run(delivery.candidate_accounts(db, row))
    assert [str(account['_id']) for account in result] == [actors['staff']['id']]


def test_account_target_is_not_expanded_to_staff_role_peers():
    db, actors, row = setup()
    row.update(recipient_type='account', recipient_id=actors['staff']['id'])
    assert [str(account['_id']) for account in run(delivery.candidate_accounts(db, row))] == [actors['staff']['id']]
