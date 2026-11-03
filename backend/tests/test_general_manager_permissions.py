"""Business oversight is separate from account/security administration."""
import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routes import access
from utils.access_matrix import ACCESS_MATRIX, get_module_access, RUNTIME_OVERRIDES
from utils.employee_access import authorize_employee
from utils import leave_workflow, performance_workflows, mfa
from utils.form_access import authorize_signature
from .test_leave_management import fixture, payload, budget, fixed_date


def test_general_manager_has_hr_business_grants_and_is_privileged():
    assert 'general_manager' in access.SYSTEM_ROLES
    for module in ACCESS_MATRIX:
        assert get_module_access(module, 'general_manager') == get_module_access(module, 'hr_admin')
    assert mfa.privileged({'role': 'general_manager'})


@pytest.mark.parametrize('operation', [
    lambda req: access.list_users_with_roles(req),
    lambda req: access.update_user_role('target', req),
    lambda req: access.update_matrix_cell(req),
    lambda req: access.reset_matrix_cell(req),
    lambda req: access.create_custom_role(req),
    lambda req: access.delete_custom_role('custom', req),
    lambda req: access.review_employee_logins(req),
    lambda req: access.create_employee_account(access.EmployeeAccountRequest(employee_id='staff'), req),
])
def test_general_manager_cannot_administer_accounts_or_permissions(operation):
    with patch.object(access, 'get_current_user', AsyncMock(return_value={'id':'gm', 'role':'general_manager'})), patch.object(access, 'get_db') as db:
        with pytest.raises(HTTPException) as exc: asyncio.run(operation(SimpleNamespace()))
    assert exc.value.status_code == 403
    db.assert_not_called()


def test_general_manager_hr_leave_review_and_self_approval_protection():
    db, actors = fixture(); actor = {**actors['hr'], 'role':'general_manager'}
    with patch('utils.email_service.send_email', AsyncMock()), patch('automation.engine.automation_engine.fire_event', AsyncMock()):
        row = asyncio.run(leave_workflow.create(db, actors['staff'], payload(), budget()))
        viewed = asyncio.run(leave_workflow.view(db, actor, db.leave_requests.docs[0]))
        assert viewed['can_hr_override']
        body = {'decision':'Approve', 'hr_override':True, 'stage':'hr', 'reason':'Manager unavailable; reviewed by HR oversight', 'handover_reviewed':True, 'policy_review_confirmed':True}
        result = asyncio.run(leave_workflow.decide(db, actor, row['id'], body, budget()))
        assert result['status'] == 'Approved'
    own = {**db.leave_requests.docs[0], 'employee_id':actor['employee_id'], 'status':'Pending'}
    assert not asyncio.run(leave_workflow.view(db, actor, own))['can_hr_override']


def test_general_manager_permissions_honor_explicit_revocation():
    db, actors = fixture(); actor={**actors['hr'], 'role':'general_manager'}
    RUNTIME_OVERRIDES[('M05','general_manager')] = None
    try:
        with pytest.raises(HTTPException): asyncio.run(authorize_employee(db, actor, 'staff', 'M05', write=True))
    finally: del RUNTIME_OVERRIDES[('M05','general_manager')]


def test_general_manager_hr_review_projection_and_separate_finance_signature():
    db, actors = fixture(); actor={**actors['hr'], 'role':'general_manager'}
    row={'id':'review', 'employee_id':'staff', 'workflow_version':1, 'status':'Manager_Submitted'}
    assert performance_workflows.projection(row, actor, db.employees.docs[0])['can_hr_review']
    asyncio.run(authorize_signature(db, actor, 'hr_admin', 'staff'))
    for role in ('finance', 'it_admin', 'employee'):
        with pytest.raises(HTTPException): asyncio.run(authorize_signature(db, actor, role, 'staff'))


def test_it_can_only_sign_manager_steps_for_actual_reports():
    db, actors = fixture(); actor={**actors['boss'], 'role':'it_admin'}
    asyncio.run(authorize_signature(db, actor, 'line_manager', 'staff'))
    for subject in ('other', None):
        with pytest.raises(HTTPException): asyncio.run(authorize_signature(db, actor, 'line_manager', subject))
