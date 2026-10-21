"""HR status editing uses existing permissions, audit and activation gates."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import solvers
from .test_solver_security import actor, database, request, run, solver


@pytest.mark.parametrize("state", ["Registering", "Inactive", "Suspended", "Deactivated"])
def test_hr_status_change_preserves_identity_and_audits(state):
    original = solver()
    db = database([original])
    with patch.object(solvers, "get_db", return_value=db), \
            patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())), \
            patch("utils.email_triggers.fire_and_forget", AsyncMock()):
        result = run(solvers.update_solver(str(original["_id"]), solvers.SolverUpdate(lifecycle_state=state), request()))
    assert result["lifecycle_state"] == state
    assert db.solvers.docs[0]["id"] == original["id"]
    assert len(db.solvers.docs) == 1
    assert db.solvers.docs[0]["phone_number"] == original["phone_number"]
    assert any(row["event"] == "solver.updated" and "lifecycle_state" in row["detail"]["fields"] for row in db.audit_logs.docs)


@pytest.mark.parametrize("state", ["", "invalid"])
def test_invalid_status_is_rejected(state):
    db = database([solver(lifecycle_state="Inactive")])
    with patch.object(solvers, "get_db", return_value=db), \
            patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver("one", solvers.SolverUpdate(lifecycle_state=state), request()))
    assert error.value.status_code == 422
    assert db.solvers.writes == 0


@pytest.mark.parametrize('role', ['hr_admin', 'hr_manager'])
def test_hr_can_reactivate_and_edit_profile_without_external_verification(role):
    original = solver(lifecycle_state='Inactive', status='Suspended', activation_publication_state='Legacy', national_id='old')
    db = database([original])
    with patch.object(solvers, 'get_db', return_value=db), patch.object(solvers, 'get_current_user', AsyncMock(return_value=actor(role))), patch('utils.email_triggers.fire_and_forget', AsyncMock()):
        result = run(solvers.update_solver('one', solvers.SolverUpdate(lifecycle_state='Active', region='Coast', national_id_number='corrected', accuracy_score=85, onboarded_at=None), request()))
    assert result['lifecycle_state'] == result['status'] == 'Active'
    assert result['region'] == 'Coast' and result['accuracy_score'] == 85
    assert result['national_id'] == result['national_id_number'] == 'corrected'
    assert result['activation_publication_state'] == 'Ready'
    assert result['hr_status_decision']['actor_id'] == actor(role)['id']
    assert result.get('activation_date') is None
    assert db.solver_ratings.writes == 0


def test_hr_status_change_is_not_published_if_audit_fails():
    db = database([solver(lifecycle_state='Inactive')])
    db.audit_logs.insert_one = AsyncMock(side_effect=RuntimeError('synthetic audit outage'))
    with patch.object(solvers, 'get_db', return_value=db), patch.object(solvers, 'get_current_user', AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver('one', solvers.SolverUpdate(lifecycle_state='Active'), request()))
    assert error.value.status_code == 503
    assert solvers.workflow.view(db.solvers.docs[0])['lifecycle_state'] == 'Requires review'


@pytest.mark.parametrize("role", ["employee", "solver", "finance", "it_admin"])
def test_unauthorized_status_update_is_rejected_server_side(role):
    db = database([solver()])
    with patch.object(solvers, "get_db", return_value=db), \
            patch.object(solvers, "get_current_user", AsyncMock(return_value=actor(role))):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver("one", solvers.SolverUpdate(lifecycle_state="Inactive"), request()))
    assert error.value.status_code == 403
    assert db.solvers.writes == 0
