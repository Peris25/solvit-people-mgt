from unittest.mock import AsyncMock,patch
from utils import performance_workflows as flow, notification_email as inbox
from .test_probation_manager_led import setup,payload,act,completed_meeting
from .test_performance_workflows import run
from .integrity_fakes import Collection


def deliver_event(db,event):
    for notice in db.notifications.docs:
        if notice.get('data',{}).get('performance_event')==event:
            run(inbox.deliver_item(db,notice))


def test_opening_emails_manager_action_and_employee_information_with_direct_review_button(monkeypatch):
    db,users,ref=setup();db.email_log=Collection();monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','true')
    with patch('utils.email_service.send_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        run(flow.notify(db,db.performance_reviews.docs[0],'created'))
        deliver_event(db,'created')
    messages={call.kwargs['to']:call.kwargs for call in send.await_args_list}
    assert set(messages)=={'staff@example.com','manager@example.com'}
    own=messages['staff@example.com']['html'];manager=messages['manager@example.com']['html']
    assert 'Your probation review has been sent to' in own
    assert db.employees.docs[4]['full_name'] in own
    assert 'Complete the employee' in manager and db.employees.docs[0]['full_name'] in manager
    for message in messages.values():
        assert '/performance?review='+ref in message['html']
        assert '>Open review</a>' in message['html'] and 'display:inline-block' in message['html']
        assert 'Month 3' in message['html']


def test_manager_submission_notifies_hr_and_employee_and_final_release_notifies_both(monkeypatch):
    db,users,ref=setup();db.email_log=Collection();monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','true')
    with patch('utils.email_service.send_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        run(flow.assess(db,users['manager'],ref,'manager',payload(db,ref)))
        deliver_event(db,'performance.assessment.manager')
        sent={call.kwargs['to']:call.kwargs['html'] for call in send.await_args_list}
        assert {'staff@example.com','hr@example.com'}<=set(sent)
        assert 'line manager has submitted' in sent['staff@example.com']
        assert 'Arrange the employee' in sent['hr@example.com']
        assert '/performance?review='+ref in sent['staff@example.com']
        completed_meeting(db,users,ref)
        act(db,users,ref,'hr','hr',{'summary':'Approved after discussion','outcome':'Confirm'})
        act(db,users,ref,'hr','release',{})
        send.reset_mock();deliver_event(db,'performance.assessment.release')
        released={call.kwargs['to']:call.kwargs['html'] for call in send.await_args_list}
        assert {'staff@example.com','hr@example.com'}<=set(released)
        assert 'acknowledge receipt' in released['staff@example.com']
        assert 'released to the employee' in released['hr@example.com']
        assert all('/performance?review='+ref in html for html in released.values())


def test_inbox_sender_resolves_manager_from_employee_when_it_delivers_first(monkeypatch):
    db,users,ref=setup();db.email_log=Collection();monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','true')
    assert not db.performance_reviews.docs[0].get('line_manager_id')
    with patch('utils.email_service.send_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        deliver_event(db,'created')
    messages={call.kwargs['to']:call.kwargs['html'] for call in send.await_args_list}
    assert 'Complete the employee' in messages['manager@example.com']
    assert 'as their line manager' in messages['manager@example.com']
    assert 'Your probation review has been sent to' in messages['staff@example.com']
    assert all('/performance?review='+ref in html for html in messages.values())
