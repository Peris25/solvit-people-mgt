from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import email_service as service
from utils.email_content import content_error
from .test_runtime_controls import database, run


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'true')
    monkeypatch.setattr(service, '_MIN_INTERVAL_S', 0)


@pytest.mark.parametrize('subject,body', [('', '<p>Leave submitted</p>'), ('  ', 'Hello'),
    ('Leave', ''), ('Leave', '<p>&nbsp; &#8203;</p>'), ('Leave', '<!-- empty --><br>'),
    ('Leave', '<style>body {color:red}</style>'), ('Leave', '<img alt="message" src="image">'),
    ('Leave', '<p>(no body)</p>'), ('Leave', '<p>{{missing}}</p>'), ('Bad\nSubject', 'Hello'),
    ('Leave', service._wrap_solvit_brand('<p>(no body)</p>')),
    ('Leave', service._wrap_solvit_brand('<p> </p>').replace('<!--solvit-body-start-->', '').replace('<!--solvit-body-end-->', ''))])
@pytest.mark.parametrize('provider', ['smtp', 'sender_net'])
def test_invalid_email_never_reaches_transport_or_retry(subject, body, provider):
    db = database(); db.email_delivery_config.docs[0]['testing'].update(provider=provider, api_key='synthetic-key')
    with patch.object(service, '_attempt_send', new=AsyncMock()) as smtp, patch.object(service, '_attempt_send_sender_net', new=AsyncMock()) as sender:
        result = run(service.send_email(db, 'staff@example.com', subject=subject, html=body))
    assert result['reason'] == 'invalid_email_content'
    assert smtp.await_count == sender.await_count == 0
    assert not db.email_retry_queue.docs and db.email_log.docs[-1]['status'] == 'skipped'


def test_missing_template_is_not_sent_with_generic_fallback():
    db = database()
    with patch.object(service, '_attempt_send', new=AsyncMock()) as send:
        result = run(service.send_email(db, 'staff@example.com', template_key='missing.template'))
    assert result['reason'] == 'missing_email_template' and send.await_count == 0
    assert not db.email_retry_queue.docs


@pytest.mark.parametrize('provider', ['smtp', 'sender_net'])
def test_valid_template_renders_and_still_sends(provider):
    db = database(); db.email_delivery_config.docs[0]['testing'].update(provider=provider, api_key='synthetic-key')
    run(db.email_templates.insert_one({'tenant_id': 'solvit', 'key': 'leave.synthetic', 'subject': 'Leave for {{employee_name}}', 'body': '<p>Your leave request was submitted, {{employee_name}}.</p>'}))
    with patch.object(service, '_attempt_send', new=AsyncMock()) as smtp, patch.object(service, '_attempt_send_sender_net', new=AsyncMock()) as sender:
        result = run(service.send_email(db, 'staff@example.com', template_key='leave.synthetic', context={'employee_name': 'Synthetic Staff'}))
    assert result['status'] == 'sent' and smtp.await_count + sender.await_count == 1
    assert db.email_log.docs[-1]['subject'] == 'Leave for Synthetic Staff'


def test_empty_after_merge_is_blocked_and_plain_text_remains_supported():
    db = database()
    run(db.email_templates.insert_one({'tenant_id': 'solvit', 'key': 'empty.merge', 'subject': 'Review', 'body': '<p>{{missing}}</p>'}))
    with patch.object(service, '_attempt_send', new=AsyncMock()) as send:
        assert run(service.send_email(db, 'staff@example.com', template_key='empty.merge'))['reason'] == 'invalid_email_content'
        assert run(service.send_email(db, 'staff@example.com', subject='Reminder', text='Your review is due.'))['status'] == 'sent'
    assert send.await_count == 1


def test_legacy_empty_retry_is_blocked_without_requeue():
    db = database()
    run(db.email_retry_queue.insert_one({'tenant_id': 'solvit', 'to': 'staff@example.com', 'subject': 'Solvit People Platform', 'html': service._wrap_solvit_brand('<p>(no body)</p>'), 'status': 'pending', 'retry_count': 1, 'next_attempt_at': '2000-01-01'}))
    with patch.object(service, '_attempt_send', new=AsyncMock()) as send:
        assert run(service.process_retry_queue(db)) == 1
    assert send.await_count == 0 and len(db.email_retry_queue.docs) == 1
    assert db.email_retry_queue.docs[0]['status'] == 'blocked'


def test_branding_cannot_make_an_empty_body_valid():
    assert content_error('Subject', service._wrap_solvit_brand(''))
    assert content_error('Subject', service._wrap_solvit_brand('<p>Your leave request is ready for review.</p>')) is None


def test_template_editor_rejects_blank_template_before_saving():
    from routes import email_templates
    request = SimpleNamespace(json=AsyncMock(return_value={'subject': 'Leave', 'body': '<p>&nbsp;</p>'}))
    with patch.object(email_templates, 'get_current_user', new=AsyncMock(return_value={'role': 'it_admin', 'id': 'synthetic'})), patch.object(email_templates, 'get_db', return_value=database()):
        with pytest.raises(HTTPException) as error: run(email_templates.update_template('synthetic', request))
    assert error.value.status_code == 422
