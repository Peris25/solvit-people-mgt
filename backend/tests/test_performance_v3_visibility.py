from copy import deepcopy
from datetime import date
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import HTTPException

from utils import performance_v3 as service, performance_workflows as workflow
from utils.employee_accounts import provision_employee_account
from .test_profile_self_service import fixture, run
from .test_role_kpi_library import approved, save


def summary_review():
    return {'id': 'review', 'employee_id': 'staff', 'line_manager_id': 'manager', 'status': 'HR_Reviewed', 'workflow_version': 3,
            'peer_due_on': '2026-11-07', 'peer_summary': {'response_count': 3, 'averages': [8] * 5,
            'comments': ['A useful anonymous observation'], 'retention_average': 10}}


@pytest.mark.parametrize('actor', ['hr', 'manager'])
def test_hr_and_current_manager_see_anonymous_averages_before_meeting(actor):
    db, users = fixture()
    with patch.object(service, 'today', return_value=date(2026, 11, 8)):
        result = workflow.projection(summary_review(), users[actor], db.employees.docs[0])
    assert result['peer_summary']['averages'] == [8] * 5
    assert ('retention_average' in result['peer_summary']) == (actor == 'hr')


def test_peer_projection_never_forwards_unexpected_respondent_metadata():
    db, users = fixture(); row = summary_review()
    row['peer_summary'].update(respondent_ids=['private'], responses=[{'actor': 'private'}])
    with patch.object(service, 'today', return_value=date(2026, 11, 8)):
        result = workflow.projection(row, users['hr'], db.employees.docs[0])
    assert not {'respondent_ids', 'responses'} & set(result['peer_summary'])


def test_manager_must_match_review_assignment_as_well_as_current_reporting_link():
    db, users = fixture(); row = summary_review(); row['line_manager_id'] = 'someone-else'
    with patch.object(service, 'today', return_value=date(2026, 11, 8)):
        assert 'peer_summary' not in workflow.projection(row, users['manager'], db.employees.docs[0])


@pytest.mark.parametrize('actor', ['hr', 'manager', 'staff'])
@pytest.mark.parametrize('count,day', [(2, 8), (3, 7)])
def test_no_rolling_or_small_group_averages_even_for_hr(actor, count, day):
    db, users = fixture(); row = summary_review(); row['peer_summary']['response_count'] = count
    with patch.object(service, 'today', return_value=date(2026, 11, day)):
        assert 'peer_summary' not in service.projection(row, users[actor], db.employees.docs[0])


def test_employee_sees_results_only_after_release_and_never_retention():
    db, users = fixture(); row = summary_review(); employee = db.employees.docs[0]
    with patch.object(service, 'today', return_value=date(2026, 11, 8)):
        assert 'peer_summary' not in service.projection(row, users['staff'], employee)
        row.update(released_at='2026-11-08T12:00:00Z', released_by='hr')
        result = service.projection(row, users['staff'], employee)
    assert 'retention_average' not in result['peer_summary']
    assert row['peer_summary']['retention_average'] == 10


def test_employee_kpis_assigned_at_account_setup_once_and_visible_with_legacy_id():
    db, users = fixture(); employee = db.employees.docs[0]; employee['role_title'] = 'IT Support'
    entry = approved(db, users['hr']); save(db, users['hr'], entry, action='publish')
    with patch('utils.employee_accounts.hash_password', return_value='synthetic-hash'):
        run(provision_employee_account(db, 'staff', None, users['hr']))
    first = run(service.assignment(db, employee)); assert first
    assert first['values']['goals'] == entry['goals']
    run(provision_employee_account(db, 'staff', None, users['hr']))
    assert run(service.assignment(db, employee))['version'] == first['version']
    legacy = {**users['staff'], 'employee_id': str(employee['_id'])}
    visible = run(service.my_kpis(db, legacy))
    assert visible['goals'] == entry['goals']
    assert not {'approval_reference', 'updated_by', 'tenant_id', '_id'} & set(visible)


def test_unapproved_or_missing_role_does_not_invent_targets():
    db, users = fixture(); employee = db.employees.docs[0]; employee['role_title'] = 'IT Support'
    save(db, users['hr'], approved(db, users['hr']), action='draft')
    run(service.auto_assignment(db, employee, users['hr']))
    assert run(service.assignment(db, employee)) is None


def test_my_kpis_has_no_cross_employee_selector_or_write_on_read():
    db, users = fixture()
    before = deepcopy(db.system_settings.docs)
    assert run(service.my_kpis(db, users['staff'])) is None
    assert db.system_settings.docs == before
    with pytest.raises(HTTPException): run(service.my_kpis(db, {**users['staff'], 'tenant_id': 'foreign'}))


def test_week_three_check_is_new_task_without_rewriting_old_checklists():
    from routes.onboarding import FTE_ONBOARDING_TASKS
    task = next(t for t in FTE_ONBOARDING_TASKS if t['task_key'] == 'KPI_W3')
    assert task['day_offset'] == 14 and task['assigned_role'] == 'line_manager'
