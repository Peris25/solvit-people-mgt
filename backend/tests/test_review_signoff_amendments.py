from copy import deepcopy
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process, performance_v3_admin as admin, performance_v3_reviews as reviews
from utils.staff_views import build_staff_views
from utils.role_kpi_library import view
from .test_performance_v3_end_to_end import configured
from .test_profile_self_service import run


def test_november_23_cycle_deadlines_match_signoff_without_opening_cycle():
    db, users, _, _ = configured(); db.performance_cycles.docs = []
    with patch.object(process, 'today', return_value=date(2026, 11, 20)):
        result = run(process.create_cycle(db, users['hr'], {'cycle_type': 'Year_End', 'cycle_year': 2026, 'starts_on': '2026-11-23', 'approval_reference': 'HR sign-off amendments', 'alignment_confirmed': True}))
    assert [result[k] for k in ['self_due_on', 'peer_due_on', 'manager_due_on', 'ends_on']] == ['2026-11-29', '2026-11-29', '2026-12-06', '2026-12-20']
    assert result['status'] == 'Configured'


def test_release_acknowledgement_uses_two_working_days_and_skips_holidays():
    db, users, _, row = configured()
    row.update(status='HR_Reviewed', meeting_completed_at='2026-12-23T10:00:00+00:00', overall_score=1.5, nine_box_placement='Core_Contributor')
    async def save(db, user, row, update, event): return {**row, **update}
    db.public_holidays.docs = [{'date': '2026-12-25', 'tenant_id': 'solvit'}]
    with patch.object(process, 'record', AsyncMock(return_value=(row, db.employees.docs[0]))), patch.object(process, 'today', return_value=date(2026, 12, 23)), patch.object(process, 'instant', return_value=datetime(2026, 12, 23, 12, tzinfo=timezone.utc)), patch.object(process, 'save', side_effect=save), patch.object(process, 'notice', AsyncMock()), patch.object(process, 'hr_notice', AsyncMock()), patch('utils.leave_policy.contract_policy', AsyncMock(return_value={'saturday_weight': 0})):
        result = run(reviews.release(db, users['hr'], row['id'], {'expected_version': row['version']}))
    assert result['ack_due_on'] == '2026-12-28'


def test_hr_peer_progress_counts_received_chosen_and_submitted_without_pairings():
    db, users, cycle, review = configured()
    for i in range(5):
        db.performance_peer_tasks.docs.append({'cycle_id': cycle['id'], 'reviewer_employee_id': 'staff', 'status': 'Submitted' if i < 2 else 'Assigned', 'employee_id': 'private-colleague-'+str(i), 'tenant_id': 'solvit'})
    for i in range(2):
        db.performance_peer_responses.docs.append({'cycle_id': cycle['id'], 'review_id': review['id'], 'scores': [9]*5, 'comment': 'PRIVATE', 'tenant_id': 'solvit'})
    db.performance_peer_responses.docs.append({'cycle_id': cycle['id'], 'review_id': review['id'], 'tenant_id': 'foreign'})
    people = [{'id': 'staff', 'name': 'Synthetic staff'}, {'id': 'other', 'name': 'Synthetic other'}]
    result = run(admin.peer_progress(db, users['hr'], [cycle], people))
    row = next(r for r in result if r['employee_id'] == 'staff')
    assert (row['received'], row['chosen'], row['submitted']) == (2, 5, 2)
    assert row['below_received_minimum'] and not row['below_chosen_minimum'] and row['below_submitted_minimum']
    assert set(row) == {'employee_id','employee_name','cycle_id','received','chosen','submitted','below_received_minimum','below_chosen_minimum','below_submitted_minimum'}
    assert 'PRIVATE' not in str(result) and 'private-colleague' not in str(result)
    assert next(r for r in result if r['employee_id']=='other')['chosen'] == 0
    with pytest.raises(HTTPException): run(admin.peer_progress(db, users['staff'], [cycle], people))


def test_explicit_md_board_reporting_is_resolved_without_fake_employee_parent():
    db, users, _, _ = configured(); md=deepcopy(db.employees.docs[0])
    md.update(role_title='Managing Director', reports_to_board=True, line_manager_id=None)
    before=deepcopy(md)
    directory, tree=build_staff_views([md],users['hr'])
    assert directory[0]['line_manager_name']=='Board of Directors'
    assert directory[0]['reporting_status']=='resolved' and directory[0]['line_manager_id'] is None
    assert md==before


def test_obsolete_kpi_note_is_removed_from_saved_library_view_without_rewriting_it():
    from .test_role_kpi_library import draft
    db, users, _, _ = configured()
    entry=draft(db,users['hr']); entry['source_reference']='Approved source; supplied weights are proposals pending approval.'
    row={'values':entry,'status':'Published','version':'example','updated_at':'2026-11-20','published_values':deepcopy(entry)}
    before=deepcopy(row)
    assert view(row)['source_reference']=='Approved source.'
    assert row==before


@pytest.mark.parametrize('saturday,expected', [(0, '2026-12-22'), (0.5, '2026-12-21')])
def test_acknowledgement_counts_a_scheduled_half_day_as_one_working_date(saturday, expected):
    db, users, _, row = configured()
    row.update(status='HR_Reviewed', meeting_completed_at='2026-12-18T10:00:00+00:00', overall_score=1.5, nine_box_placement='Core_Contributor')
    async def save(db, user, row, update, event): return {**row, **update}
    with patch.object(process, 'record', AsyncMock(return_value=(row, db.employees.docs[0]))), patch.object(process, 'today', return_value=date(2026, 12, 18)), patch.object(process, 'instant', return_value=datetime(2026, 12, 18, 12, tzinfo=timezone.utc)), patch.object(process, 'save', side_effect=save), patch.object(process, 'notice', AsyncMock()), patch.object(process, 'hr_notice', AsyncMock()), patch('utils.leave_policy.contract_policy', AsyncMock(return_value={'saturday_weight': saturday})):
        assert run(reviews.release(db, users['hr'], row['id'], {'expected_version': row['version']}))['ack_due_on'] == expected
