from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import leave
from utils.leave_balances import balances
from utils.leave_eligibility import eligible_leave_types
from utils import leave_policy as policy
from .test_leave_management import fixture, payload, run


@pytest.mark.parametrize('gender,expected', [('Female', 'Maternity'), (' female ', 'Maternity'),
    ('F', 'Maternity'), ('Male', 'Paternity'), ('m', 'Paternity'), (None, None), ('Other', None)])
def test_types_and_balances_follow_saved_employee_gender_without_writes(gender, expected):
    db, _ = fixture()
    employee = db.employees.docs[0]
    employee['gender'] = gender
    expected_parental = {expected} if expected else set()
    types = eligible_leave_types(leave.LEAVE_TYPES, employee)
    assert {'Maternity', 'Paternity'} & types.keys() == expected_parental
    assert {'Annual', 'Sick', 'Compassionate', 'Unpaid'} <= types.keys()
    with patch.object(leave, '_active_leave_types', AsyncMock(return_value=leave.LEAVE_TYPES)):
        result = run(balances(db, employee))
    assert {'Maternity', 'Paternity'} & result.keys() == expected_parental
    assert db.leave_balances.writes == 0


@pytest.mark.parametrize('gender,kind', [('Male', 'Maternity'), ('Female', 'Paternity'),
    (None, 'Maternity'), (None, 'Paternity')])
def test_api_preview_rejects_ineligible_parental_leave_even_with_forged_payload_gender(gender, kind):
    db, _ = fixture()
    employee = db.employees.docs[0]
    employee['gender'] = gender
    with pytest.raises(HTTPException) as error:
        run(policy.preview(db, employee, payload(leave_type=kind, gender='Female' if kind == 'Maternity' else 'Male')))
    assert error.value.status_code == 422
    assert 'profile' in error.value.detail


@pytest.mark.parametrize('gender,expected', [('Female', 'Maternity'), ('Male', 'Paternity'), (None, None)])
def test_leave_types_endpoint_uses_current_employees_record(gender, expected):
    db, users = fixture()
    db.employees.docs[0]['gender'] = gender
    with patch.object(leave, 'get_db', return_value=db), patch.object(leave, 'get_current_user', AsyncMock(return_value=users['staff'])), patch.object(leave, '_active_leave_types', AsyncMock(return_value=leave.LEAVE_TYPES)):
        result = run(leave.get_leave_types(object()))
    assert {'Maternity', 'Paternity'} & result.keys() == ({expected} if expected else set())


def test_saved_balance_snapshot_remains_unchanged_when_ineligible_type_is_hidden():
    from datetime import datetime, timezone
    db, _ = fixture()
    employee = db.employees.docs[0]
    employee['gender'] = 'Female'
    snapshot = {'employee_id': 'staff', 'tenant_id': 'solvit', 'year': datetime.now(timezone.utc).year,
                'Annual': {'remaining': 2.5}, 'Maternity': {'remaining': 90}, 'Paternity': {'remaining': 14}}
    from copy import deepcopy
    db.leave_balances.docs = [deepcopy(snapshot)]
    with patch.object(leave, '_active_leave_types', AsyncMock(return_value=leave.LEAVE_TYPES)):
        result = run(balances(db, employee))
    assert result['Maternity']['remaining'] == 90
    assert 'Paternity' not in result
    assert db.leave_balances.docs == [snapshot]
