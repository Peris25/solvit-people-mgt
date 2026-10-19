import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from routes import solvers, data_import
from utils import solver_access as access
from utils.form_access import form_subject
from utils.task_access import authorize_task, authorize_notification
from routes import onboarding, employees as employee_routes
from .integrity_fakes import Database, Collection, employee, account


def solver(key="one", **values):
    return {"_id": ObjectId(), "id": key, "tenant_id": "solvit", "full_name": "Synthetic " + key,
            "email": key + "@example.com", "phone_number": "+254700000001", "lifecycle_state": "Active", **values}


def actor(role="hr_admin", **values):
    return {"id": "synthetic-account", "role": role, "tenant_id": "solvit", **values}


def database(records=(), users=(), employees=()):
    db = Database(employees, users)
    db.solvers = Collection(records)
    db.solver_ratings = Collection()
    return db


def request(body=None):
    return SimpleNamespace(json=AsyncMock(return_value=body or {}))


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("role", ["employee", "finance", "it_admin", "custom_staff"])
def test_detail_cannot_disclose_solver_by_forged_id_to_unauthorized_roles(role):
    db = database([solver()])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor(role))):
        with pytest.raises(HTTPException) as error:
            run(solvers.get_solver("one", request({"role": "hr_admin"})))
    assert error.value.status_code == 403
    assert db.solvers.writes == 0


def test_solver_self_email_alias_is_unique_and_other_solver_is_denied():
    one, two = solver(email=" ONE@example.com "), solver("two", phone_number="0700000002")
    db = database([one, two])
    user = actor("solver", email="one@example.com")
    assert run(access.authorize_solver(db, user, str(one["_id"])))["id"] == "one"
    with pytest.raises(HTTPException) as error:
        run(access.authorize_solver(db, user, "two"))
    assert error.value.status_code == 403


@pytest.mark.parametrize("case", ["missing", "email_duplicate", "canonical_duplicate", "conflicting_accounts", "blank_phone"])
def test_ambiguous_or_unlinked_solver_accounts_fail_closed(case):
    record = solver()
    records, users = [record], []
    user = actor("solver", email="one@example.com")
    if case == "missing": user["solver_id"] = "missing"
    if case == "email_duplicate": records.append(solver("two", email="one@example.com"))
    if case == "canonical_duplicate":
        records.append(solver("one", email="other@example.com")); user["solver_id"] = str(record["_id"])
    if case == "conflicting_accounts":
        user["solver_id"] = "one"; users.append(account(role="solver", solver_id="one"))
    if case == "blank_phone": user = actor("solver", phone_number="")
    with pytest.raises(HTTPException): run(access.own_solver(database(records, users), user))


@pytest.mark.parametrize("reference", ["canonical", "storage", "native", "legacy"])
def test_solver_canonical_and_legacy_lookup_preserves_records(reference):
    record = solver()
    if reference == "legacy": record.pop("id")
    value = record.get("id") if reference == "canonical" else record["_id"] if reference == "native" else str(record["_id"])
    saved = deepcopy(record)
    db = database([record])
    assert run(access.find_solver(db, value, actor()))["_id"] == record["_id"]
    output = access.solver_view(record, actor())
    assert output["id"] == str(record["_id"])
    assert output["canonical_id"] == str(record.get("id") or record["_id"])
    assert record == saved


def test_foreign_tenant_id_cannot_be_read_or_modified_even_by_hr():
    foreign = solver(tenant_id="other")
    db = database([foreign])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        for operation in (solvers.get_solver("one", request()),
                          solvers.update_solver("one", solvers.SolverUpdate(full_name="changed"), request()),
                          solvers.activate_solver("one", request())):
            with pytest.raises(HTTPException) as error: run(operation)
            assert error.value.status_code == 404
    assert db.solvers.writes == 0


@pytest.mark.parametrize("title,allowed", [("Solvers Manager", True), ("Operations Coordinator / Head of Solvers", True),
                                          ("Operations Coordinator", True), ("Technical Services Manager", False), ("", False)])
