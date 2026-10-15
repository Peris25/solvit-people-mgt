"""Personal Staff Home: synthetic records, no external data or writes."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routes import dashboard
from utils.staff_home import staff_home_data
from utils.access_matrix import RUNTIME_OVERRIDES
from .integrity_fakes import Database, Collection, employee, account


def fixture(role="employee", **changes):
    emp = employee(full_name="Synthetic Ada", role_title="IT Lead", department="IT Support", start_date="2025-01-01", **changes)
    owner = account(employee_id="staff", role=role)
    user = {**owner, "id": str(owner["_id"])}
    db = Database([emp, employee("other", email="other@example.com")], [owner])
    for name in ("leave_requests", "tasks", "notifications", "notification_receipts", "form_submissions", "performance_reviews", "recognitions"):
        setattr(db, name, Collection())
    return db, user, emp


def load(db, user, balance=None):
    loader = balance or AsyncMock(return_value={"annual_days_remaining": 5.25, "sick_days_remaining": 30})
    return asyncio.run(staff_home_data(db, user, loader))


@pytest.mark.parametrize("role", ["employee", "line_manager", "finance", "hr_admin", "hr_manager", "executive", "it_admin"])
def test_every_linked_employee_gets_only_their_own_snapshot(role):
    db, user, emp = fixture(role)
    for field in ("medical_notes", "bank_account", "current_salary_kes", "password_hash"):
        emp[field] = "must-not-be-exposed"
    db.employees.docs[0] = deepcopy(emp)
    db.leave_requests = Collection([
        {"id": "own", "employee_id": "staff", "status": "Pending_Manager", "tenant_id": "solvit", "leave_type": "Annual", "reason": "private", "medical_certificate": "private"},
        {"id": "other", "employee_id": "other", "status": "Pending_Manager", "tenant_id": "solvit"},
        {"id": "foreign", "employee_id": "staff", "status": "Pending_Manager", "tenant_id": "foreign"},
        {"id": "done", "employee_id": "staff", "status": "Approved", "tenant_id": "solvit"},
    ])
    before = deepcopy(db.employees.docs)
    data = load(db, user)
    assert data["employee"] == {"id": "staff", "full_name": "Synthetic Ada", "role_title": "IT Lead", "department": "IT Support"}
    assert [row["id"] for row in data["pending_leave"]] == ["own"]
    assert "reason" not in data["pending_leave"][0]
    assert db.employees.docs == before
    assert all(getattr(db, name).writes == 0 for name in ("employees", "users", "tasks", "notifications", "leave_requests"))


@pytest.mark.parametrize("reference", ["canonical", "storage", "native"])
def test_legacy_employee_and_linked_record_aliases(reference):
    db, user, emp = fixture()
    ref = "staff" if reference == "canonical" else str(emp["_id"]) if reference == "storage" else emp["_id"]
    db.leave_requests.docs.append({"id": "alias", "employee_id": ref, "tenant_id": "solvit", "status": "Pending_HR"})
    assert load(db, user)["pending_leave"][0]["id"] == "alias"


@pytest.mark.parametrize("start", [None, "invalid", "2999-01-01"])
def test_missing_invalid_or_future_start_never_fabricates_leave_balance(start):
    db, user, _ = fixture()
    db.employees.docs[0]["start_date"] = start
    loader = AsyncMock()
    data = load(db, user, loader)
    assert data["leave_balance"] is None and data["pending_leave"] == []
    loader.assert_not_awaited()


def test_empty_data_has_real_empty_states_and_existing_balance_is_reused():
    db, user, _ = fixture()
    loader = AsyncMock(return_value={"annual_days_remaining": 0, "sick_days_remaining": 0, "unrelated": "private"})
    data = load(db, user, loader)
    loader.assert_awaited_once_with("staff")
    assert data["leave_balance"] == {"annual_days_remaining": 0, "sick_days_remaining": 0}
    assert data["tasks"] == data["notifications"] == data["pending_leave"] == []
    assert data["unread_notifications"] == 0
    assert "announcements" not in data


def test_tasks_notifications_reviews_and_recognition_are_own_and_redacted():
    db, user, _ = fixture("hr_admin")
    db.tasks = Collection([
        {"id": "own", "tenant_id": "solvit", "status": "Pending", "assigned_to": user["id"], "employee_id": "staff", "title": "Own action", "notes": "private"},
        {"id": "someone", "tenant_id": "solvit", "status": "Pending", "assigned_to": user["id"], "employee_id": "other", "title": "Other private"},
        {"id": "done", "tenant_id": "solvit", "status": "Completed", "assigned_to": user["id"]},
        {"id": "other-assignee", "tenant_id": "solvit", "status": "Pending", "employee_id": "staff", "assigned_role": "hr_admin", "assigned_to": "different-account"},
    ])
    db.form_submissions = Collection([
        {"id": "own-form", "tenant_id": "solvit", "status": "InProgress", "subject_employee_id": "staff", "next_required_role": "employee", "form_title": "Own form", "data": {"private": "value"}},
        {"id": "other-form", "tenant_id": "solvit", "status": "InProgress", "subject_employee_id": "other", "next_required_role": "hr_admin"},
    ])
    db.notifications = Collection([
        {"id": "own-notice", "tenant_id": "solvit", "recipient_id": user["id"], "title": "Own update", "data": {"employee_id": "staff"}},
        {"id": "other-notice", "tenant_id": "solvit", "recipient_role": "hr_admin", "title": "Other private", "data": {"employee_id": "other"}},
        {"id": "foreign", "tenant_id": "foreign", "recipient_id": user["id"]},
        {"id": "forged", "tenant_id": "solvit", "recipient_role": "hr_admin", "recipient_id": "other-user"},
        {"id": "read", "tenant_id": "solvit", "user_id": user["id"], "body": "Read update", "read_at": "2026-01-01"},
    ])
    db.performance_reviews = Collection([{"id": "review", "tenant_id": "solvit", "employee_id": "staff", "overall_score": 1.8, "manager_notes": "private"}, {"id": "other", "tenant_id": "solvit", "employee_id": "other"}])
    db.recognitions = Collection([{"id": "recognition", "tenant_id": "solvit", "nominee_id": "staff", "recognition_type": "Values", "nominator_email": "private"}, {"id": "other", "tenant_id": "solvit", "nominee_id": "other"}])
    data = load(db, user)
    assert {r["id"] for r in data["tasks"]} == {"own", "own-form"}
    assert {r["id"] for r in data["notifications"]} == {"own-notice", "read"}
    assert data["unread_notifications"] == 1
    assert [r["id"] for r in data["reviews"]] == ["review"]
    assert [r["id"] for r in data["recognitions"]] == ["recognition"]
    assert not any(secret in str(data) for secret in ("manager_notes", "nominator_email", "Other private", "private"))


def test_role_assignment_does_not_make_another_employees_form_my_task():
    db, user, _ = fixture()
    db.form_submissions = Collection([{"id": "form", "tenant_id": "solvit", "subject_employee_id": "staff", "status": "InProgress", "next_required_role": "line_manager"}])
    assert load(db, user)["tasks"] == []


@pytest.mark.parametrize("case", ["unlinked", "duplicate", "other_tenant", "conflicting_accounts", "solver"])
def test_invalid_account_identity_fails_closed(case):
    db, user, emp = fixture()
    if case == "unlinked": user["employee_id"] = "missing"
    if case == "duplicate": db.employees.docs.append(employee("staff", email="duplicate@example.com"))
    if case == "other_tenant": user["tenant_id"] = "foreign"
    if case == "conflicting_accounts": db.users.docs.append(account(employee_id="staff"))
    if case == "solver": user["role"] = "solver"
    with pytest.raises(HTTPException): load(db, user)


def test_runtime_revocation_removes_module_data_and_quick_links(monkeypatch):
    db, user, _ = fixture()
    monkeypatch.setitem(RUNTIME_OVERRIDES, ("M18", "employee"), None)
    monkeypatch.setitem(RUNTIME_OVERRIDES, ("M13", "employee"), None)
    loader = AsyncMock()
    data = load(db, user, loader)
    assert data["leave_balance"] is None and data["pending_leave"] is None
    assert not any(link["path"] in ("/leave", "/policies") for link in data["quick_links"])
    loader.assert_not_awaited()


def test_route_ignores_forged_employee_manager_and_role_query_parameters():
    db, user, _ = fixture()
    request = SimpleNamespace(query_params={"employee_id": "other", "manager_id": "other", "role": "hr_admin"})
    with patch.object(dashboard, "get_current_user", AsyncMock(return_value=user)), patch.object(dashboard, "get_db", return_value=db), patch("routes.leave.get_leave_balances", AsyncMock(return_value={})):
        assert asyncio.run(dashboard.staff_home(request))["employee"]["id"] == "staff"
