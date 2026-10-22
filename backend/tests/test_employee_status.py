import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import employees
from .integrity_fakes import Database, employee


def update(db, value, role="hr_admin"):
    user = {"id": "actor", "role": role, "employee_id": "boss"}
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value=user)), patch.object(employees, "authorize_employee", AsyncMock()):
        return asyncio.run(employees.update_employee("staff", employees.EmployeeUpdate(lifecycle_state=value), SimpleNamespace()))


@pytest.mark.parametrize("status", ["Inactive", "Onboarding", "Probation", "PIP", "On_Leave", "Realignment", "Suspended", "Notice_Period", "Exiting", "Exited"])
def test_hr_admin_can_set_supported_status_without_changing_identity(status):
    original = employee("staff", line_manager_id="boss")
    db = Database([original])
    result = update(db, status)
    assert result["lifecycle_state"] == status
    assert result["id"] == original["id"]
    assert result["line_manager_id"] == "boss"
    assert db.audit_log.docs


@pytest.mark.parametrize("role", ["employee", "line_manager", "finance", "hr_manager"])
def test_manual_status_change_remains_hr_admin_only(role):
    db = Database([employee("staff", line_manager_id="boss"), employee("boss", email="boss@example.com")])
    with pytest.raises(HTTPException) as error:
        update(db, "Inactive", role)
    assert error.value.status_code == 403
    assert not db.employees.writes


def test_invalid_status_cannot_be_written_but_unchanged_legacy_status_is_preserved():
    db = Database([employee("staff")])
    with pytest.raises(HTTPException) as error:
        update(db, "Typo status")
    assert error.value.status_code == 422
    assert not db.employees.writes
    db.employees.docs[0]["lifecycle_state"] = "Legacy status"
    assert update(db, "Legacy status")["lifecycle_state"] == "Legacy status"


def test_inactive_manager_requires_reassignment_of_direct_reports():
    db = Database([employee("staff"), employee("report", line_manager_id="staff")])
    with pytest.raises(HTTPException) as error:
        update(db, "Inactive")
    assert error.value.status_code == 409
    assert not db.employees.writes


def test_status_edit_does_not_override_started_offboarding():
    db = Database([employee("staff", lifecycle_state="Exiting", offboarding_started_at="2026-10-01")])
    with pytest.raises(HTTPException) as error:
        update(db, "Active")
    assert error.value.status_code == 409
    assert not db.employees.writes


@pytest.mark.parametrize("path", ["bulk", "transition"])
def test_inactive_status_is_supported_by_existing_hr_workflow_routes(path):
    db = Database([employee("staff")])
    request = SimpleNamespace(json=AsyncMock(return_value={"employee_ids": ["staff"], "lifecycle_state": "Inactive"}))
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})), patch("automation.engine.automation_engine.fire_event", new_callable=AsyncMock):
        asyncio.run(employees.bulk_transition(request) if path == "bulk" else employees.transition_state("staff", request))
    assert db.employees.docs[0]["lifecycle_state"] == "Inactive"
