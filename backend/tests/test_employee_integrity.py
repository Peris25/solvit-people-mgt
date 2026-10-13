import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.employee_integrity import (
    normalize_email, find_employee, resolve_user_employee, validate_manager,
    integrity_write, insert_employee,
)
from utils.employee_accounts import provision_employee_account
from utils.integrity_audit import audit_records
from routes import employees, recruitment, data_import, access, auth_routes
from .integrity_fakes import Database, employee, account


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.mark.parametrize("value", ["staff@example.com", "STAFF@EXAMPLE.COM", "  Staff@Example.com  "])
def test_email_normalization(value):
    assert normalize_email(value) == "staff@example.com"
    assert normalize_email("staff+tag@example.com") == "staff+tag@example.com"


@pytest.mark.parametrize("value", [None, "", "bad", "staff @example.com"])
def test_invalid_email(value):
    with pytest.raises(HTTPException) as error:
        normalize_email(value)
    assert error.value.status_code == 422


@pytest.mark.parametrize("legacy_email", ["staff@example.com", "STAFF@EXAMPLE.COM", " staff@example.com "])
def test_creation_rejects_normalized_legacy_duplicates(legacy_email):
    db = Database([employee(email=legacy_email), employee("boss", "boss@example.com")])
    with pytest.raises(HTTPException) as error:
        run(insert_employee(db, {"id": "new", "work_email": "Staff@example.com", "line_manager_id": "boss"}))
    assert error.value.status_code == 409
    assert db.employees.writes == 0


def test_new_employee_canonicalizes_manager_alias_and_preserves_existing_records():
    boss = employee("boss", "boss@example.com", is_board_chair=True)
    db = Database([boss])
    original = deepcopy(db.employees.docs)
    result = run(insert_employee(db, {"id": "new", "work_email": " NEW@example.com ", "line_manager_id": str(boss["_id"])}))
    assert result["work_email"] == result["work_email_normalized"] == "new@example.com"
    assert result["line_manager_id"] == "boss"
    assert db.employees.docs[0] == original[0]


@pytest.mark.parametrize("kind", ["missing", "exited", "self", "cycle", "broken_chain", "cross_tenant"])
def test_invalid_manager_assignments(kind):
    staff = employee()
    boss = employee("boss", "boss@example.com")
    manager_id = "boss"
    if kind == "missing": manager_id = "absent"
    if kind == "exited": boss["lifecycle_state"] = "Exited"
    if kind == "self": manager_id = str(staff["_id"])
    if kind == "cycle": boss["line_manager_id"] = "staff"
    if kind == "broken_chain": boss["line_manager_id"] = "absent"
    if kind == "cross_tenant": boss["tenant_id"] = "other"
    db = Database([staff, boss])
    with pytest.raises(HTTPException):
        run(validate_manager(db, manager_id, staff))
    assert db.employees.writes == 0


def test_root_exception_is_explicit_not_role_based():
    db = Database()
    assert run(validate_manager(db, None, employee(is_board_chair=True))) is None
    with pytest.raises(HTTPException):
        run(validate_manager(db, None, employee(role="hr_admin")))


def test_ambiguous_reference_rejected_instead_of_selecting_a_record():
    db = Database([employee("duplicate"), employee("duplicate", "other@example.com")])
    with pytest.raises(HTTPException):
        run(find_employee(db, "duplicate"))


@pytest.mark.parametrize("mode", ["explicit", "missing", "seed_bug", "system"])
def test_legacy_account_resolution_is_read_only(mode):
    staff = employee()
    user = account()
    if mode == "explicit":
        user.update(employee_id="staff", email="old-login@example.com")
    if mode == "seed_bug": user["employee_id"] = str(user["_id"])
    if mode == "system": user["account_type"] = "system"
    db = Database([staff], [user])
    result = run(resolve_user_employee(db, user))
    assert (result is None) == (mode == "system")
    if result: assert result["id"] == "staff"
    assert db.employees.writes == db.users.writes == 0


@pytest.mark.parametrize("conflict", ["duplicate_employees", "duplicate_accounts", "orphan", "shared_link"])
def test_conflicting_account_relationships_fail_closed(conflict):
    staff, user = employee(), account()
    emps, users = [staff], [user]
    if conflict == "duplicate_employees": emps.append(employee("other"))
    if conflict == "duplicate_accounts": users.append(account(email="STAFF@example.com"))
    if conflict == "orphan": user["employee_id"] = "absent"
    if conflict == "shared_link":
        user["employee_id"] = "staff"
        users.append(account("other@example.com", employee_id="staff"))
    with pytest.raises(HTTPException) as error:
        run(resolve_user_employee(Database(emps, users), user))
    assert error.value.status_code == 409


