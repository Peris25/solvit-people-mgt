from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from routes import forms
from utils import performance_v3 as process, performance_v3_peers as peers
from .test_performance_v3_end_to_end import configured
from .test_profile_self_service import run
from .integrity_fakes import Collection


def test_selector_only_lists_current_reviewers_assignments_and_business_fields():
    db, users, cycle, review = configured()
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        choices = run(peers.listing(db, users['other']))
    assert len(choices) == 1 and choices[0]['employee_name'] == 'staff' and choices[0]['can_submit']
    assert not {'reviewer_employee_id', 'scores', 'retain', 'work_email', 'salary'} & set(choices[0])
    with patch.object(process, 'today', return_value=date(2026, 12, 7)):
        assert not run(peers.listing(db, users['other']))[0]['can_submit']


def test_future_and_submitted_tasks_cannot_be_selected():
    db, users, cycle, review = configured()
    with patch.object(process, 'today', return_value=date(2026, 11, 29)):
        assert not run(peers.listing(db, users['other']))[0]['can_submit']
    task = next(t for t in db.performance_peer_tasks.docs if t['reviewer_employee_id'] == 'other')
    task['status'] = 'Submitted'
    assert not run(peers.listing(db, users['other']))[0]['can_submit']


def test_self_and_inactive_subjects_are_not_available_and_stale_submission_fails():
    db, users, cycle, review = configured()
    task = next(t for t in db.performance_peer_tasks.docs if t['reviewer_employee_id'] == 'other')
    task['employee_id'] = 'other'
    assert run(peers.listing(db, users['other'])) == []
    task['employee_id'] = 'staff'; db.employees.docs[0]['lifecycle_state'] = 'Inactive'
    assert run(peers.listing(db, users['other'])) == []
    with pytest.raises(HTTPException):
        run(peers.submit(db, users['other'], task['id'], {'scores': [8] * 5, 'retain': 10, 'relationship': 'Peer', 'comment': ''}))
    assert not db.performance_peer_responses.docs


def test_legacy_form_26_cannot_create_parallel_identified_submissions():
    db, users, cycle, review = configured(); db.form_submissions = Collection()
    request = SimpleNamespace(json=AsyncMock(return_value={'data': {'integrity': 5}, 'employee_id': 'staff'}))
    with patch.object(forms, 'get_current_user', AsyncMock(return_value=users['other'])), patch.object(forms, 'get_db', return_value=db):
        for action in (forms.submit_form, forms.start_form_submission):
            with pytest.raises(HTTPException) as error: run(action('form-26', request))
            assert error.value.status_code == 409
        schema = run(forms.get_form_schema('form-26', request))
        run(db.form_submissions.insert_one({'id': 'legacy-peer', 'tenant_id': 'solvit', 'form_id': 'form-26', 'status': 'InProgress', 'next_required_role': 'employee'}))
        with patch.object(forms, 'authorize_signature', AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as error: run(forms.sign_form_step('legacy-peer', request))
            assert error.value.status_code == 409
    assert len(db.form_submissions.docs) == 1 and db.form_submissions.docs[0]['status'] == 'InProgress'
    assert schema['submission_mode'] == 'assigned_peer_review' and schema['rating_scale'] == {'min': 0, 'max': 10}
