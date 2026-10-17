import asyncio
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import NetworkTimeout

from routes import leave, lnd, performance, projects, forms, onboarding, automation_routes, employees, settings
from utils.employee_integrity import integrity_write, insert_employee
from utils.task_access import authorize_task
from utils.access_matrix import CUSTOM_ROLE_DEFINITIONS
from .integrity_fakes import Database, Collection, employee


def run(call): return asyncio.run(call)


def fixture():
    boss = employee("boss", "boss@example.com")
    staff = employee(line_manager_id="boss")
    other = employee("other", "other@example.com", line_manager_id="other-boss")
    other_boss = employee("other-boss", "other-boss@example.com")
    db = Database([boss, staff, other, other_boss])
    for name in ["leave_requests", "training_requests", "idps", "skills_matrix", "notifications", "performance_reviews", "projects", "form_submissions", "onboarding_tasks", "tasks", "solvers"]:
        setattr(db, name, Collection())
    return db


def actor(role="employee", identity="staff"):
    return {"id": "user-" + identity, "email": identity + "@example.com", "role": role,
            "employee_id": identity, "tenant_id": "solvit"}


@contextmanager
def as_user(module, db, user):
    with patch.object(module, "get_db", return_value=db), patch.object(module, "get_current_user", AsyncMock(return_value=user)), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        yield


def request(body): return SimpleNamespace(json=AsyncMock(return_value=body))


def test_board_list_preserves_existing_authorized_directory():
    db = fixture()
    db.employees.docs[0]["board_only"] = True
    db.employees.docs[0]["is_md"] = True
    with as_user(employees, db, actor("board")):
        rows = run(employees.list_employees(None))
    assert {row["id"] for row in rows} == {"boss", "staff", "other", "other-boss"}


@pytest.mark.parametrize("role", ["finance", "executive", "solver", "custom_staff"])
def test_employee_detail_rejects_foreign_subject_for_non_hr_roles(role):
    db = fixture()
    with patch.dict(CUSTOM_ROLE_DEFINITIONS, {"custom_staff": {"inherits_from": "employee"}}):
        with as_user(employees, db, actor(role)):
            with pytest.raises(HTTPException) as error:
                run(employees.get_employee("other", None))
    assert error.value.status_code == 403


def test_manager_cannot_read_foreign_board_led_panel():
    db = fixture()
    db.employees.docs[2]["is_md"] = True
    with as_user(performance, db, actor("line_manager", "boss")):
        with pytest.raises(HTTPException) as error:
            run(performance.get_review_panel("other", None))
    assert error.value.status_code == 403


def test_settings_masks_entire_secret_and_preserves_masked_roundtrip():
    db = fixture()
    db.platform_settings = Collection([{"_id": ObjectId(), "tenant_id": "solvit",
                                       "email_api_key": "synthetic-secret-key-for-tests"}])
    with as_user(settings, db, actor("hr_admin")):
        fetched = run(settings.get_settings(None))
        assert fetched["email_api_key"] == "***"
        result = run(settings.update_settings(settings.PlatformSettings(email_api_key="***", currency="KES"), None))
        assert result["email_api_key"] == "***"
    assert db.platform_settings.docs[0]["email_api_key"] == "synthetic-secret-key-for-tests"


@pytest.mark.parametrize("role", ["employee", "finance", "executive", "custom_staff"])
@pytest.mark.parametrize("kind", ["leave", "training", "idp", "skills"])
def test_forged_employee_create_or_modify_has_no_writes(role, kind):
    db = fixture()
    with patch.dict(CUSTOM_ROLE_DEFINITIONS, {"custom_staff": {"inherits_from": "employee"}}):
        module = leave if kind == "leave" else lnd
        with as_user(module, db, actor(role)):
            with pytest.raises(HTTPException) as error:
                if kind == "leave":
                    run(leave.create_leave_request(leave.LeaveRequest(employee_id="other", line_manager_id="other-boss", leave_type="Annual", start_date="2026-10-20", end_date="2026-10-21"), None))
                elif kind == "training":
                    run(lnd.create_training_request(lnd.TrainingRequest(employee_id="other", training_name="Synthetic", provider="Internal", delivery_method="Internal", business_justification="Synthetic"), None))
                elif kind == "idp": run(lnd.create_or_update_idp(lnd.IDPCreate(employee_id="other"), None))
                else: run(lnd.update_skills_matrix("other", request({"skills": []})))
        assert error.value.status_code == 403
    assert all(getattr(db, name).writes == 0 for name in ["leave_requests", "training_requests", "idps", "skills_matrix", "notifications"])


@pytest.mark.parametrize("kind", ["leave_balance", "rollover", "idp", "skills", "performance_history", "employee_profile"])
def test_forged_employee_read_is_denied(kind):
    db = fixture()
    module = leave if kind in ("leave_balance", "rollover") else lnd if kind in ("idp", "skills") else performance if kind == "performance_history" else employees
    with as_user(module, db, actor()):
        with pytest.raises(HTTPException) as error:
            operation = {"leave_balance": lambda: leave.get_leave_balances("other", None), "rollover": lambda: leave.get_rollover_balance("other", None), "idp": lambda: lnd.get_idp("other", None), "skills": lambda: lnd.get_skills_matrix("other", None), "performance_history": lambda: performance.get_review_history("other", None), "employee_profile": lambda: employees.get_employee_profile("other", None)}[kind]
            run(operation())
    assert error.value.status_code == 403