def test_manager_authority_requires_unique_saved_qualified_role(title, allowed):
    db = database(employees=[employee("manager", role_title=title)])
    user = actor("line_manager", employee_id="manager")
    if allowed: assert run(access.solver_access(db, user, write=True))["scope"] == "solvers_manager"
    else:
        with pytest.raises(HTTPException) as error: run(access.solver_access(db, user, write=True))
        assert error.value.status_code == 403


def test_manager_and_self_output_redact_private_data_while_hr_retains_private_view():
    record = solver(bank_account_number="private-marker", national_id_number="private-marker", kra_pin="private-marker",
                    medical_notes="private-marker", disciplinary_notes="private-marker", notes="private-marker", password_hash="never-publish")
    for role in ("solver", "line_manager"):
        assert "private-marker" not in str(access.solver_view(record, actor(role)))
    assert access.solver_view(record, actor())["bank_account_number"] == "private-marker"
    assert "password_hash" not in access.solver_view(record, actor())


def test_aggregate_executive_sees_counts_only_and_no_individuals():
    db = database([solver(), solver("other", tenant_id="foreign")])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor("executive"))):
        assert run(solvers.list_solvers(request())) == []
        stats = run(solvers.get_solver_stats(request()))
        assert stats["total"] == 1 and stats["can_manage"] is False
        with pytest.raises(HTTPException): run(solvers.get_solver("one", request()))


def test_self_list_and_statistics_exclude_other_records():
    db = database([solver(), solver("two")])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor("solver", email="one@example.com"))):
        assert len(run(solvers.list_solvers(request()))) == 1
        assert run(solvers.get_solver_stats(request()))["total"] == 1


@pytest.mark.parametrize("value", ["0700 000 001", "+254700000001", "254-700-000-001", "700000001", 254700000001, 254700000001.0])
def test_phone_formats_have_one_canonical_identity(value):
    assert access.normalize_phone(value) == "+254700000001"
    with pytest.raises(HTTPException) as error: run(access.unique_phone(database([solver()]), value, actor()))
    assert error.value.status_code == 409


@pytest.mark.parametrize("value", [None, "", "invalid", "++254700000001", "123", True])
def test_invalid_phones_are_rejected(value):
    with pytest.raises(HTTPException) as error: access.normalize_phone(value)
    assert error.value.status_code == 422


def test_unchanged_phone_and_email_formats_are_not_rewritten_and_accounts_are_preserved():
    original = solver(phone_number="0700 000 001", email=" ONE@example.com ")
    db = database([original])
    changes = run(access.solver_identity_write(db, {"phone_number": original["phone_number"], "email": original["email"]}, actor(), original))
    assert changes == {} and db.solvers.writes == db.users.writes == 0


def test_email_change_cannot_orphan_legacy_email_linked_account():
    record = solver()
    user = account(email="one@example.com", role="solver")
    with pytest.raises(HTTPException) as error:
        run(access.solver_identity_write(database([record], [user]), {"email": "new@example.com"}, actor(), record))
    assert error.value.status_code == 409
    user["solver_id"] = "one"
    db = database([record], [user])
    assert run(access.solver_identity_write(db, {"email": "new@example.com"}, actor(), record))["email"] == "new@example.com"
    assert db.users.writes == 0


def test_solver_email_duplicates_are_rejected_on_identity_writes():
    db = database([solver(), solver("two", email=" OTHER@example.com ")])
    with pytest.raises(HTTPException):
        run(access.solver_identity_write(db, {"email": "other@example.com"}, actor(), db.solvers.docs[0]))


def test_only_qualified_manager_operational_writes_and_hr_private_writes_are_permitted():
    db = database([solver()], employees=[employee("manager", role_title="Solvers Manager")])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor("line_manager", employee_id="manager"))):
        with pytest.raises(HTTPException) as error:
            run(solvers.update_solver("one", solvers.SolverUpdate(bank_account_number="forged"), request()))
        assert error.value.status_code == 403
        result = run(solvers.update_solver("one", solvers.SolverUpdate(full_name="Updated synthetic"), request()))
        assert result["full_name"] == "Updated synthetic"
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        assert run(solvers.update_solver("one", solvers.SolverUpdate(bank_account_number="approved-test-only"), request()))["bank_account_number"] == "approved-test-only"


