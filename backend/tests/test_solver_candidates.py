import asyncio
from copy import deepcopy
from unittest.mock import patch, AsyncMock
import pytest
from fastapi import HTTPException
from utils import solver_candidates as service
from .test_profile_self_service import fixture as base_fixture
from .integrity_fakes import Collection

def run(coro): return asyncio.run(coro)

def fixture():
    db, users = base_fixture()
    db.candidates = Collection(); db.solvers = Collection()
    run(db.candidates.insert_one({'id': 'candidate', 'tenant_id': 'solvit', 'candidate_type': 'Solver', 'requisition_id': 'req',
        'full_name': 'Synthetic Applicant', 'email': 'candidate@example.com', 'phone_number': '0712345678',
        'current_stage': 'Stage 1 — Passed / Awaiting Values Assessment', 'status': 'Active',
        'stage_scores': {'stage_1_eligibility': 'Passed'}, 'has_driving_licence': True, 'updated_at': '2026-11-04T08:00:00Z'}))
    return db, users

def edit(db, user, **changes):
    body = service.Edit(expected_version=service.version(db.candidates.docs[0]), reason='HR verified applicant progression', **changes)
    return run(service.update(db, user, 'candidate', body))

def test_legacy_stage_one_pass_is_eligible_not_active_or_overall_passed():
    db, _ = fixture(); before = deepcopy(db.candidates.docs[0])
    result = service.projection(before, True, True)
    assert result['recruitment_stage'] == 'Eligible'
    assert db.candidates.docs[0] == before and not db.solvers.docs

@pytest.mark.parametrize('stage', ['Interviewing', 'Awaiting assessment', 'Passed', 'Awaiting confirmation', 'On hold', 'Not selected', 'Withdrawn'])
def test_hr_can_edit_stages_without_creating_solver_or_changing_assessment_answers(stage):
    db, users = fixture(); result = edit(db, users['hr'], stage=stage)
    assert result['recruitment_stage'] == stage
    assert not db.solvers.docs
    assert db.candidates.docs[0]['stage_scores'] == {'stage_1_eligibility': 'Passed'}
    assert db.candidates.docs[0]['has_driving_licence'] is True
    assert db.audit_logs.docs[0]['event'] == 'solver.applicant.updated'

@pytest.mark.parametrize('actor', ['staff', 'other', 'finance'])
def test_ordinary_accounts_cannot_update_applicants(actor):
    db, users = fixture()
    with pytest.raises(HTTPException) as error: edit(db, users[actor], stage='Passed')
    assert error.value.status_code == 403
    assert len(db.candidates.docs) == 1 and not db.audit_logs.docs

def test_explicit_hr_confirmation_is_required_and_creates_one_real_active_solver():
    db, users = fixture()
    with pytest.raises(HTTPException): edit(db, users['hr'], stage='Active', confirm_active=True)
    edit(db, users['hr'], stage='Passed')
    with pytest.raises(HTTPException): edit(db, users['hr'], stage='Active')
    result = edit(db, users['hr'], stage='Active', confirm_active=True)
    assert result['solver_id'] == db.solvers.docs[0]['id']
    assert db.solvers.docs[0]['lifecycle_state'] == 'Active'
    assert db.solvers.docs[0]['activation_publication_state'] == 'Ready'
    assert db.solvers.docs[0]['phone_number'] == '+254712345678'
    assert 'onboarded_at' not in db.solvers.docs[0]
    assert not result['can_edit']
    with pytest.raises(HTTPException): edit(db, users['hr'], stage='Active', confirm_active=True)
    assert len(db.solvers.docs) == 1

def test_stale_edit_and_cross_tenant_reference_are_rejected():
    db, users = fixture()
    body = service.Edit(expected_version=service.version(db.candidates.docs[0]), reason='HR correction of contact details', stage='Interviewing')
    db.candidates.docs[0]['updated_at'] = 'changed'
    with pytest.raises(HTTPException) as error: run(service.update(db, users['hr'], 'candidate', body))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException): run(service.update(db, {**users['hr'], 'tenant_id': 'other'}, 'candidate', body))
    assert not db.audit_logs.docs

def test_contact_duplicates_and_existing_solver_collision_are_not_merged():
    db, users = fixture()
    run(db.candidates.insert_one({'id': 'other', 'tenant_id': 'solvit', 'email': 'taken@example.com', 'phone_number': '+254700000001'}))
    with pytest.raises(HTTPException): edit(db, users['hr'], email='TAKEN@example.com')
    with pytest.raises(HTTPException): edit(db, users['hr'], phone_number='0700000001')
    edit(db, users['hr'], stage='Passed')
    run(db.solvers.insert_one({'id': 'existing', 'tenant_id': 'solvit', 'phone_number': '+254712345678', 'lifecycle_state': 'Inactive'}))
    with pytest.raises(HTTPException): edit(db, users['hr'], stage='Active', confirm_active=True)
    assert len(db.solvers.docs) == 1 and db.solvers.docs[0]['lifecycle_state'] == 'Inactive'

def test_audit_failure_does_not_publish_changes_or_create_solver():
    db, users = fixture(); edit(db, users['hr'], stage='Passed'); before = deepcopy(db.candidates.docs[0])
    with patch.object(db.audit_logs, 'insert_one', side_effect=RuntimeError('synthetic audit outage')):
        with pytest.raises(RuntimeError): edit(db, users['hr'], stage='Active', confirm_active=True)
    assert db.candidates.docs[0] == before and not db.solvers.docs

def test_managers_cannot_edit_private_solver_applicants():
    db, users = fixture()
    with pytest.raises(HTTPException) as error:
        edit(db, users['manager'], stage='Interviewing')
    assert error.value.status_code == 403 and not db.solvers.docs


def test_applicant_linked_to_fte_cannot_be_converted_again_as_solver():
    db, users = fixture(); db.candidates.docs[0]['employee_id'] = 'staff'
    assert service.projection(db.candidates.docs[0], True, True)['can_edit'] is False
    with pytest.raises(HTTPException): edit(db, users['hr'], stage='Active', confirm_active=True)
    assert not db.solvers.docs and db.users.writes == 0


def test_unchanged_save_preserves_legacy_stage_and_timestamps():
    db, users = fixture(); before = deepcopy(db.candidates.docs[0])
    result = edit(db, users['hr'], full_name=before['full_name'], email=before['email'],
                  phone_number=before['phone_number'], stage='Eligible')
    assert result['recruitment_stage'] == 'Eligible'
    assert db.candidates.docs[0] == before and not db.audit_logs.docs
