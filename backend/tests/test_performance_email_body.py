from unittest.mock import AsyncMock, patch
import pytest
from utils import performance_email_body as copy, performance_v3 as process, performance_v3_reminders as reminders
from utils import notification_email
from utils.email_routing import action_email
from .test_performance_v3_end_to_end import configured
from .test_profile_self_service import run
from .integrity_fakes import Collection


def fixture(event='opened', title='Complete your performance self-review', recipient='staff'):
    db, users, cycle, review = configured()
    review.update(self_assessment={'secret':'private-answer'}, peer_summary={'secret':'private-peer-scores'},
                  manager_assessment={'comment':'private-manager-comment'}, ack_due_on='2026-12-30')
    notice={'_id':process.key('synthetic-email',event), 'tenant_id':'solvit', 'recipient_id':recipient,
            'title':title, 'data':{'performance_v3':True, 'performance_review_id':review['id'],
                'employee_id':'staff', 'cycle_id':cycle['id'], 'performance_event':event}, 'v3_email_pending':True}
    return db,review,notice


@pytest.mark.parametrize('event,title,recipient,expected,when',[
    ('opened','Complete your performance self-review','staff','your own Year-end 2026','06 December 2026'),
    ('manager-week2','Your team performance cycle is open','manager','as their line manager','13 December 2026'),
    ('self-submitted','Review your employee’s submitted assessment','manager','employee has submitted','13 December 2026'),
    ('manager-submitted','Performance assessment ready for HR review',None,'complete the HR checks','27 December 2026'),
    ('released','Your performance review is released; please acknowledge it','staff','acknowledge','30 December 2026'),
    ('peer-shortfall:2026-12-07','Week 1 peer review shortfall',None,'fewer than three','06 December 2026'),
    ('dispute','Employee submitted a written performance review dispute',None,'record HR’s response',None),
    ('actual-correction:v2','HR corrected assessment actuals','manager','updated assessment','13 December 2026'),
    ('outcomes','Track the released review follow-up actions',None,'record progress',None),
])
def test_role_specific_actions_have_context_and_no_private_answers(event,title,recipient,expected,when):
    db,review,notice=fixture(event,title,recipient)
    message=run(copy.body(db,notice,recipient))
    assert expected.lower() in message.lower()
    if when: assert when in message
    if recipient!='staff': assert db.employees.docs[0]['full_name'] in message
    assert all(secret not in message for secret in ('private-answer','private-peer-scores','private-manager-comment'))


def test_opening_manager_notice_is_specific_even_for_already_queued_old_event():
    db,review,notice=fixture('manager-week2','Your team performance cycle is open','manager')
    notice['data'].pop('performance_event')
    message=run(copy.body(db,notice,'manager'))
    assert db.employees.docs[0]['full_name'] in message
    assert 'They should complete their self-review first' in message
    assert 'as their line manager' in message and 'your own Year-end' not in message


def test_peer_request_names_subject_and_deadline_but_never_exposes_other_reviewers():
    db,review,notice=fixture('peer-assigned:task','Complete an anonymous 360 review','other')
    notice['data'].pop('performance_review_id')
    notice['data']['performance_peer_task_id']='task'
    db.performance_peer_tasks.docs=[{'id':'task','tenant_id':'solvit','review_id':review['id'],'due_on':'2026-12-09'}]
    message=run(copy.body(db,notice,'other'))
    assert db.employees.docs[0]['full_name'] in message
    assert 'not your own self-review' in message and '09 December 2026' in message
    assert 'private-peer-scores' not in message


def test_alignment_is_own_survey_not_a_review_of_another_employee():
    db,review,notice=fixture('alignment:staff','Complete the Alignment Survey')
    notice['data'].pop('performance_review_id')
    notice['data']['performance_alignment_cycle_id']=review['cycle_id']
    message=run(copy.body(db,notice,'staff'))
    assert 'your own survey' in message and '12 questions' in message and '06 December 2026' in message
    assert 'manager scores' not in message


def test_meeting_proposal_is_not_presented_as_a_booking_and_times_use_nairobi():
    db,review,notice=fixture('meeting-proposed:date','Manager proposed a review meeting; arrange it manually',None)
    review['meeting_proposal']={'scheduled_at':'2026-12-15T10:30:00+00:00','location':'Meeting room'}
    message=run(copy.body(db,notice))
    assert 'not a confirmed booking' in message and '13:30 EAT' in message and 'Meeting room' in message


def test_html_is_escaped_and_paragraphs_are_readable_without_sending_mail(monkeypatch):
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','true')
    db,review,notice=fixture()
    db.email_log=Collection()
    db.employees.docs[0]['full_name']='<script>alert(1)</script>'
    message=run(copy.body(db,notice,'staff'))
    with patch('utils.email_service.send_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        run(action_email(db,'solvit','synthetic-copy','staff@example.com','Unchanged subject',message,'https://example.com/review'))
    html=send.await_args.kwargs['html']
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert html.count('<p>')>=5 and send.await_args.kwargs['subject']=='Unchanged subject'


def test_v3_delivery_uses_specific_body_without_changing_subject_or_recipient(monkeypatch):
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED','true')
    db,review,notice=fixture('manager-week2','Your team performance cycle is open','manager')
    db.notifications.docs=[notice]
    with patch('utils.email_routing.action_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        run(reminders.deliver(db,'solvit'))
    args=send.await_args.args
    assert args[3]=='manager@example.com' and args[4]=='Your team performance cycle is open'
    assert db.employees.docs[0]['full_name'] in args[5] and '13 December 2026' in args[5]
    assert '?review='+review['id'] in args[6]


def test_authorized_inbox_sender_uses_same_copy_if_it_delivers_first():
    db,review,notice=fixture('manager-week2','Your team performance cycle is open','manager')
    account={'_id':'manager-account','employee_id':'manager','email':'manager@example.com','is_active':True}
    with patch.object(notification_email,'candidate_accounts',new=AsyncMock(return_value=[account])), \
         patch.object(notification_email,'list_inbox',new=AsyncMock(return_value={'items':[{'title':notice['title'],'message':'Authorized summary'}]})), \
         patch.object(notification_email,'action_email',new=AsyncMock(return_value={'status':'sent'})) as send:
        assert run(notification_email.deliver_item(db,notice))
    assert db.employees.docs[0]['full_name'] in send.await_args.args[5]
    assert 'as their line manager' in send.await_args.args[5]
    assert send.await_args.args[4]==notice['title']
