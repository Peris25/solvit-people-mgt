import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import employees
from .integrity_fakes import Collection, Database, account, employee


def remove(db, target, user=None, name=None):
    request = SimpleNamespace(json=AsyncMock(return_value={"confirm_name": name or target["full_name"]}))
    with patch.object(employees, "get_db", return_value=db), patch.object(
        employees, "get_current_user", AsyncMock(return_value=user or {"id": "hr", "role": "hr_admin"})
    ):
        return asyncio.run(employees.remove_employee(str(target["_id"]), request))


def test_removal_retains_recovery_copy_and_history():
    target, other = employee("extra"), employee("keeper")
    db = Database([target, other])
    db.removed_employee_records = Collection()
    db.leave_requests = Collection([{"_id": "history", "employee_id": "extra"}])
    history = deepcopy(db.leave_requests.docs)
    assert remove(db, target)["status"] == "removed"
    assert db.employees.docs == [other]
    assert db.removed_employee_records.docs[0]["record"] == target
    assert db.audit_logs.docs[0]["action"] == "employee.removed"
    assert db.leave_requests.docs == history
    assert not db.integrity_locks.docs


@pytest.mark.parametrize("case", ["staff", "manager", "wrong_name", "account", "email_account", "report", "self", "board", "tenant"])
def test_removal_rejects_unsafe_or_unauthorized_requests(case):
    target = employee("extra")
    db = Database([target])
    db.removed_employee_records = Collection()
    user = {"id": "hr", "role": "hr_admin"}
    name = None
    if case == "staff": user["role"] = "employee"
    if case == "manager": user["role"] = "hr_manager"
    if case == "wrong_name": name = "different person"
    if case == "account": db.users = Collection([account(employee_id=str(target["_id"]))])
    if case == "email_account": db.users = Collection([account(email=" EXTRA@EXAMPLE.COM ")])
    if case == "email_account": target["work_email"] = db.employees.docs[0]["work_email"] = "extra@example.com"
    if case == "report": db.employees.docs.append(employee("report", line_manager_id="extra", lifecycle_state="Exited"))
    if case == "self": user["employee_id"] = "extra"
    if case == "board": db.employees.docs[0]["board_only"] = True
    if case == "tenant": user["tenant_id"] = "other"
    with pytest.raises(HTTPException): remove(db, target, user, name)
    assert db.employees.writes == db.removed_employee_records.writes == db.audit_logs.writes == 0


def test_backup_failure_does_not_delete_employee_and_retains_lock():
    target = employee("extra")
    db = Database([target])
    db.removed_employee_records = SimpleNamespace(insert_one=AsyncMock(side_effect=RuntimeError("storage unavailable")))
    with pytest.raises(RuntimeError): remove(db, target)
    assert db.employees.docs == [target]
    assert db.integrity_locks.docs


@pytest.mark.parametrize("existing,start,expected", [(True, None, None), (False, "2026-01-01", "2026-04-01")])
def test_existing_roster_entry_keeps_unknown_dates_and_skips_onboarding(existing, start, expected):
    db = Database([employee("boss")])
    payload = employees.EmployeeCreate(full_name="Reference Employee", work_email="new@example.com",
        department="IT Support", role_title="IT Support", role_level="", line_manager_id="boss",
        start_date=start, existing_employee=existing, lifecycle_state="Active")
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})), patch(
        "routes.masters_settings.get_setting", AsyncMock(return_value=3)
    ), patch("automation.engine.automation_engine.fire_event", new_callable=AsyncMock) as event, patch(
        "utils.email_triggers.fire_and_forget", new_callable=AsyncMock
    ) as email:
        result = asyncio.run(employees.create_employee(payload, SimpleNamespace()))
    assert result["start_date"] == start
    assert result["probation_end_date"] == expected
    assert "existing_employee" not in result
    assert event.await_count == email.await_count == (0 if existing else 1)


@pytest.mark.parametrize("start,existing", [(None, False), ("2026-02-31", True)])
def test_creation_rejects_missing_new_hire_date_or_invalid_date(start, existing):
    db = Database()
    payload = employees.EmployeeCreate(full_name="Example", work_email="new@example.com", department="Operations",
        role_title="Example", role_level="L2", start_date=start, existing_employee=existing)
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})), patch("routes.masters_settings.get_setting", AsyncMock(return_value=3)):
        with pytest.raises(HTTPException) as error:
            asyncio.run(employees.create_employee(payload, SimpleNamespace()))
    assert error.value.status_code == 422
    assert not db.employees.docs
