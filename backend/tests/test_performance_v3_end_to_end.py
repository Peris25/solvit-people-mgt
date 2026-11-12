from copy import deepcopy
from datetime import date, datetime, timezone
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process, performance_v3_reviews as reviews
from utils import performance_v3_admin as admin, performance_v3_peers as peers, performance_v3_alignment as alignment
from .integrity_fakes import Collection
from .test_profile_self_service import fixture, run
from .test_role_kpi_library import approved, save


class MongoCollection(Collection):
    async def update_one(self, query, update, upsert=False):
        if upsert and not await self.find_one(query):
            await self.insert_one({**query, **deepcopy(update.get('$setOnInsert', {}))})
        return await super().update_one(query, update, upsert=False)


def configured():
    db, users = fixture()
    for name in ('performance_cycles', 'performance_peer_tasks', 'performance_peer_responses', 'survey_windows', 'survey_responses', 'public_holidays', 'leave_policy_profiles'):
        setattr(db, name, MongoCollection())
    db.notifications = MongoCollection()
    staff = db.employees.docs[0]; staff['role_title'] = 'IT Support'
    manager = next(e for e in db.employees.docs if e['id'] == 'manager'); manager['role_title'] = 'Managing Director'
    entry = approved(db, users['hr']); entry['scope'] = 'Annual'
    save(db, users['hr'], entry, action='publish')
    assigned = run(process.assignment(db, staff))
    run(process.assign(db, users['hr'], 'staff', {'role_id': 'it-support', 'expected_version': assigned['version'] if assigned else None, 'reason': 'Approved synthetic role mapping'}))
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        cycle = run(process.create_cycle(db, users['hr'], {'cycle_type': 'Year_End', 'cycle_year': 2026, 'starts_on': '2026-11-30', 'approval_reference': 'Synthetic approval reference', 'alignment_confirmed': True}))
        run(process.open_cycle(db, users['hr'], cycle['id'], ['staff']))
    return db, users, cycle, db.performance_reviews.docs[0]


def assessment(row):
    return {'actuals': {g['id']: {'actual': 1 if g['direction'] == 'Rated' else True if g['direction'] == 'Binary' else g['target_value'], 'self_score': 1, 'evidence': 'Synthetic verified report'} for g in row['section_a_kpis']},
            'values': [{'score': 8, 'example': 'Synthetic evidence'} for _ in range(5)],
            'accomplishments': ['One', 'Two', 'Three'], 'challenge': 'Challenge', 'do_differently': 'Improvement', 'support': 'Support'}


def ready_for_hr():
    db, users, cycle, row = configured()
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        run(reviews.self_assessment(db, users['staff'], row['id'], {'expected_version': row['version'], 'assessment': assessment(row), 'submit': True}))
        for actor in ('other', 'hr', 'finance'):
            task = next(t for t in db.performance_peer_tasks.docs if t['reviewer_employee_id'] == actor)
            run(peers.submit(db, users[actor], task['id'], {'scores': [8] * 5, 'retain': 10, 'relationship': 'Peer', 'comment': 'Anonymous example'}))
    row = db.performance_reviews.docs[0]
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        run(reviews.manager_assessment(db, users['manager'], row['id'], {'expected_version': row['version'], 'actuals': {k: {'actual': v['actual']} for k, v in row['self_assessment']['actuals'].items()}, 'summary': 'Verified manager review'}))
        run(admin.company_feedback(db, users['hr'], cycle['id'], {'nps': 50, 'csat': 4.7, 'source_reference': 'Synthetic verified company survey'}))
    return db, users, cycle, db.performance_reviews.docs[0]


