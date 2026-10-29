import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import access
from utils.employee_accounts import provision_employee_account, employee_login_review
from .integrity_fakes import Database, employee, account


@pytest.mark.parametrize("role", ["employee", "line_manager", "hr_manager", "finance", "executive", "board", "solver"])
def test_provisioning_and_review_deny_other_roles(role):
    with patch.object(access, "get_current_user", AsyncMock(return_value={"role": role})):
        for action in [access.create_employee_account(access.EmployeeAccountRequest(employee_id="staff"), None), access.review_employee_logins(None)]:
            with pytest.raises(HTTPException) as error:
                asyncio.run(action)
            assert error.value.status_code == 403


def test_hr_route_creates_employee_with_mandatory_password_change():
    db = Database([employee()])
    with patch.object(access, "get_db", return_value=db), patch.object(access, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})), patch("utils.employee_accounts.hash_password", return_value="synthetic-hash"):
        result = asyncio.run(access.create_employee_account(access.EmployeeAccountRequest(employee_id="staff", initial_password="Synthetic-staff-setup"), None))
    assert result["created"] is True
    assert db.users.docs[0]["role"] == "employee"
    assert db.users.docs[0]["must_change_password"] is True
    assert db.users.docs[0]["password_hash"] == "synthetic-hash"
    assert "initial_password" not in db.users.docs[0]
    assert db.audit_logs.docs


@pytest.mark.parametrize("role", ["it_admin", "hr_admin", "line_manager", "finance", "executive", "board"])
def test_hr_cannot_link_or_reset_existing_non_employee_accounts(role):
    db = Database([employee()], [account(role=role, password_hash="preserve-this", employee_id="staff")])
    with pytest.raises(HTTPException) as error:
        asyncio.run(provision_employee_account(db, "staff", "Ignored-initial", {"id": "hr", "role": "hr_admin"}))
    assert error.value.status_code == 403
    assert db.users.docs[0]["password_hash"] == "preserve-this"
    assert not db.users.writes


def test_hr_link_is_idempotent_and_preserves_existing_password_and_role():
    db = Database([employee()], [account(role="employee", password_hash="preserved", employee_id=None)])
    for unused in range(2):
        result = asyncio.run(provision_employee_account(db, "staff", None, {"id": "hr", "role": "hr_admin"}))
        assert result["created"] is False
    assert len(db.users.docs) == 1
    assert db.users.docs[0]["employee_id"] == "staff"
    assert db.users.docs[0]["password_hash"] == "preserved"
    assert db.users.docs[0]["role"] == "employee"


def test_hr_login_review_preserves_board_visibility_and_hides_account_ids():
    db = Database([employee(), employee("board", email="board@example.com", board_only=True)], [account(employee_id="staff", role="employee")])
    result = asyncio.run(employee_login_review(db, {"id": "hr", "role": "hr_admin"}))
    assert len(result) == 1
    assert result[0]["employee_id"] == "staff"
    assert "account_id" not in result[0]
    assert "password_hash" not in result[0]