@pytest.mark.parametrize("route", ["create", "update", "activate", "rating"])
def test_ordinary_solver_cannot_forge_writes_for_any_subject(route):
    db = database([solver()]);user = actor("solver", email="one@example.com")
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=user)):
        operation = {"create": lambda: solvers.create_solver(solvers.SolverCreate(full_name="fake", phone_number="0700000002"), request()),
                     "update": lambda: solvers.update_solver("one", solvers.SolverUpdate(lifecycle_state="Active"), request()),
                     "activate": lambda: solvers.activate_solver("one", request()),
                     "rating": lambda: solvers.submit_client_rating("one", request({"accuracy": 100, "timeliness": 100, "overall": 100}))}[route]
        with pytest.raises(HTTPException) as error: run(operation())
        assert error.value.status_code == 403
    assert db.solvers.writes == db.solver_ratings.writes == 0


def test_solver_form_cannot_bypass_duplicate_canonical_identity_using_storage_alias():
    first, second = solver(), solver(email="different@example.com")
    db = database([first, second])
    with pytest.raises(HTTPException) as error:
        run(form_subject(db, actor("solver", email="one@example.com"), {"solver_id": str(second["_id"]), "data": {}}, {"module": "M04"}))
    assert error.value.status_code == 409


def test_import_validation_rejects_existing_and_batch_formatted_phone_duplicates():
    headers = [c[0] for c in data_import.TEMPLATES["solver"]["columns"]]
    def row(phone, code):
        values = {"Full Name": "Synthetic", "Phone Number": phone, "Solver ID": code, "Date of Onboarding": "01/01/2026", "App Status": "Active"}
        return [values.get(h) for h in headers]
    results = run(data_import._validate_rows("solver", [row("0700000001", "code1"), row("0700000002", "code2"), row("+254700000002", "code3")], database([solver()])))
    assert [r["valid"] for r in results] == [False, True, False]


def test_literal_search_cannot_expand_scope_using_regex():
    db = database([solver()])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        assert run(solvers.list_solvers(request(), search=".*")) == []


def test_rating_uses_canonical_id_and_tenant_instead_of_client_supplied_identity():
    record = solver(); db = database([record]); db.solver_ratings.docs = [{"_id": ObjectId(), "id": "old", "tenant_id": "foreign", "solver_id": "one", "voided": False, "overall": 0, "accuracy": 0, "timeliness": 0, "created_at": "2026-01-01"}]
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        run(solvers.submit_client_rating(str(record["_id"]), request({"accuracy": 90, "timeliness": 80, "overall": 85, "tenant_id": "foreign", "solver_id": "other"})))
    assert db.solver_ratings.docs[-1]["solver_id"] == "one" and db.solver_ratings.docs[-1]["tenant_id"] == "solvit"
    assert db.solvers.docs[0]["client_rating_average"] == 85


def test_it_rating_void_cannot_modify_other_tenants():
    db = database([solver()]);db.solver_ratings.docs = [{"_id": ObjectId(), "id": "foreign-rating", "tenant_id": "foreign", "solver_id": "one", "voided": False}]
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor("it_admin"))):
        with pytest.raises(HTTPException) as error: run(solvers.void_rating("foreign-rating", request({"reason": "Synthetic test reason"})))
    assert error.value.status_code == 404 and db.solver_ratings.writes == 0


def test_permission_override_cannot_widen_an_ordinary_solver_to_other_records():
    db = database([solver(), solver("two")])
    with patch.object(access, "get_module_access", return_value={"level": "Full", "scope": None}):
        with pytest.raises(HTTPException): run(access.authorize_solver(db, actor("solver", email="one@example.com"), "two"))
        with pytest.raises(HTTPException): run(access.solver_access(db, actor("solver"), write=True))


