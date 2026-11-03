import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from routes import access
from .test_leave_management import fixture


def change(db, actor, target, role):
    req=SimpleNamespace(json=AsyncMock(return_value={'role':role}))
    with patch.object(access,'get_current_user',AsyncMock(return_value=actor)), patch.object(access,'get_db',return_value=db):
        return asyncio.run(access.update_user_role(str(target['_id']),req))


@pytest.mark.parametrize('role', sorted(access.HR_ASSIGNABLE_ROLES))
def test_hr_assigns_linked_business_roles_with_audit_and_session_invalidation(role):
    db, actors=fixture(); db.employees.docs[0]['employment_type']='Full_Time'; target=db.users.docs[0]
    result=change(db,actors['hr'],target,role)
    assert result['role']==role
    if role!='employee':
        assert target['sessions_invalidated_at']
        assert db.audit_logs.docs[-1]['action']=='user.role_changed'


@pytest.mark.parametrize('role',['it_admin','hr_admin','board','solver','custom_security'])
def test_hr_cannot_grant_protected_roles(role):
    db,actors=fixture()
    with pytest.raises(HTTPException): change(db,actors['hr'],db.users.docs[0],role)
    assert not db.audit_logs.docs


@pytest.mark.parametrize('role',['it_admin','hr_admin','board','custom_security'])
def test_hr_cannot_change_protected_accounts(role):
    db,actors=fixture(); target=db.users.docs[0]; target['role']=role
    with pytest.raises(HTTPException) as exc: change(db,actors['hr'],target,'employee')
    assert exc.value.status_code==403


def test_hr_cannot_change_self_or_unlinked_account():
    db,actors=fixture()
    with pytest.raises(HTTPException): change(db,actors['hr'],db.users.docs[3],'employee')
    target=db.users.docs[0]; target['employee_id']='unknown'
    with pytest.raises(HTTPException): change(db,actors['hr'],target,'line_manager')


def test_hr_listing_excludes_security_accounts_and_other_tenants():
    db,actors=fixture(); db.users.docs[0]['role']='it_admin'; db.users.docs[1]['tenant_id']='other'
    with patch.object(access,'get_current_user',AsyncMock(return_value=actors['hr'])),patch.object(access,'get_db',return_value=db):
        rows=asyncio.run(access.list_users_with_roles(SimpleNamespace()))
    assert str(db.users.docs[0]['_id']) not in {r['id'] for r in rows}
    assert str(db.users.docs[1]['_id']) not in {r['id'] for r in rows}
