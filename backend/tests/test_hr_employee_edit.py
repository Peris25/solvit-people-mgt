"""HR edits do not require external legacy checks or orphan login accounts."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import employees
from .integrity_fakes import Database, employee, account
from .test_solver_security import run, request


def test_hr_email_change_preserves_unambiguous_legacy_login_without_manual_review():
    staff = employee()
    user = account(role='line_manager', password_hash='synthetic-preserved-hash', is_active=True)
    user['employee_id'] = str(user['_id'])
    db = Database([staff], [user])
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value={'id': 'hr', 'role': 'hr_admin', 'tenant_id': 'solvit'})):
        result = run(employees.update_employee('staff', employees.EmployeeUpdate(work_email='new@example.com', start_date='2026-01-01'), request()))
    assert result['work_email'] == 'new@example.com'
    assert db.employees.docs[0]['start_date'] == '2026-01-01'
    saved = db.users.docs[0]
    assert saved['employee_id'] == 'staff'
    assert saved['email'] == user['email']
    assert saved['password_hash'] == user['password_hash']
    assert saved['role'] == 'line_manager'


def test_hr_cannot_reassign_another_employees_login_through_email_edit():
    first, second = employee(), employee('other', 'other@example.com')
    user = account(employee_id='other')
    db = Database([first, second], [user])
    with patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value={'id': 'hr', 'role': 'hr_admin', 'tenant_id': 'solvit'})):
        with pytest.raises(HTTPException):
            run(employees.update_employee('staff', employees.EmployeeUpdate(work_email='new@example.com'), request()))
    assert db.employees.writes == db.users.writes == 0