def test_custom_solver_base_role_cannot_widen_self_scope_through_override():
    db = database([solver(), solver("two")])
    with patch.dict(access.CUSTOM_ROLE_DEFINITIONS, {"custom_self": {"inherits_from": "solver"}}), \
            patch.object(access, "get_module_access", return_value={"level": "Full", "scope": None}):
        with pytest.raises(HTTPException): run(access.authorize_solver(db, actor("custom_self", email="one@example.com"), "two"))
        with pytest.raises(HTTPException): run(access.solver_access(db, actor("custom_self"), write=True))


def test_native_storage_account_alias_cannot_hide_conflicting_solver_accounts():
    record = solver()
    db = database([record], [account(role="solver", solver_id=record["_id"])])
    with pytest.raises(HTTPException) as error: run(access.own_solver(db, actor("solver", solver_id="one")))
    assert error.value.status_code == 409


def test_private_hr_access_is_audited_without_copying_private_values():
    db = database([solver(bank_account_number="private-marker")])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        run(solvers.get_solver("one", request()))
    assert db.audit_logs.docs[0]["event"] == "solver.private_record.view"
    assert "private-marker" not in str(db.audit_logs.docs)


def test_private_hr_read_does_not_return_data_if_audit_fails():
    db = database([solver(bank_account_number="private-marker")])
    db.audit_logs.insert_one = AsyncMock(side_effect=RuntimeError("synthetic unavailable audit"))
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error: run(solvers.get_solver("one", request()))
    assert error.value.status_code == 503


def test_concurrent_formatted_phone_creation_cannot_create_two_solvers():
    db = database()
    async def create_both():
        return await asyncio.gather(
            solvers.create_solver(solvers.SolverCreate(full_name="Synthetic first", phone_number="0700000001"), request()),
            solvers.create_solver(solvers.SolverCreate(full_name="Synthetic second", phone_number="+254700000001"), request()),
            return_exceptions=True)
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())), \
            patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        results = run(create_both())
    assert len(db.solvers.docs) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1


