from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process, performance_v3_reviews as reviews, performance_v3_admin as admin
from utils import performance_v3_reminders as reminders, performance_v3_scoring as scoring
from utils.notification_centre import related_link
from .test_profile_self_service import run
from .test_performance_v3_end_to_end import configured, ready_for_hr


def test_peer_notification_deep_link_is_assigned_reviewer_only():
    db, users, cycle, row = configured()
    notification = next(n for n in db.notifications.docs if n.get('data', {}).get('performance_peer_task_id') and n.get('recipient_id') == 'other')
    link, _ = run(related_link(db, users['other'], notification, 'Performance'))
    assert link.startswith('/performance?peer=')
    assert run(related_link(db, users['staff'], notification, 'Performance'))[0] is None


def test_alignment_notification_has_actual_authorized_task_link():
    db, users, cycle, row = configured()
    notification = next(n for n in db.notifications.docs if n.get('data', {}).get('performance_alignment_cycle_id'))
    link, _ = run(related_link(db, users['staff'], notification, 'Performance'))
    assert link == '/performance?alignment=' + cycle['id']
    assert run(related_link(db, users['other'], notification, 'Performance'))[0] is None


def test_manager_and_hr_cannot_bypass_peer_minimum_or_collection_deadline():
    db, users, cycle, row = ready_for_hr()
    for actor in ('staff', 'other', 'manager', 'finance'):
        with pytest.raises(HTTPException): run(reviews.compile_review(db, users[actor], row['id'], {'expected_version': row['version'], 'summary': 'Not an HR approval'}))
    with patch.object(process, 'today', return_value=date(2026, 12, 6)):
        with pytest.raises(HTTPException): run(reviews.compile_review(db, users['hr'], row['id'], {'expected_version': row['version'], 'summary': 'Too early'}))
    db.performance_peer_responses.docs.pop()
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        with pytest.raises(HTTPException): run(reviews.compile_review(db, users['hr'], row['id'], {'expected_version': row['version'], 'summary': 'Too few responses'}))


def test_hr_actual_correction_is_audited_and_requires_recompilation():
    db, users, cycle, row = ready_for_hr()
    actuals = {g['id']: 1.5 for g in row['section_a_kpis']}
    run(reviews.correct_actuals(db, users['hr'], row['id'], {'expected_version': row['version'], 'actuals': actuals, 'reason': 'Verified corrected performance report'}))
    saved = db.performance_reviews.docs[0]
    assert saved['status'] == 'Manager_Submitted' and saved['overall_score'] is None
    assert len(saved['actual_corrections']) == 1
    assert saved['actual_corrections'][0]['before']['actuals'] != saved['manager_assessment']['actuals']
    assert any(a['event'] == 'performance.v3.actuals.corrected' for a in db.audit_logs.docs)


def test_release_and_meeting_actions_cannot_be_forged_by_employee():
    db, users, cycle, row = ready_for_hr()
    for action in ('schedule', 'complete', 'propose'):
        with pytest.raises(HTTPException): run(reviews.meeting(db, users['staff'], row['id'], {'expected_version': row['version']}, action))
    with pytest.raises(HTTPException): run(reviews.release(db, users['staff'], row['id'], {'expected_version': row['version']}))
    assert db.performance_reviews.docs[0]['status'] == 'Manager_Submitted'


def test_automatic_jobs_and_delivery_stay_disabled_in_staging(monkeypatch):
    monkeypatch.setenv('ENABLE_BACKGROUND_JOBS', 'false'); monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'false')
    db = AsyncMock()
    run(reminders.daily(db)); run(reminders.deliver(db, 'solvit'))
    assert not db.mock_calls


@pytest.mark.parametrize('score,gate,hold,expected', [(1,80,False,1.15),(1.5,80,False,1.05),(2,80,False,1),(2.25,80,False,.5),(2.5,100,False,0),(1,79,False,0),(1,100,True,0)])
def test_bonus_handoff_interpolation_is_gated_and_does_not_make_payments(score, gate, hold, expected):
    assert scoring.bonus_multiplier(score, gate, hold) == expected


