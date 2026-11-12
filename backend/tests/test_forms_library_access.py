import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import forms
from utils.form_access import can_view_form


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize('role,targets', [
    ('employee', {'employee'}), ('line_manager', {'employee', 'line_manager'}),
    ('solver', {'solver'}), ('it_admin', {'employee'}), ('finance', {'employee'}),
    ('general_manager', {'employee'}), ('hr_admin', None), ('hr_manager', None),
])
def test_catalog_returns_only_permitted_categories_and_counts(role, targets):
    user = {'id': 'account', 'role': role}
    with patch.object(forms, 'get_current_user', AsyncMock(return_value=user)):
        result = run(forms.list_forms(object()))
    expected = {key for key, schema in forms.FORM_SCHEMAS.items()
                if targets is None or schema.get('target_role') in targets}
    assert {row['id'] for row in result} == expected
    assert all(can_view_form(user, row) for row in result)


@pytest.mark.parametrize('role,target', [('employee', 'solver'), ('employee', 'line_manager'),
    ('employee', 'hr_admin'), ('employee', 'hr_manager'), ('line_manager', 'hr_admin'),
    ('line_manager', 'solver'), ('solver', 'employee'), ('it_admin', 'line_manager')])
def test_direct_schema_and_submission_requests_cannot_bypass_library(role, target):
    form_id = next(key for key, schema in forms.FORM_SCHEMAS.items()
                   if schema.get('target_role') == target and key != 'form-06')
    request = SimpleNamespace(json=AsyncMock(return_value={'data': {}}))
    with patch.object(forms, 'get_current_user', AsyncMock(return_value={'role': role})), patch.object(forms, 'get_db', return_value=object()):
        for action in (forms.get_form_schema, forms.start_form_submission, forms.submit_form):
            with pytest.raises(HTTPException) as error:
                run(action(form_id, request))
            assert error.value.status_code == 403


@pytest.mark.parametrize('role', ['hr_admin', 'hr_manager'])
def test_hr_can_inspect_every_schema(role):
    with patch.object(forms, 'get_current_user', AsyncMock(return_value={'role': role})):
        for form_id in forms.FORM_SCHEMAS:
            schema = run(forms.get_form_schema(form_id, object()))
            assert schema['id'] == form_id