@pytest.mark.parametrize("value", ["not-a-number", float("nan"), float("inf")])
def test_invalid_rating_numbers_never_write_metrics(value):
    db = database([solver()])
    with patch.object(solvers, "get_db", return_value=db), patch.object(solvers, "get_current_user", AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error: run(solvers.submit_client_rating("one", request({"accuracy": value, "timeliness": 80, "overall": 80})))
    assert error.value.status_code == 400 and db.solver_ratings.writes == db.solvers.writes == 0


@pytest.mark.parametrize("role", ["employee", "solver", "line_manager"])
def test_onboarding_read_cannot_create_or_view_another_solver_induction(role):
    db = database([solver(), solver("two")]);db.onboarding_tasks = Collection()
    with patch.object(onboarding, "get_db", return_value=db), patch.object(onboarding, "get_current_user", AsyncMock(return_value=actor(role, email="one@example.com"))):
        with pytest.raises(HTTPException): run(onboarding.get_solver_onboarding("two", request()))
    assert db.onboarding_tasks.writes == 0


def test_solver_self_can_read_own_induction_without_lazy_record_creation():
    db = database([solver()]);db.onboarding_tasks = Collection()
    with patch.object(onboarding, "get_db", return_value=db), patch.object(onboarding, "get_current_user", AsyncMock(return_value=actor("solver", email="one@example.com"))):
        assert run(onboarding.get_solver_onboarding("one", request())) == []
    assert db.onboarding_tasks.writes == 0


def test_solver_can_complete_own_assigned_step_but_not_manager_step_or_other_subject():
    db = database([solver(), solver("two")])
    task = {"_id": ObjectId(), "id": "task", "tenant_id": "solvit", "entity_type": "solver", "entity_id": "one", "assigned_role": "solver"}
    db.onboarding_tasks = Collection([task])
    with patch.object(onboarding, "get_db", return_value=db), patch.object(onboarding, "get_current_user", AsyncMock(return_value=actor("solver", email="one@example.com"))):
        result = run(onboarding.update_task("task", onboarding.TaskUpdate(status="Completed", completed_by="forged"), request()))
        assert result["completed_by"] == "synthetic-account"
        for change in ({"assigned_role": "line_manager"}, {"entity_id": "two"}):
            db.onboarding_tasks.docs[0].update(change)
            with pytest.raises(HTTPException): run(onboarding.update_task("task", onboarding.TaskUpdate(status="Completed"), request()))
    assert db.onboarding_tasks.writes == 1


@pytest.mark.parametrize("kind", ["task", "notification"])
def test_shared_task_and_notification_routes_cannot_bypass_solver_ownership(kind):
    db = database([solver(), solver("two")]);user = actor("solver", email="one@example.com")
    if kind == "task":
        operation = authorize_task(db, user, {"entity_type": "solver", "entity_id": "two", "assigned_role": "solver"}, write=True)
    else:
        operation = authorize_notification(db, user, {"recipient_role": "solver", "data": {"solver_id": "two"}})
    with pytest.raises(HTTPException) as error: run(operation)
    assert error.value.status_code == 403


@pytest.mark.parametrize("change", [{"role_title": "Solvers Manager"}, {"current_salary_kes": 80000}, {"national_id_number": "forged-private"}])
def test_line_manager_cannot_promote_report_into_solver_authority_or_change_private_fields(change):
    db = database(employees=[employee("manager"), employee("report", line_manager_id="manager", role_title="Valuation Officer")])
    user = actor("line_manager", employee_id="manager")
    with patch.object(employee_routes, "get_db", return_value=db), patch.object(employee_routes, "get_current_user", AsyncMock(return_value=user)):
        with pytest.raises(HTTPException) as error:
            run(employee_routes.update_employee("report", employee_routes.EmployeeUpdate(**change), request()))
    assert error.value.status_code == 403 and db.employees.writes == 0


def test_hr_cannot_change_other_tenant_employee_role_to_grant_solver_authority():
    db = database(employees=[employee("foreign-report", tenant_id="foreign", role_title="Valuation Officer")])
    with patch.object(employee_routes, "get_db", return_value=db), patch.object(employee_routes, "get_current_user", AsyncMock(return_value=actor())):
        with pytest.raises(HTTPException) as error:
            run(employee_routes.update_employee("foreign-report", employee_routes.EmployeeUpdate(role_title="Solvers Manager"), request()))
    assert error.value.status_code == 404 and db.employees.writes == 0


def test_employee_storage_alias_shadow_cannot_grant_another_managers_reports():
    from utils.employee_integrity import resolve_user_employee
    owner = employee("manager", role_title="Solvers Manager")
    shadow = employee(str(owner["_id"]), role_title="Different manager", work_email="different@example.com")
    db = database(employees=[owner, shadow])
    with pytest.raises(HTTPException) as error:
        run(resolve_user_employee(db, actor("line_manager", employee_id="manager")))
    assert error.value.status_code == 409


@pytest.mark.parametrize("role", ["employee", "line_manager", "solvers_manager"])
def test_employee_team_view_redacts_private_fields_without_mutating_record(role):
    record = employee("report", current_salary_kes=80000, bank_account="private", national_id_number="private", medical_notes="private", password_hash="secret")
    view = employee_routes.employee_view(record, actor(role, employee_id="other"))
    assert view["id"] == "report"
    assert not {"current_salary_kes", "bank_account", "national_id_number", "medical_notes", "password_hash"} & view.keys()
    assert record["bank_account"] == "private" and "_id" in record


@pytest.mark.parametrize("role", ["hr_admin", "hr_manager", "employee"])
def test_employee_hr_and_self_views_preserve_authorized_private_fields(role):
    record = employee("self", current_salary_kes=80000, bank_account="private", password_hash="secret")
    view = employee_routes.employee_view(record, actor(role, employee_id="self"))
    assert view["current_salary_kes"] == 80000 and view["bank_account"] == "private"
    assert "password_hash" not in view
