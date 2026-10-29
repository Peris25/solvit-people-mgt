"""FTE login rollout stays read-only, scoped and least privileged."""
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import access
from utils.employee_accounts import employee_login_review, provision_employee_account
from .integrity_fakes import Database, employee, account
from .test_solver_security import run, request


def admin():
    return {"id": "admin", "role": "it_admin", "tenant_id": "solvit"}


def test_review_links_legacy_ids_without_changing_roles_passwords_or_records():
    staff = employee(employment_type="Full-Time")
    user = account(employee_id=str(staff["_id"]), role="line_manager", is_active=True,
                   password_hash="synthetic-private-hash", must_change_password=True)
    db = Database([staff], [user]); before = deepcopy((db.employees.docs, db.users.docs))
    rows = run(employee_login_review(db, admin()))
    assert rows[0]["status"] == "Linked"
    assert rows[0]["role"] == "line_manager"
    assert rows[0]["must_change_password"] is True
    assert "password_hash" not in rows[0]
    assert "synthetic-private-hash" not in str(rows)
    assert (db.employees.docs, db.users.docs) == before
    assert db.users.writes == db.employees.writes == db.audit_logs.writes == 0


@pytest.mark.parametrize("case", ["missing", "disabled", "duplicate_accounts", "invalid_link", "duplicate_email", "exited", "unknown_type"])
def test_review_identifies_rollout_issues_without_automatic_repair(case):
    staff = employee(employment_type="FTE")
    users = [account(employee_id="staff", is_active=True)]
    employees = [staff]
    if case == "missing": users = []
    if case == "disabled": users[0]["is_active"] = False
    if case == "duplicate_accounts": users.append(account(employee_id="staff"))
    if case == "invalid_link": users[0]["employee_id"] = "missing"
    if case == "duplicate_email": employees.append(employee("second", " STAFF@example.com ", employment_type="Full_Time"))
    if case == "exited": staff["lifecycle_state"] = "Exited"
    if case == "unknown_type": staff.pop("employment_type")
    db = Database(employees, users)
    rows = run(employee_login_review(db, admin()))
    assert rows[0]["status"] == "Needs review"
    assert rows[0]["issues"]
    assert db.users.writes == db.employees.writes == 0


def test_review_excludes_solvers_and_other_tenants():
    db = Database([employee(employment_type="FTE"), employee("gig", "gig@example.com", employment_type="Solver"),
                   employee("foreign", "foreign@example.com", tenant_id="foreign", employment_type="FTE")])
    rows = run(employee_login_review(db, admin()))
    assert [row["employee_id"] for row in rows] == ["staff"]


@pytest.mark.parametrize("role", ["employee", "line_manager", "hr_manager", "finance", "solver"])
def test_review_endpoint_rejects_roles_outside_account_administration(role):
    with patch.object(access, "get_current_user", AsyncMock(return_value={"id": "user", "role": role})):
        with pytest.raises(HTTPException) as error:
            run(access.review_employee_logins(request()))
    assert error.value.status_code == 403


@pytest.mark.parametrize("state", ["Exited", "Terminated", "Inactive"])
def test_provisioning_cannot_enable_departed_employee(state):
    db = Database([employee(lifecycle_state=state)])
    with pytest.raises(HTTPException) as error:
        run(provision_employee_account(db, "staff", "never-used", admin()))
    assert error.value.status_code == 409
    assert db.users.writes == 0
