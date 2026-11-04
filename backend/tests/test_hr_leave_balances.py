import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from utils.hr_leave_balances import overview
from .test_staff_home import fixture
from .integrity_fakes import employee


@pytest.mark.parametrize("role", ["employee", "line_manager", "it_admin", "finance", "executive", "board", "solver"])
def test_non_hr_cannot_list_balances(role):
    db, user, _ = fixture(role)
    with pytest.raises(HTTPException) as error:
        asyncio.run(overview(db, user))
    assert error.value.status_code == 403


@pytest.mark.parametrize("role", ["hr_admin", "hr_manager", "general_manager"])
def test_hr_reuses_balances_with_filters_tenant_isolation_and_no_writes(role):
    db, user, _ = fixture(role)
    db.employees.docs += [employee("foreign", tenant_id="other", full_name="Foreign"), employee("solver", employment_type="Solver", full_name="Solver")]
    before = deepcopy(db.employees.docs)
    value = {"Annual": {"remaining": 4.5, "used": 13, "accrued_kenyan_act": 17.5}, "annual_available_to_request": 4.5, "source": "stored_snapshot"}
    with patch("utils.hr_leave_balances.balances", new=AsyncMock(return_value=value)) as loader:
        result = asyncio.run(overview(db, user, search="ada", department="IT Support"))
    assert result["total"] == 1
    assert result["items"][0]["balances"] == value
    assert result["items"][0]["annual_pending_days"] == 0
    assert loader.await_count == 1
    assert not any(field in str(result) for field in ("password_hash", "bank_account", "medical_notes", "current_salary_kes"))
    assert db.employees.docs == before and db.employees.writes == 0


def test_ambiguous_employee_is_review_state_not_wrong_balance():
    db, user, _ = fixture("hr_admin")
    db.employees.docs.append(employee("staff", full_name="Duplicate", email="duplicate@example.com"))
    with patch("utils.hr_leave_balances.balances", new=AsyncMock()) as loader:
        result = asyncio.run(overview(db, user, search="ada"))
    assert result["items"][0]["needs_review"] is True
    assert result["items"][0]["balances"] is None
    loader.assert_not_awaited()


def test_only_page_balances_are_calculated_and_errors_do_not_become_zero():
    db, user, _ = fixture("hr_admin")
    with patch("utils.hr_leave_balances.balances", new=AsyncMock(side_effect=HTTPException(409, "Conflicting snapshots"))) as loader:
        result = asyncio.run(overview(db, user, limit=1))
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["items"][0]["balances"] is None
    assert result["items"][0]["needs_review"]
    assert loader.await_count == 1
