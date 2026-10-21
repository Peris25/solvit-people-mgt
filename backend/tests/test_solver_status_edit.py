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


@pytest.mark.parametrize("state", ["", "invalid", "Active"])
def test_invalid_status_and_unverified_reactivation_are_rejected(state):
    db = database([solver(lifecycle_state="Inactive")])
    with patch.object(solvers, "get_db", return_value=db), \
            patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver("one", solvers.SolverUpdate(lifecycle_state=state), request()))
    assert error.value.status_code == (409 if state == "Active" else 422)
    assert db.solvers.writes == 0


@pytest.mark.parametrize("role", ["employee", "solver", "finance", "it_admin"])
def test_unauthorized_status_update_is_rejected_server_side(role):
    db = database([solver()])
    with patch.object(solvers, "get_db", return_value=db), \
            patch.object(solvers, "get_current_user", AsyncMock(return_value=actor(role))):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver("one", solvers.SolverUpdate(lifecycle_state="Inactive"), request()))
    assert error.value.status_code == 403
    assert db.solvers.writes == 0
