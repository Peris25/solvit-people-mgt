"""Technical administration does not imply HR-wide access; synthetic fixtures."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from utils.access_matrix import get_module_access, RUNTIME_OVERRIDES
from utils.employee_access import authorize_employee
from utils import performance_workflows, leave_workflow
from .test_leave_management import fixture, payload, budget, fixed_date


@pytest.mark.parametrize('module', ['M04', 'M05', 'M08', 'M09', 'M18'])
def test_it_team_layer_is_direct_report_scoped_and_honors_revocation(module):
    db, actors = fixture(); actor = {**actors['boss'], 'role': 'it_admin'}
    assert get_module_access(module, 'it_admin') == {'level': 'Manage', 'scope': 'own_team'}
    assert asyncio.run(authorize_employee(db, actor, 'staff', module, write=True))['id'] == 'staff'
    with pytest.raises(HTTPException): asyncio.run(authorize_employee(db, actor, 'other', module, write=True))
    RUNTIME_OVERRIDES[(module, 'it_admin')] = None
    try:
        with pytest.raises(HTTPException): asyncio.run(authorize_employee(db, actor, 'staff', module, write=True))
    finally: del RUNTIME_OVERRIDES[(module, 'it_admin')]


def test_it_manager_recommends_direct_report_leave_but_cannot_hr_override():
    db, actors = fixture(); actor = {**actors['boss'], 'role': 'it_admin'}
    with patch('utils.email_service.send_email', AsyncMock()), patch('automation.engine.automation_engine.fire_event', AsyncMock()):
        result = asyncio.run(leave_workflow.create(db, actors['staff'], payload(), budget()))
    viewed = asyncio.run(leave_workflow.view(db, actor, db.leave_requests.docs[0]))
    assert viewed['approval_stage'] == 'manager' and viewed['can_hr_override'] is False
    with pytest.raises(HTTPException):
        asyncio.run(leave_workflow.decide(db, actor, result['id'], {'decision':'Approve','hr_override':True}, budget()))


def test_it_manager_does_not_gain_hr_review_or_compensation_permissions():
    db, actors = fixture(); actor = {**actors['boss'], 'role':'it_admin'}
    row = {'id':'review','employee_id':'staff','workflow_version':1,'status':'Self_Submitted','manager_assessment':{'comment':'Team review'}}
    projection = performance_workflows.projection(row, actor, db.employees.docs[0])
    assert projection['can_manage'] and not projection['can_hr_review']
    assert get_module_access('M10', 'it_admin') is None
