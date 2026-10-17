"""Synthetic-only lifecycle security, idempotency and recovery regressions."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from routes import lifecycle, onboarding
from utils import lifecycle_workflows as service
from .test_profile_self_service import fixture as profile_fixture
from .integrity_fakes import Collection


def run(coro): return asyncio.run(coro)


def fixture():
    db, users = profile_fixture()
    for name in ('tasks', 'onboarding_tasks', 'user_session_invalidations'):
        setattr(db, name, Collection())
    db.employees.docs[0]['lifecycle_state'] = 'Onboarding'
    return db, users


def initiate(db, user, **values):
    with patch.object(lifecycle, 'get_db', return_value=db), patch.object(lifecycle, 'get_current_user', return_value=user):
        return run(lifecycle.initiate(lifecycle.Initiate(employee_id='staff', **values), SimpleNamespace()))


def test_onboarding_initiation_is_explicit_idempotent_and_keeps_identity():
    db, users = fixture(); before = deepcopy(db.employees.docs)
    initiate(db, users['hr'], kind='onboarding')
    initiate(db, users['hr'], kind='onboarding')
    assert len(db.onboarding_tasks.docs) == len(onboarding.FTE_ONBOARDING_TASKS)
    assert db.employees.docs == before and db.users.writes == 0
    by_key = {row['task_key']: row for row in db.onboarding_tasks.docs}
    assert by_key['C30']['due_date'] == '2020-01-31'
    assert by_key['T19']['due_date'] == '2020-01-03'
    assert by_key['T02']['assigned_role'] == 'it_admin'
    assert len(db.notifications.docs) == 6
    assert sum(row['event'] == 'onboarding.initiated' for row in db.audit_logs.docs) == 1


@pytest.mark.parametrize('actor', ['staff', 'other', 'manager', 'finance'])
def test_only_hr_initiates(actor):
    db, users = fixture()
    with pytest.raises(HTTPException): initiate(db, users[actor], kind='onboarding')
    assert not db.onboarding_tasks.docs


def test_get_never_creates_tasks():
    db, users = fixture()
    with patch.object(onboarding, 'get_db', return_value=db), patch.object(onboarding, 'get_current_user', return_value=users['staff']):
        assert run(onboarding.get_employee_onboarding('staff', SimpleNamespace())) == []
    assert not db.onboarding_tasks.docs


@pytest.mark.parametrize('role,actor,allowed', [('employee','staff',True), ('employee','other',False), ('line_manager','staff',False), ('line_manager','manager',True), ('finance','staff',False), ('finance','finance',True), ('it_admin','manager',False)])
def test_responsibility_checks(role, actor, allowed):
    db, users = fixture(); task = {'entity_id':'staff','assigned_role':role}
    if allowed: run(service.task_access(db, users[actor], task, write=True))
    else:
        with pytest.raises(HTTPException): run(service.task_access(db, users[actor], task, write=True))


def test_checklist_completion_audited_idempotent_and_no_notes_in_projection():
    db, users = fixture(); initiate(db, users['hr'], kind='onboarding')
    task = next(t for t in db.onboarding_tasks.docs if t['task_key'] == 'T19')
    result = run(service.update_checklist(db, users['staff'], db.onboarding_tasks, task, 'Completed', 'private'))
    assert result['status'] == 'Completed' and 'notes' not in result
    count = len(db.audit_logs.docs)
    run(service.update_checklist(db, users['staff'], db.onboarding_tasks, task, 'Completed'))
    assert len(db.audit_logs.docs) == count
    with pytest.raises(HTTPException): run(service.update_checklist(db, users['staff'], db.onboarding_tasks, task, 'Pending'))


def test_exit_initiation_requires_authorization_and_does_not_disable_account():
    db, users = fixture()
    with pytest.raises(HTTPException): initiate(db, users['hr'], kind='offboarding')
    initiate(db, users['hr'], kind='offboarding', last_working_day='2020-02-01', authorization_reference='synthetic-approved')
    count = len(db.tasks.docs)
    initiate(db, users['hr'], kind='offboarding', last_working_day='2020-02-01', authorization_reference='synthetic-approved')
    assert count == 31 and len(db.tasks.docs) == count
    assert not db.users.writes and db.employees.docs[0]['lifecycle_state'] == 'Exiting'


def ready_exit(db, users, last_day='2020-02-01'):
    initiate(db, users['hr'], kind='offboarding', last_working_day=last_day, authorization_reference='synthetic-approved')
    for task in db.tasks.docs: task['status'] = 'Completed'
    return db.employees.docs[0]


@pytest.mark.parametrize('scenario', ['early', 'incomplete', 'duplicate_account', 'self', 'direct_reports'])
def test_exit_guards(scenario):
    db, users = fixture(); employee = ready_exit(db, users, '2099-01-01' if scenario == 'early' else '2020-02-01')
    if scenario == 'incomplete': db.tasks.docs[0]['status'] = 'Pending'
    if scenario == 'duplicate_account': db.users.docs.append({**db.users.docs[1], 'employee_id':'staff'})
    if scenario == 'direct_reports': db.employees.docs[1]['line_manager_id'] = 'staff'
    actor = {**users['hr'], 'employee_id':'staff'} if scenario == 'self' else users['hr']
    with pytest.raises(HTTPException): run(service.finalize_exit(db, actor, employee))
    assert db.users.writes == 0 and employee['lifecycle_state'] == 'Exiting'


def test_exit_revokes_sessions_archives_without_deleting_and_audits():
    db, users = fixture(); employee = ready_exit(db, users); before = len(db.employees.docs)
    run(service.finalize_exit(db, users['hr'], employee))
    assert db.users.docs[0]['is_active'] is False
    assert employee['lifecycle_state'] == 'Exited' and len(db.employees.docs) == before
    assert db.user_session_invalidations.docs[0]['user_id'] == str(db.users.docs[0]['_id'])
    assert db.audit_logs.docs[-1]['event'] == 'offboarding.completed'


def test_checklist_list_isolates_employee_and_redacts_notes():
    db, users = fixture(); initiate(db, users['hr'], kind='onboarding')
    db.onboarding_tasks.docs[0]['notes'] = 'confidential'
    with patch.object(lifecycle, 'get_db', return_value=db), patch.object(lifecycle, 'get_current_user', return_value=users['other']):
        assert run(lifecycle.checklists(SimpleNamespace())) == []
    with patch.object(lifecycle, 'get_db', return_value=db), patch.object(lifecycle, 'get_current_user', return_value=users['staff']):
        rows = run(lifecycle.checklists(SimpleNamespace()))
    assert len(rows) == 1 and 'confidential' not in str(rows)


def test_legacy_reference_resolves_without_relinking():
    db, users = fixture(); task = {'entity_id':str(db.employees.docs[0]['_id']), 'assigned_role':'employee'}
    assert run(service.task_access(db, users['staff'], task, write=True))['id'] == 'staff'


def test_partial_legacy_checklist_can_resume_without_duplicate_keys():
    db, users = fixture(); initiate(db, users['hr'], kind='onboarding')
    old = db.onboarding_tasks.docs[0]
    old['entity_id'] = str(db.employees.docs[0]['_id'])
    old['status'] = 'Completed'
    db.onboarding_tasks.docs[:] = [old]
    initiate(db, users['hr'], kind='onboarding')
    assert len(db.onboarding_tasks.docs) == len(onboarding.FTE_ONBOARDING_TASKS)
    assert db.onboarding_tasks.docs[0]['status'] == 'Completed'


def test_document_verification_requires_same_employee_and_hr():
    db, users = fixture(); initiate(db, users['hr'], kind='onboarding')
    task = next(t for t in db.onboarding_tasks.docs if t['task_key'] == 'DOCS')
    with pytest.raises(HTTPException): run(service.update_checklist(db, users['hr'], db.onboarding_tasks, task, 'Completed'))
    run(db.employee_documents.insert_one({'id':'wrong', 'tenant_id':'solvit', 'employee_id':'other'}))
    with pytest.raises(HTTPException): run(service.update_checklist(db, users['hr'], db.onboarding_tasks, task, 'Completed', document_id='wrong'))
    run(db.employee_documents.insert_one({'id':'own', 'tenant_id':'solvit', 'employee_id':'staff', 'publication_state':'Ready'}))
    result = run(service.update_checklist(db, users['hr'], db.onboarding_tasks, task, 'Completed', document_id='own'))
    assert result['document_id'] == 'own'


def test_scheduler_requires_explicit_active_hr_authorization_and_honors_cutoff():
    db, users = fixture(); employee = ready_exit(db, users)
    run(service.process_approved_exits(db)); assert db.users.writes == 0
    employee['offboarding_deactivation_approved_by'] = str(users['staff']['_id'])
    run(service.process_approved_exits(db)); assert db.users.writes == 0
    employee['offboarding_deactivation_approved_by'] = str(users['hr']['_id'])
    employee['last_working_day'] = '2099-01-01'
    run(service.process_approved_exits(db)); assert db.users.writes == 0
    employee['last_working_day'] = '2020-01-01'
    run(service.process_approved_exits(db))
    assert db.users.docs[0]['is_active'] is False


def test_clearance_form_cannot_bypass_timed_approval_and_automation_is_idempotent():
    from automation.engine import AutomationEngine, FORM_OUTCOME_HANDLERS
    assert FORM_OUTCOME_HANDLERS['clearance.signed_off'].get('new_state') is None
    db, users = fixture(); engine = AutomationEngine(); engine.db = db
    run(engine._create_exit_tasks('staff')); run(engine._create_exit_tasks(str(db.employees.docs[0]['_id'])))
    assert len(db.tasks.docs) == 31


def test_existing_lifecycle_routes_cannot_bypass_approved_exit():
    from utils.employee_integrity import change_employee_state
    db, users = fixture(); ready_exit(db, users)
    with pytest.raises(HTTPException): run(change_employee_state(db, 'staff', 'Exited'))
    assert db.employees.docs[0]['lifecycle_state'] == 'Exiting'


def test_authorized_scheduled_revocation_does_not_wait_for_unfinished_clearance():
    db, users = fixture(); employee = ready_exit(db, users)
    db.tasks.docs[0]['status'] = 'Pending'
    employee['offboarding_deactivation_approved_by'] = str(users['hr']['_id'])
    run(service.process_approved_exits(db))
    assert db.users.docs[0]['is_active'] is False
    assert employee['lifecycle_state'] == 'Exiting' and employee.get('offboarding_access_revoked_at')
    assert not employee.get('offboarding_completed_at')
    assert any(row['event'] == 'offboarding.access.revoked' for row in db.audit_logs.docs)