def test_forged_manager_rejected_and_saved_manager_used():
    db = fixture()
    from datetime import timedelta
    from utils.leave_policy import today
    db.employees.docs[1].update(start_date="2020-01-01", department="Operations")
    start = today() + timedelta(days=14)
    data = {"employee_id": "staff", "leave_type": "Annual", "start_date": start.isoformat(), "end_date": (start + timedelta(days=1)).isoformat(), "notes": "Cover responsibilities and deadlines", "handover_contact_id": "other"}
    with as_user(leave, db, actor()):
        with pytest.raises(HTTPException):
            run(leave.create_leave_request(leave.LeaveRequest(**data, line_manager_id="other-boss"), None))
        result = run(leave.create_leave_request(leave.LeaveRequest(**data), None))
    assert result["employee_id"] == "staff"
    assert result["line_manager_id"] == "boss"
    assert len(db.leave_requests.docs) == 1


@pytest.mark.parametrize("module,name,operation", [(leave, "leave_requests", leave.leave_decision), (lnd, "training_requests", lnd.training_decision)])
@pytest.mark.parametrize("role,identity,target", [("employee", "staff", "other"), ("employee", "staff", "staff"), ("line_manager", "boss", "other"), ("line_manager", "boss", "boss")])
def test_unauthorized_decision_and_self_approval_have_no_writes(module, name, operation, role, identity, target):
    db = fixture()
    getattr(db, name).docs = [{"_id": ObjectId(), "id": "record", "tenant_id": "solvit", "employee_id": target, "status": "Pending_Manager"}]
    with as_user(module, db, actor(role, identity)):
        with pytest.raises(HTTPException) as error: run(operation("record", request({"decision": "Approve"})))
    assert error.value.status_code == 403
    assert getattr(db, name).writes == 0


@pytest.mark.parametrize("role", ["line_manager", "hr_admin", "hr_manager"])
def test_authorized_training_decision_preserves_hr_approval_gate(role):
    db = fixture()
    db.training_requests.docs = [{"_id": ObjectId(), "id": "record", "tenant_id": "solvit", "employee_id": "staff", "cost_kes": 6000, "duration_days": 1, "requires_hr_approval": True, "line_manager_id":"boss", "status":"Pending_Manager_Approval" if role == "line_manager" else "Pending_HR_Approval", "manager_decision":None if role == "line_manager" else "Approve"}]
    with as_user(lnd, db, actor(role, "boss")):
        result = run(lnd.training_decision("record", request({"decision": "Approve", "requires_hr_approval": False})))
    assert result["status"] == ("Pending_HR_Approval" if role == "line_manager" else "Approved")


def test_bulk_training_checks_entire_batch_before_writing():
    db = fixture()
    with as_user(lnd, db, actor("line_manager", "boss")):
        with pytest.raises(HTTPException):
            run(lnd.bulk_assign_training(request({"employee_ids": ["staff", "other"], "training_name": "Synthetic"})))
    assert db.training_requests.writes == 0


@pytest.mark.parametrize("module,name,operation", [(leave, "leave_requests", leave.list_leave_requests), (lnd, "training_requests", lnd.list_training_requests)])
def test_lists_are_scoped_for_employee_and_manager(module, name, operation):
    db = fixture()
    getattr(db, name).docs = [{"_id": ObjectId(), "id": key, "tenant_id": "solvit", "employee_id": key} for key in ("staff", "other", "boss")]
    with as_user(module, db, actor()):
        rows = run(operation(None))
        assert [r["employee_id"] for r in rows] == ["staff"]
        with pytest.raises(HTTPException): run(operation(None, employee_id="other"))
    with as_user(module, db, actor("line_manager", "boss")):
        assert {r["employee_id"] for r in run(operation(None))} == {"boss", "staff"}


def test_form_employee_role_does_not_authorize_another_employees_signature():
    db = fixture()
    db.form_submissions.docs = [{"_id": ObjectId(), "id": "form", "tenant_id": "solvit", "status": "InProgress", "subject_employee_id": "other", "next_required_role": "employee", "data": {}}]
    with as_user(forms, db, actor()):
        with pytest.raises(HTTPException): run(forms.sign_form_step("form", request({"signature": "Synthetic"})))
    assert db.form_submissions.writes == 0


def test_form_forged_nested_subject_cannot_trigger_other_employee_workflow():
    db = fixture()
    with as_user(forms, db, actor()):
        with pytest.raises(HTTPException):
            run(forms.submit_form("form-31", request({"employee_id": "staff", "data": {"employee_id": "other"}, "signatures": {"employee": "Synthetic"}})))
    assert db.form_submissions.writes == 0


