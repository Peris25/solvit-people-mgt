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