def test_account_provisioning_idempotent_preserves_password_and_role():
    user = account(role="hr_admin", password_hash="preserved", employee_id=None)
    db = Database([employee()], [user])
    actor = {"id": "admin", "tenant_id": "solvit"}
    first = run(provision_employee_account(db, "staff", None, actor))
    second = run(provision_employee_account(db, "staff", "Ignored-for-existing", actor))
    assert first["id"] == second["id"] == str(user["_id"])
    assert first["created"] is second["created"] is False
    assert db.users.docs[0]["employee_id"] == "staff"
    assert db.users.docs[0]["password_hash"] == "preserved"
    assert db.users.docs[0]["role"] == "hr_admin"
    assert len(db.users.docs) == 1


def test_new_account_requires_password_and_uses_employee_role():
    db = Database([employee()])
    actor = {"id": "admin"}
    with pytest.raises(HTTPException): run(provision_employee_account(db, "staff", None, actor))
    with patch("utils.employee_accounts.validate_password_policy") as policy, patch("utils.employee_accounts.hash_password", return_value="hash"):
        result = run(provision_employee_account(db, "staff", "Synthetic-initial", actor))
        policy.assert_called_once_with("Synthetic-initial", [])
    assert result["created"] is True
    assert db.users.docs[0]["role"] == "employee"
    assert db.users.docs[0]["must_change_password"] is True
    assert "password" not in json.dumps(result)


def test_existing_account_cannot_be_reassigned_to_another_employee():
    db = Database([employee()], [account(employee_id="different")])
    with pytest.raises(HTTPException): run(provision_employee_account(db, "staff", None, {"id": "admin"}))
    assert db.users.writes == 0


def test_concurrent_employee_creation_is_serialized_without_expiring_lock():
    db = Database([employee("boss", "boss@example.com")])
    async def create():
        try:
            async with integrity_write(db):
                return await insert_employee(db, {"id": "new", "work_email": "new@example.com", "line_manager_id": "boss"})
        except HTTPException as error:
            return error.status_code
    async def both():
        return await asyncio.gather(create(), create())
    results = run(both())
    assert len(db.employees.docs) == 2
    assert 409 in results
    assert not db.integrity_locks.docs


def test_unchanged_legacy_manager_is_preserved_by_employee_update():
    staff = employee(line_manager_id="bad-legacy-reference", department="Legacy")
    db = Database([staff])
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})):
        result = run(employees.update_employee("staff", employees.EmployeeUpdate(full_name="Updated", line_manager_id="bad-legacy-reference"), None))
    assert result["line_manager_id"] == "bad-legacy-reference"
    assert result["department"] == "Legacy"


def test_manager_cannot_edit_unrelated_employee():
    db = Database([employee(), employee("boss", "boss@example.com")])
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "u", "role": "line_manager", "employee_id": "boss"})), patch.object(employees, "_my_employee_id", AsyncMock(return_value="boss")):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee("staff", employees.EmployeeUpdate(full_name="Changed"), None))
    assert error.value.status_code == 403
    assert db.employees.writes == 0