def test_form_solver_id_cannot_bypass_subject_authorization():
    db = fixture()
    db.solvers.docs = [{"_id": ObjectId(), "id": "foreign-solver", "tenant_id": "solvit", "email": "foreign@example.com"}]
    with as_user(forms, db, actor()):
        with pytest.raises(HTTPException) as error:
            run(forms.submit_form("form-03", request({"solver_id": "foreign-solver", "data": {}})))
    assert error.value.status_code == 403
    assert db.form_submissions.writes == 0


def test_signing_rejects_forged_nested_manager_without_employee_field():
    db = fixture()
    db.form_submissions.docs = [{"_id": ObjectId(), "id": "form", "form_id": "form-13", "tenant_id": "solvit", "status": "InProgress", "subject_employee_id": "staff", "next_required_role": "employee", "data": {}}]
    with as_user(forms, db, actor()):
        with pytest.raises(HTTPException) as error:
            run(forms.sign_form_step("form", request({"signature": "Synthetic", "data": {"line_manager_id": "other-boss"}})))
    assert error.value.status_code == 403
    assert db.form_submissions.writes == 0


def test_signature_compare_and_set_rejects_race_without_outcome():
    db = fixture()
    db.form_submissions.docs = [{"_id": ObjectId(), "id": "form", "form_id": "form-31", "tenant_id": "solvit", "status": "InProgress", "subject_employee_id": "staff", "next_required_role": "employee", "current_step_index": 0, "completing_users_sequence": ["employee"], "required_signatures": ["employee"], "outcome_rule": "resignation.submitted", "data": {}}]
    with as_user(forms, db, actor()), patch.object(db.form_submissions, "update_one", AsyncMock(return_value=SimpleNamespace(modified_count=0))), patch("automation.engine.automation_engine.fire_event", AsyncMock()) as outcome:
        with pytest.raises(HTTPException) as error:
            run(forms.sign_form_step("form", request({"signature": "Synthetic"})))
        outcome.assert_not_awaited()
    assert error.value.status_code == 409


def test_shared_employee_creation_rejects_email_of_another_linked_account():
    db = fixture()
    db.users.docs = [{"_id": ObjectId(), "email": " NEW@EXAMPLE.COM ", "tenant_id": "solvit", "employee_id": "other"}]
    before = len(db.employees.docs)
    with pytest.raises(HTTPException) as error:
        run(insert_employee(db, employee("new", "new@example.com", line_manager_id="boss")))
    assert error.value.status_code == 409
    assert len(db.employees.docs) == before


def test_assignee_cannot_modify_task_with_unresolved_employee_subject():
    db = fixture()
    with pytest.raises(HTTPException) as error:
        run(authorize_task(db, actor(), {"employee_id": "missing", "assigned_to": "user-staff"}, write=True))
    assert error.value.status_code == 409


@pytest.mark.parametrize("module,name,operation", [(projects, "projects", lambda: projects.update_project("record", request({"status": "Completed"}))), (onboarding, "onboarding_tasks", lambda: onboarding.update_task("record", onboarding.TaskUpdate(status="Completed"), None)), (automation_routes, "tasks", lambda: automation_routes.update_task("record", request({"status": "Completed"})))])
def test_forged_record_id_cannot_modify_other_employee(module, name, operation):
    db = fixture()
    getattr(db, name).docs = [{"_id": ObjectId(), "id": "record", "tenant_id": "solvit", "employee_id": "other", "entity_id": "other", "entity_type": "employee", "assigned_to": "user-other"}]
    with as_user(module, db, actor()):
        with pytest.raises(HTTPException): run(operation())
    assert getattr(db, name).writes == 0


@pytest.mark.parametrize("error", [NetworkTimeout("synthetic uncertainty"), asyncio.CancelledError(), RuntimeError("synthetic unknown error")])
def test_uncertain_write_keeps_lock_and_blocks_second_writer(error):
    db = fixture()
    async def interrupted():
        async with integrity_write(db): raise error
    with pytest.raises(type(error)): run(interrupted())
    assert len(db.integrity_locks.docs) == 1
    assert db.integrity_locks.docs[0]["worker_instance"]
    assert db.integrity_locks.docs[0]["process_id"]
    async def second():
        async with integrity_write(db): pass
    with pytest.raises(HTTPException) as failure: run(second())
    assert failure.value.status_code == 409


def test_known_validation_failure_releases_own_lock_only():
    db = fixture()
    async def rejected():
        async with integrity_write(db): raise HTTPException(422, "Synthetic validation")
    with pytest.raises(HTTPException): run(rejected())
    assert not db.integrity_locks.docs


def test_matrix_override_does_not_make_ordinary_employee_a_company_approver():
    from utils.access_matrix import RUNTIME_OVERRIDES
    db = fixture()
    db.leave_requests.docs = [{"_id": ObjectId(), "id": "record", "tenant_id": "solvit", "employee_id": "other"}]
    with patch.dict(RUNTIME_OVERRIDES, {("M18", "employee"): {"level": "Full", "scope": None}}), as_user(leave, db, actor()):
        with pytest.raises(HTTPException): run(leave.leave_decision("record", request({"decision": "Approve"})))
    assert db.leave_requests.writes == 0
