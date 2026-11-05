import asyncio
import pytest
from fastapi import HTTPException
from utils.solver_intake_access import require_intake_admin
from utils.solver_candidates import permissions, record
from routes.solver_intake import _hr_or_solvers, _authorize_applicant_export
from utils.legacy_security import recruitment_scope

@pytest.mark.parametrize('role', ['employee', 'line_manager', 'solvers_manager', 'executive', 'general_manager', 'hr_manager', 'solver', 'finance', 'board', 'custom_admin'])
def test_private_intake_denies_other_roles_before_database_access(role):
    user = {'role': role}
    assert asyncio.run(_hr_or_solvers(user)) is False
    for operation in [permissions(None, user), record(None, user, 'forged'), _authorize_applicant_export(None, user)]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(operation)
        assert error.value.status_code == 403

@pytest.mark.parametrize('role', ['hr_admin', 'it_admin'])
def test_explicit_admins_have_narrow_intake_access(role):
    user = {'role': role}
    require_intake_admin(user)
    assert asyncio.run(_hr_or_solvers(user)) is True
    asyncio.run(permissions(None, user, write=True))
    asyncio.run(_authorize_applicant_export(None, user))

@pytest.mark.parametrize('role', ['hr_manager', 'general_manager', 'executive'])
def test_generic_recruitment_scope_cannot_be_overridden_to_expose_solvers(role):
    scope = asyncio.run(recruitment_scope(None, {'role': role, 'tenant_id': 'solvit'}))
    scope['candidate_type'] = 'Solver'
    assert {'candidate_type': {'$ne': 'Solver'}} in scope['$and']

@pytest.mark.parametrize('name,args', [
    ('list_requisitions', (None,)),
    ('download_eligible_cv', ('forged', None)),
    ('download_ineligible_cv', ('forged', None)),
    ('requisition_qr', ('forged', None)),
])
def test_private_routes_reject_managers_before_reading_records(name, args):
    from unittest.mock import AsyncMock, patch
    from routes import solver_intake
    with patch.object(solver_intake, 'get_current_user', new=AsyncMock(return_value={'role': 'line_manager'})):
        with pytest.raises(HTTPException) as error:
            asyncio.run(getattr(solver_intake, name)(*args))
    assert error.value.status_code == 403
