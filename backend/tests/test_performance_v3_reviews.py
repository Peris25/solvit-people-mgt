from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from utils import performance_v3 as process, performance_v3_reviews as reviews
from .test_profile_self_service import fixture, run


def review():
    return {'id': 'synthetic-review', 'employee_id': 'staff', 'line_manager_id': 'manager',
            'version': 'original', 'workflow_version': 3, 'status': 'Self_Draft',
            'starts_on': '2026-11-01', 'self_due_on': '2026-11-07', 'peer_due_on': '2026-11-07',
            'manager_due_on': '2026-11-14', 'section_a_kpis': [
                {'id': 'quality', 'direction': 'Higher', 'target_value': 100, 'weight': 100}],
            'group_weights': {}}


def self_payload():
    return {'expected_version': 'original', 'submit': True, 'assessment': {
        'actuals': {'quality': {'actual': 90, 'self_score': 1.5, 'evidence': 'Verified synthetic work summary'}},
        'values': [{'score': 8, 'example': 'Synthetic work example'} for _ in range(5)],
        'accomplishments': ['First achievement', 'Second achievement', 'Third achievement'],
        'challenge': 'A challenge', 'do_differently': 'An improvement', 'support': 'Support requested'}}


@pytest.mark.parametrize('actor', ['other', 'manager', 'hr', 'finance'])
def test_other_people_cannot_complete_employee_assessment(actor):
    db, users = fixture(); employee = db.employees.docs[0]
    with patch.object(process, 'record', AsyncMock(return_value=(review(), employee))), \
         patch.object(process, 'save', AsyncMock()) as save:
        with pytest.raises(HTTPException) as error:
            run(reviews.self_assessment(db, users[actor], 'synthetic-review', self_payload()))
        assert error.value.status_code == 403
        save.assert_not_awaited()


def test_self_submission_validates_and_routes_only_to_manager():
    db, users = fixture(); employee = db.employees.docs[0]; row = review()
    async def save(db, user, original, update, event): return {**original, **deepcopy(update)}
    with patch.object(process, 'record', AsyncMock(return_value=(row, employee))), \
         patch.object(process, 'today', return_value=date(2026, 11, 2)), \
         patch.object(process, 'evidence', AsyncMock(return_value=[])), \
         patch.object(process, 'save', side_effect=save), \
         patch.object(process, 'notice', AsyncMock()) as notice:
        result = run(reviews.self_assessment(db, users['staff'], row['id'], self_payload()))
        assert result['status'] == 'Self_Submitted'
        assert 'overall_score' not in result
        assert notice.await_args.args[4] == 'manager'


def test_draft_is_partial_but_submission_requires_all_narrative_and_values():
    db, users = fixture(); employee = db.employees.docs[0]
    with patch.object(process, 'record', AsyncMock(return_value=(review(), employee))), \
         patch.object(process, 'today', return_value=date(2026, 11, 2)), \
         patch.object(process, 'save', AsyncMock()) as save:
        with pytest.raises(HTTPException):
            run(reviews.self_assessment(db, users['staff'], 'synthetic-review', {
                'expected_version': 'original', 'submit': True, 'assessment': {}}))
        save.assert_not_awaited()


@pytest.mark.parametrize('actor', ['staff', 'other', 'hr', 'finance'])
def test_manager_assessment_cannot_be_submitted_by_employee_or_hr(actor):
    db, users = fixture(); employee = db.employees.docs[0]; row = {**review(), 'status': 'Self_Submitted'}
    with patch.object(process, 'record', AsyncMock(return_value=(row, employee))):
        with pytest.raises(HTTPException) as error:
            run(reviews.manager_assessment(db, users[actor], row['id'], {'expected_version': 'original'}))
        assert error.value.status_code == 403


def test_manager_correction_requires_explanation_and_stale_versions_are_rejected():
    db, users = fixture(); employee = db.employees.docs[0]
    row = {**review(), 'status': 'Self_Submitted', 'self_assessment': self_payload()['assessment']}
    with patch.object(process, 'record', AsyncMock(return_value=(row, employee))), \
         patch.object(process, 'today', return_value=date(2026, 11, 9)), \
         patch.object(process, 'save', AsyncMock()) as save:
        for body in [
            {'expected_version': 'old', 'actuals': {'quality': {'actual': 90}}, 'summary': 'Review'},
            {'expected_version': 'original', 'actuals': {'quality': {'actual': 80}}, 'summary': 'Review'},
        ]:
            with pytest.raises(HTTPException): run(reviews.manager_assessment(db, users['manager'], row['id'], body))
        save.assert_not_awaited()


def test_hr_cannot_compile_own_review():
    db, users = fixture(); employee = next(e for e in db.employees.docs if e['id'] == 'hr')
    with patch.object(process, 'record', AsyncMock(return_value=({**review(), 'employee_id': 'hr'}, employee))):
        with pytest.raises(HTTPException) as error:
            run(reviews.compile_review(db, users['hr'], 'synthetic-review', {'expected_version': 'original'}))
        assert error.value.status_code == 403