def test_repeated_conversion_does_not_create_duplicate_employee():
    from bson import ObjectId
    candidate = {"_id": ObjectId(), "id": "candidate", "full_name": "Synthetic applicant", "email": "new@example.com", "department": "Operations", "position_applied": "Staff"}
    db = Database([employee("boss", "boss@example.com")], candidates=[candidate])
    request = SimpleNamespace(json=AsyncMock(return_value={"line_manager_id": "boss"}))
    with patch.object(recruitment, "get_db", return_value=db), patch.object(recruitment, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        first = run(recruitment.convert_to_employee("candidate", request))
        second = run(recruitment.convert_to_employee("candidate", request))
    assert first["id"] == second["id"]
    assert len(db.employees.docs) == 2


def test_import_detects_batch_and_large_legacy_dataset_duplicates():
    existing = [employee(str(i), f"staff{i}@example.com") for i in range(1002)]
    boss = employee("boss", "boss@example.com", full_name="Unique Manager")
    db = Database(existing + [boss])
    template = data_import.TEMPLATES["fte_employee"]
    headers = [c[0] for c in template["columns"]]
    def row(email):
        values = {"Full Name": "Synthetic Staff", "Job Title": "Staff", "Work Email": email,
                  "Department": "Operations",
                  "Employment Start Date": "2025-01-01", "Line Manager Full Name": "Unique Manager"}
        level = next(key for key in headers if key.startswith("Job Level"))
        values[level] = "L2"
        return [values.get(h) for h in headers]
    results = run(data_import._validate_rows("fte_employee", [row("STAFF1001@EXAMPLE.COM"), row(" new@example.com "), row("NEW@example.com")], db))
    assert [r["valid"] for r in results] == [False, True, False]
    assert results[1]["normalized"]["line_manager_id"] == "boss"


def test_redacted_audit_detects_orphans_duplicates_cycles_without_mutation():
    first = employee("first", "private@example.com", line_manager_id="second")
    second = employee("second", " PRIVATE@EXAMPLE.COM ", line_manager_id="first")
    user = account("private@example.com", employee_id="missing")
    original = deepcopy(([first, second], [user]))
    report = audit_records([first, second], [user])
    assert report["issue_counts"]["duplicate_employee_email"] == 1
    assert report["issue_counts"]["reporting_cycle"] == 1
    assert report["issue_counts"]["orphaned_account_link"] == 1
    output = json.dumps(report)
    assert "private@example.com" not in output.lower()
    assert str(first["_id"]) not in output
    assert ([first, second], [user]) == original
    assert report["read_only"] is True
    assert report["indexes_ready"] is False


def test_demo_destruction_requires_explicit_development_flags():
    from automation.seed_data import require_demo_data_access
    with patch.dict("os.environ", {"APP_ENV": "production", "ALLOW_DESTRUCTIVE_DEMO_DATA": "true"}):
        with pytest.raises(HTTPException): require_demo_data_access()


def test_account_endpoint_retains_it_admin_permissions():
    with patch.object(access, "get_current_user", AsyncMock(return_value={"role": "hr_admin"})):
        with pytest.raises(HTTPException) as error:
            run(access.create_employee_account(access.EmployeeAccountRequest(employee_id="staff"), None))
    assert error.value.status_code == 403


@pytest.mark.parametrize("inactive,duplicate", [(True, False), (False, True)])
def test_login_rejects_inactive_or_ambiguous_accounts(inactive, duplicate):
    users = [account(is_active=not inactive)]
    if duplicate: users.append(account(" STAFF@EXAMPLE.COM "))
    db = Database(users=users)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
    with patch.object(auth_routes, "get_db", return_value=db), patch.object(auth_routes, "rate_limit", return_value=False), patch.object(auth_routes, "is_locked_out", return_value=0), patch.object(auth_routes, "record_audit", AsyncMock()), patch.object(auth_routes, "record_login_failure", return_value=4):
        with pytest.raises(HTTPException) as error:
            run(auth_routes.login(auth_routes.LoginRequest(email="staff@example.com", password="synthetic"), request, Response()))
    assert error.value.status_code == 401


def test_departing_manager_requires_report_reassignment():
    from utils.employee_integrity import change_employee_state
    boss = employee("boss", "boss@example.com")
    staff = employee(line_manager_id=str(boss["_id"]))
    db = Database([boss, staff])
    with pytest.raises(HTTPException) as error:
        run(change_employee_state(db, "boss", "Exited"))
    assert error.value.status_code == 409
    assert db.employees.writes == 0
    assert not db.integrity_locks.docs


def test_staff_update_rejects_email_collision_and_invalid_manager():
    db = Database([employee(), employee("other", "other@example.com")])
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})):
        for change in [{"work_email": " OTHER@example.com "}, {"line_manager_id": "absent"}]:
            with pytest.raises(HTTPException):
                run(employees.update_employee("staff", employees.EmployeeUpdate(**change), None))
    assert db.employees.writes == 0


def test_employee_email_change_preserves_explicit_login_identity():
    user = account(employee_id="staff", password_hash="preserved")
    db = Database([employee()], [user])
    with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})):
        result = run(employees.update_employee("staff", employees.EmployeeUpdate(work_email="NEW@example.com"), None))
    assert result["work_email"] == "new@example.com"
    assert db.users.docs[0] == user
    assert db.users.writes == 0