def test_peer_deadline_cannot_be_extended_after_results_are_compiled():
    db, users, cycle, row = ready_for_hr()
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        run(reviews.compile_review(db, users['hr'], row['id'], {'expected_version': row['version'], 'summary': 'Verified by HR'}))
        with pytest.raises(HTTPException): run(admin.peers(db, users['hr'], row['id'], {'extend_days': 3, 'reason': 'Cannot reopen published aggregates'}))


def test_dispute_to_hr_is_not_exposed_to_line_manager():
    db, users, cycle, row = configured()
    row['dispute'] = {'statement': 'Confidential written HR dispute', 'status': 'Pending_HR'}
    assert 'dispute' not in process.projection(row, users['manager'], db.employees.docs[0])
    assert 'dispute' in process.projection(row, users['staff'], db.employees.docs[0])
    assert 'dispute' in process.projection(row, users['hr'], db.employees.docs[0])


def test_daily_reminders_are_idempotent_and_keep_existing_delivery_controls(monkeypatch):
    db, users, cycle, row = configured()
    monkeypatch.setenv('ENABLE_BACKGROUND_JOBS', 'true')
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'false')
    with patch.object(process, 'today', return_value=date(2026, 12, 3)):
        run(reminders.daily(db)); count = len(db.notifications.docs)
        run(reminders.daily(db))
    assert len(db.notifications.docs) == count
    assert any(n['title'] == 'Complete your self-assessment' for n in db.notifications.docs)
    assert all(not n['v3_email_pending'] for n in db.notifications.docs)


def test_email_delivery_targets_saved_manager_and_never_another_employee(monkeypatch):
    db, users, cycle, row = configured()
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'true')
    run(process.notice(db, row, 'synthetic-manager-action', 'employee', 'manager', 'Review submitted assessment'))
    send = AsyncMock(return_value={'status': 'sent'})
    with patch('utils.email_routing.action_email', send): run(reminders.deliver(db, 'solvit'))
    assert send.await_count == 1
    assert send.await_args.args[3] == 'manager@example.com'
    assert '?review=' + row['id'] in send.await_args.args[6]


def test_legacy_review_distribution_cannot_mutate_a_v3_cycle():
    from utils.performance_workflows import launch_cycle
    db, users, cycle, row = configured(); before = len(db.performance_reviews.docs)
    with pytest.raises(HTTPException): run(launch_cycle(db, users['hr'], cycle['id']))
    assert len(db.performance_reviews.docs) == before


def test_opening_cycle_rejects_an_existing_circular_reporting_chain():
    db, users, cycle, row = configured()
    manager = next(e for e in db.employees.docs if e['id'] == 'manager')
    manager['line_manager_id'] = 'staff'
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        with pytest.raises(HTTPException): run(process.open_cycle(db, users['hr'], cycle['id'], ['staff']))
    assert len(db.performance_reviews.docs) == 1


def test_board_only_record_is_not_a_v3_subject_or_staff_peer():
    assert not process.fte({'employment_type': 'Full_Time', 'board_only': True})
    assert not process.fte({'employment_type': 'Full_Time', 'board_only': 'true'})
    assert process.fte({'employment_type': 'Full_Time', 'board_only': False})


def test_partial_cycle_is_not_published_as_company_talent_density():
    from utils import performance_v3_alignment as alignment
    db, users, cycle, row = configured()
    row.update(released_at='2026-12-07T12:00:00Z', released_by='hr', section_b_score=1, nine_box_placement='Stars')
    for _ in range(3):
        run(db.survey_responses.insert_one({'tenant_id': 'solvit', 'cycle_id': cycle['id'], 'performance_workflow_version': 3,
            'overall_alignment_score': 100, 'line_manager_id': 'manager'}))
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        result = run(alignment.report(db, users['hr'], cycle['id']))
    assert result['score'] == 100 and 'talent_density' not in result
