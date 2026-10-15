"""Isolated regression tests: no database connection or record writes."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes import employees

@pytest.mark.parametrize('manager_id,canonical,legacy,expected', [
    ('582b6176-manager', {'full_name': 'Martin Karanja Kiarie'}, None, 'Martin Karanja Kiarie'),
    ('507f1f77bcf86cd799439011', None, {'full_name': 'Legacy Manager'}, 'Legacy Manager'),
    ('invalid', None, None, None),
    (None, None, None, None),
])
def test_manager_lookup(manager_id, canonical, legacy, expected):
    manager = canonical or legacy
    with patch.object(employees, 'find_employee', AsyncMock(return_value=manager)) as lookup:
        result = asyncio.run(employees._line_manager_name(None, manager_id))
    assert result == expected
    if manager_id:
        lookup.assert_awaited_once_with(None, manager_id, "solvit")
    else:
        lookup.assert_not_called()

@pytest.mark.parametrize('manager', [{'full_name': 'Martin Karanja Kiarie'}, None])
def test_profile_retains_relationship_department_and_timeline(manager):
    employee = {'_id': ObjectId(), 'id': 'jessica', 'full_name': 'Jessica Mining',
                'department': 'HR & People', 'line_manager_id': '582b6176-manager',
                'start_date': '2025-01-01', 'work_email': 'jessica@example.test'}
    db = MagicMock()
    db.employees.find_one = AsyncMock(side_effect=[employee.copy(), manager])
    db.idps.find_one = AsyncMock(return_value=None)
    for name in ['performance_reviews', 'leave_requests', 'recognitions', 'training_requests', 'disciplinary_cases', 'notifications']:
        getattr(db, name).find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    with patch.object(employees, 'authorize_employee', AsyncMock(return_value=employee.copy())), patch.object(employees, 'find_employee', AsyncMock(side_effect=[employee.copy(), manager])), patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value={'id': 'hr', 'role': 'hr_admin'})):
        profile = asyncio.run(employees.get_employee_profile('jessica', None))
    assert profile['employee']['line_manager_name'] == (manager['full_name'] if manager else None)
    assert profile['employee']['line_manager_id'] == employee['line_manager_id']
    assert profile['employee']['department'] == 'HR & People'
    assert profile['timeline'][0]['type'] == 'joined'
    db.employees.update_one.assert_not_called()
    db.employees.insert_one.assert_not_called()


def test_unchanged_department_is_not_written_by_update():
    db = MagicMock()
    db.employees.find_one_and_update = AsyncMock(return_value={
        '_id': ObjectId(), 'id': 'jessica', 'department': 'HR & People',
        'line_manager_id': '582b6176-manager',
    })
    db.audit_log.insert_one = AsyncMock()
    db.integrity_locks.insert_one = AsyncMock()
    db.integrity_locks.delete_one = AsyncMock()
    with patch.object(employees, 'find_employee', AsyncMock(return_value={'_id': ObjectId(), 'id': 'jessica', 'department': 'HR & People'})), patch.object(employees, 'get_db', return_value=db), patch.object(employees, 'get_current_user', AsyncMock(return_value={'id': 'hr', 'role': 'hr_admin'})):
        result = asyncio.run(employees.update_employee('jessica', employees.EmployeeUpdate(full_name='Jessica Mining'), None))
    changes = db.employees.find_one_and_update.call_args.args[1]['$set']
    assert 'department' not in changes
    assert 'line_manager_id' not in changes
    assert result['department'] == 'HR & People'
