import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from scripts.provision_requested_accounts import prepare
from utils.employee_accounts import provision_employee_account
from .integrity_fakes import Database, employee


def test_requested_accounts_use_saved_details_and_reject_ambiguity():
    staff = [employee('teresiah', 'twangui@solvit.co.ke', full_name='Teresiah Example'),
             employee('mary', 'mmuriuki@solvit.co.ke', full_name='Mary Example')]
    db = Database(staff)
    assert asyncio.run(prepare(db, {'tenant_id': 'solvit'})) == staff
    db.employees.docs.append(employee('mary-two', 'mmuriuki@solvit.co.ke', full_name='Mary Other'))
    with pytest.raises(ValueError, match='Mary .*expected exactly one'):
        asyncio.run(prepare(db, {'tenant_id': 'solvit'}))
    assert db.users.writes == 0


def test_kpi_failure_does_not_fail_account_creation_or_block_next_account():
    db = Database([employee(), employee('second', 'second@example.com')])
    with patch('utils.performance_v3.auto_assignment', new=AsyncMock(side_effect=RuntimeError('KPI failure'))):
        first = asyncio.run(provision_employee_account(db, 'staff', 'Synthetic-setup-2026', {'id': 'admin'}))
        second = asyncio.run(provision_employee_account(db, 'second', 'Synthetic-setup-2026', {'id': 'admin'}))
        retry = asyncio.run(provision_employee_account(db, 'staff', None, {'id': 'admin'}))
    assert first['created'] and second['created'] and not retry['created']
    assert first['warning'] and first['id'] == retry['id']
    assert len(db.users.docs) == 2 and not db.integrity_locks.docs
    assert all(u['must_change_password'] and u['role'] == 'employee' for u in db.users.docs)