def test_complete_cycle_self_peer_manager_hr_meeting_release_and_acknowledgement():
    db, users, cycle, row = ready_for_hr()
    with patch.object(process, 'today', return_value=date(2026, 12, 7)), patch.object(process, 'instant', return_value=datetime(2026, 12, 7, tzinfo=timezone.utc)):
        run(reviews.compile_review(db, users['hr'], row['id'], {'expected_version': row['version'], 'summary': 'HR evidence verified'}))
        row = db.performance_reviews.docs[0]
        run(reviews.meeting(db, users['manager'], row['id'], {'expected_version': row['version'], 'scheduled_at': '2026-12-14T10:00:00+03:00', 'location': 'Office'}, 'propose'))
        row = db.performance_reviews.docs[0]
        run(reviews.meeting(db, users['hr'], row['id'], {'expected_version': row['version'], 'scheduled_at': '2026-12-14T10:00:00+03:00', 'location': 'Office'}, 'schedule'))
        row = db.performance_reviews.docs[0]
        with pytest.raises(HTTPException): run(reviews.release(db, users['hr'], row['id'], {'expected_version': row['version']}))
    with patch.object(process, 'today', return_value=date(2026, 12, 14)), patch.object(process, 'instant', return_value=datetime(2026, 12, 14, 12, tzinfo=timezone.utc)), patch.object(process.flow, 'now', return_value='2026-12-14T12:00:00+00:00'):
        run(reviews.meeting(db, users['hr'], row['id'], {'expected_version': row['version'], 'notes': 'Meeting completed'}, 'complete'))
        row = db.performance_reviews.docs[0]
        run(reviews.release(db, users['hr'], row['id'], {'expected_version': row['version']}))
        row = db.performance_reviews.docs[0]
        assert row['status'] == 'Completed' and row['overall_score'] == 1.3
        assert row['compensation_handoff']['status'] == 'Pending_Finance_Review'
        assert row['ack_due_on'] > '2026-12-14'
        visible = process.projection(row, users['staff'], db.employees.docs[0])
        assert visible['scores_released'] and 'retention_average' not in visible['peer_summary']
        run(reviews.acknowledge(db, users['staff'], row['id'], {'expected_version': row['version'], 'confirmed': True}))
        row = db.performance_reviews.docs[0]
        run(reviews.acknowledge(db, users['staff'], row['id'], {'expected_version': row['version'], 'dispute': 'Written disagreement for HR review'}))
    assert db.performance_reviews.docs[0]['dispute']['status'] == 'Pending_HR'
    assert any(n.get('title') == 'Your performance review is released; please acknowledge it' for n in db.notifications.docs)
    assert all(not n['v3_email_pending'] for n in db.notifications.docs)


def test_cycle_open_is_idempotent_locks_kpis_and_does_not_rewrite_employee_records():
    db, users, cycle, row = configured(); original = deepcopy(db.employees.docs)
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        run(process.open_cycle(db, users['hr'], cycle['id'], ['staff']))
    assert len(db.performance_reviews.docs) == 1
    assert len({t['id'] for t in db.performance_peer_tasks.docs}) == len(db.performance_peer_tasks.docs)
    with pytest.raises(HTTPException): run(process.assign(db, users['hr'], 'staff', {'role_id': 'it-support', 'expected_version': run(process.assignment(db, db.employees.docs[0]))['version'], 'reason': 'A proposed change after cycle open'}))
    assert db.employees.docs == original


def test_peer_extension_is_limited_and_closed_aggregates_cannot_be_reopened():
    db, users, cycle, row = configured()
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        result = run(admin.peers(db, users['hr'], row['id'], {'extend_days': 3, 'reason': 'Need three submitted peer assessments'}))
        assert result['peer_due_on'] == '2026-12-09'
        with pytest.raises(HTTPException): run(admin.peers(db, users['hr'], row['id'], {'extend_days': 4, 'reason': 'Invalid extra extension'}))
    assert all(t['due_on'] == '2026-12-09' for t in db.performance_peer_tasks.docs)


def test_alignment_reuses_surveys_is_anonymous_and_needs_three_responses():
    db, users, cycle, row = configured()
    from routes.surveys import FTE_ALIGNMENT_QUESTIONS
    answers = {q['id']: 4 for q in FTE_ALIGNMENT_QUESTIONS}
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        assert run(alignment.submit(db, users['staff'], cycle['id'], answers))['status'] == 'Submitted'
        with pytest.raises(HTTPException): run(alignment.submit(db, users['other'], cycle['id'], answers))
        with pytest.raises(HTTPException): run(alignment.submit(db, users['staff'], cycle['id'], answers))
    stored = db.survey_responses.docs[0]
    assert not {'respondent_id', 'subject_id', 'employee_id', 'submitted_at'} & set(stored)
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        assert run(alignment.report(db, users['hr'], cycle['id']))['score'] is None


@pytest.mark.parametrize('actor', ['staff', 'other', 'manager', 'finance'])
def test_non_hr_cannot_prepare_cycles_or_read_hr_tracker(actor):
    db, users = fixture()
    with pytest.raises(HTTPException): run(admin.dashboard(db, users[actor]))
    with pytest.raises(HTTPException): run(process.create_cycle(db, users[actor], {}))