def test_valid_employee_link_that_equals_user_id_cannot_be_reassigned():
    user = account()
    linked = employee(str(user["_id"]), "other@example.com")
    user["employee_id"] = str(user["_id"])
    db = Database([employee(), linked], [user])
    with pytest.raises(HTTPException):
        run(provision_employee_account(db, "staff", None, {"id": "admin"}))
    assert db.users.writes == 0


def test_successful_login_and_authenticated_user_use_canonical_employee_link():
    import database
    import utils.auth as auth
    from utils import security
    user = account(email=" STAFF@EXAMPLE.COM ", password_hash="never-returned", role="hr_admin")
    user["employee_id"] = str(user["_id"])
    staff = employee()
    db = Database([staff], [user])
    original = deepcopy((db.users.docs, db.employees.docs))
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={}, cookies={})
    response = Response()
    with patch.dict("os.environ", {"JWT_SECRET": "synthetic-local-test-secret-only-32-chars"}), patch.object(auth_routes, "get_db", return_value=db), patch.object(auth_routes, "verify_password", return_value=True), patch.object(auth_routes, "rate_limit", return_value=False), patch.object(auth_routes, "is_locked_out", return_value=0), patch.object(auth_routes, "clear_login_attempts"), patch.object(auth_routes, "record_audit", AsyncMock()):
        result = run(auth_routes.login(auth_routes.LoginRequest(email=" STAFF@example.com ", password="synthetic"), request, response))
        assert result["employee_id"] == "staff"
        assert result["role"] == "hr_admin"
        assert "password_hash" not in result
        assert str(staff["_id"]) in result["employee_reference_ids"]
        request.cookies["access_token"] = auth.create_access_token(str(user["_id"]), user["email"], user["role"])
        with patch.object(database, "get_db", return_value=db), patch.object(security, "session_invalidated_after", AsyncMock(return_value=False)):
            me = run(auth.get_current_user(request))
        assert me["employee_id"] == "staff"
        assert me["id"] == str(user["_id"])
        assert "password_hash" not in me
    assert (db.users.docs, db.employees.docs) == original
    assert "HttpOnly" in str(response.headers)
    assert "Secure" in str(response.headers)


def test_bootstrap_does_not_purge_or_reset_existing_passwords():
    from automation import seed_data
    db = Database(users=[account(password_hash="preserved")])
    fixture = [{"email": "staff@example.com", "password": "synthetic-unused", "full_name": "Synthetic"}]
    with patch.dict("os.environ", {"APP_ENV": "development", "ALLOW_DESTRUCTIVE_DEMO_DATA": "true"}), patch.object(seed_data, "DEMO_USERS", fixture):
        run(seed_data.seed_users(db))
    assert db.users.docs[0]["password_hash"] == "preserved"
    assert db.users.writes == 0
    names = ["seed_users", "seed_admin_employees", "seed_pay_bands", "seed_automation_rules", "seed_holidays", "seed_policies"]
    with patch.dict("os.environ", {"APP_ENV": "development", "ALLOW_DESTRUCTIVE_DEMO_DATA": "true"}), patch.object(seed_data, "purge_legacy_demo_data", AsyncMock()) as purge, patch.multiple(seed_data, **{name: AsyncMock() for name in names}):
        run(seed_data.seed_all(db))
    purge.assert_not_called()


def test_snapshot_cli_is_read_only_redacts_and_accepts_extended_json(capsys):
    from bson.json_util import dumps
    from scripts import audit_employee_integrity as tool
    staff = employee(is_board_chair=True, work_email_normalized="staff@example.com")
    user = account(employee_id="staff", email_normalized="staff@example.com", password_hash="sensitive-placeholder")
    snapshot = dumps({"employees": [staff], "users": [user]})
    with patch.object(Path, "read_text", return_value=snapshot), patch.object(sys, "argv", ["audit", "--snapshot", "synthetic-snapshot.json"]), patch.object(tool, "read_database", AsyncMock()) as database_reader:
        assert tool.main() == 0
    database_reader.assert_not_called()
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["employees_scanned"] == report["accounts_scanned"] == 1
    assert report["indexes_ready"] is True
    assert "sensitive-placeholder" not in output
    assert "staff@example.com" not in output
    assert str(user["_id"]) not in output
