"""Real HTTP routing/JWT/password checks with synthetic, in-memory records."""
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import jwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from server import app, SESSION_EXEMPT_ENDPOINTS
from routes import auth_routes
from utils import auth, security
from utils.employee_accounts import provision_employee_account
from .integrity_fakes import Database, Collection, employee, account

INITIAL = "Original-local-test-password-2026"
UPDATED = "Updated-local-test-password-2026"


@pytest.fixture(scope="module")
def initial_hash():
    return auth.hash_password(INITIAL)


@pytest.fixture
def session(monkeypatch, initial_hash):
    monkeypatch.setenv("JWT_SECRET", "synthetic-local-signing-key-for-password-tests-only")
    user = account(password_hash=initial_hash, employee_id="staff", is_active=True,
                   must_change_password=True, full_name="Synthetic staff")
    db = Database([employee()], [user])
    for name in ("user_session_invalidations", "revoked_refresh_tokens", "notifications"):
        setattr(db, name, Collection())
    with ExitStack() as stack:
        stack.enter_context(patch("database.get_db", return_value=db))
        stack.enter_context(patch.object(auth_routes, "get_db", return_value=db))
        stack.enter_context(patch.object(auth_routes, "rate_limit", return_value=False))
        stack.enter_context(patch.object(auth_routes, "is_locked_out", return_value=0))
        client = TestClient(app, base_url="http://127.0.0.1:18089")
        yield client, db, db.users.docs[0]
        client.close()


def sign_in(client, password=INITIAL):
    return client.post("/api/auth/login", json={"email": "staff@example.com", "password": password})


def access_for(user):
    return auth.create_access_token(str(user["_id"]), user["email"], user["role"], user.get("password_changed_at"))


def refresh_for(user):
    return auth.create_refresh_token(str(user["_id"]), user.get("password_changed_at"))[0]


def assert_restricted(response):
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "password_change_required"


def set_cookie(client, name, value):
    # Match real response-cookie host/path, so replay replaces the existing
    # cookie and logout deletion tests do not create a second hostless cookie.
    client.cookies.set(name, value, domain="127.0.0.1", path="/")


def test_first_login_has_only_recovery_access_and_secure_cookies(session):
    client, db, _ = session
    signed = sign_in(client)
    assert signed.status_code == 200 and signed.json()["must_change_password"] is True
    assert set(signed.json()) == {"id", "email", "full_name", "role", "must_change_password"}
    assert all("Secure" in cookie and "HttpOnly" in cookie for cookie in signed.headers.get_list("set-cookie"))
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    assert set(me.json()) == {"id", "email", "full_name", "role", "must_change_password"}
    assert_restricted(client.get("/api/employees"))
    assert db.employees.writes == 0 and db.notifications.writes == 0


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/employees/directory"), ("GET", "/api/employees/organogram"),
    ("GET", "/api/employees/staff"), ("GET", "/api/employees/staff/profile"),
    ("GET", "/api/employees/me/profile"), ("GET", "/api/employees/me/profile-changes"),
    ("GET", "/api/performance/cycles"), ("POST", "/api/performance/cycles"),
    ("PUT", "/api/performance/forged/goals"),
    ("POST", "/api/performance/forged/assessments/self"),
    ("POST", "/api/performance/forged/assessments/release"),
    ("GET", "/api/lifecycle/checklists"), ("POST", "/api/lifecycle/initiate"),
    ("PUT", "/api/lifecycle/onboarding/tasks/forged"),
    ("POST", "/api/lifecycle/offboarding/staff/complete"),
    ("POST", "/api/lifecycle/offboarding/staff/authorize-deactivation"),
    ("GET", "/api/documents/me"), ("GET", "/api/documents/forged/download"),
    ("POST", "/api/documents/employee/staff/upload"), ("PUT", "/api/documents/forged"),
    ("POST", "/api/employees/me/profile-changes"), ("GET", "/api/employees/profile-change-inbox"),
    ("PUT", "/api/employees/profile-changes/forged/decision"),
    ("GET", "/api/reporting/catalogue"), ("GET", "/api/reporting/audit"),
    ("GET", "/api/reporting/reports/employees"), ("GET", "/api/reporting/reports/employees/export.csv"),
    ("GET", "/api/reporting/reports/employees/export.xlsx"),
    ("GET", "/api/benefits/me"), ("GET", "/api/benefits/schemes"), ("POST", "/api/benefits/schemes"),
    ("PUT", "/api/benefits/schemes/forged"), ("POST", "/api/benefits/requests"), ("GET", "/api/benefits/requests"),
    ("PUT", "/api/benefits/requests/forged/decision"), ("GET", "/api/benefits/premiums"), ("PUT", "/api/benefits/schemes/forged/premium"),
    ("GET", "/api/lnd/programmes"), ("POST", "/api/lnd/programmes"),
    ("PUT", "/api/lnd/programmes/forged"), ("POST", "/api/lnd/programmes/forged/assign"),
    ("PUT", "/api/lnd/training/forged/completion"),
    ("GET", "/api/solver-assessments/capabilities"), ("GET", "/api/solver-assessments/configurations"),
    ("POST", "/api/solver-assessments/configurations"), ("POST", "/api/solver-assessments/configurations/forged/publish"),
    ("GET", "/api/solver-assessments/administration-options"), ("GET", "/api/solver-assessments/attempts"),
    ("POST", "/api/solver-assessments/attempts"), ("GET", "/api/solver-assessments/attempts/forged"),
    ("POST", "/api/solver-assessments/attempts/forged/parts/A/submit"), ("POST", "/api/solver-assessments/attempts/forged/score"),
    ("GET", "/api/solver-assessments/attempts/forged/documents/forged/download"),
    ("GET", "/api/solver-assessments/solvers/forged/competencies"), ("POST", "/api/solver-assessments/solvers/forged/competencies"),
    ("GET", "/api/solvers/me"), ("GET", "/api/solvers/directory-options"),
    ("GET", "/api/solvers/forged/workflow"), ("POST", "/api/solvers/forged/induction"),
    ("POST", "/api/solvers/forged/verification"), ("GET", "/api/solvers/forged/documents"),
    ("POST", "/api/solvers/forged/documents"), ("GET", "/api/solvers/forged/documents/forged/download"),
    ("POST", "/api/solvers/forged/assessments/forged/review"),
    ("GET", "/api/leave"), ("GET", "/api/lnd/training"),
    ("GET", "/api/lnd/idp/staff"), ("GET", "/api/lnd/skills-matrix/staff"),
    ("GET", "/api/exports/employees.csv"), ("GET", "/api/dashboard/line-manager"),
    ("GET", "/api/dashboard/staff-home?employee_id=other"),
    ("GET", "/api/automation/notifications/centre"), ("PUT", "/api/automation/notifications/forged/read"),
    ("POST", "/api/access/users/employee-account"), ("PUT", "/api/access/users/forged/role"),
    ("POST", "/api/forms/form-31/submit"), ("PUT", "/api/leave/forged/decision"),
    ("PUT", "/api/lnd/training/forged/decision"), ("POST", "/api/leave"),
])
def test_alternate_and_direct_requests_cannot_bypass_gate(session, method, path):
    client, db, user = session
    client.cookies.clear()
    response = client.request(method, path, headers={
        "Authorization": "Bearer " + access_for(user),
        "X-Original-URL": "/api/auth/me", "X-Forwarded-Uri": "/api/auth/password/change",
    }, json={"must_change_password": False, "employee_id": "other", "role": "hr_admin"})
    assert_restricted(response)


@pytest.mark.parametrize('state', ['Suspended', 'Inactive', 'Deactivated'])
def test_existing_solver_token_cannot_bypass_lifecycle_gate(session, state):
    from .test_solver_security import solver
    client, db, user = session
    user.update(role='solver', account_type='solver', employee_id=None, solver_id='one', must_change_password=False)
    db.solvers = Collection([solver(lifecycle_state=state)])
    headers = {'Authorization': 'Bearer ' + access_for(user)}
    for path in ('/api/forms/form-03', '/api/automation/notifications/centre', '/api/policies'):
        response = client.get(path, headers=headers)
        assert response.status_code == 403
        assert 'lifecycle state' in str(response.json())
    assert client.get('/api/auth/me', headers=headers).status_code == 200


@pytest.mark.parametrize('state', ['Active', 'Registering'])
def test_eligible_solver_retains_protected_access_after_password_change(session, state):
    from .test_solver_security import solver
    client, db, user = session
    user.update(role='solver', account_type='solver', employee_id=None, solver_id='one', must_change_password=False)
    db.solvers = Collection([solver(lifecycle_state=state)])
    response = client.get('/api/forms/form-03', headers={'Authorization': 'Bearer ' + access_for(user)})
    assert response.status_code == 200
    assert 'correct_answer' not in response.text
    assert db.users.writes == 0 and db.employees.writes == 0


@pytest.mark.parametrize("role", ["employee", "hr_admin", "it_admin", "board", "custom_staff"])
def test_privileged_or_custom_role_does_not_bypass_requirement(session, role):
    client, _, user = session
    user["role"] = role
    set_cookie(client, "access_token", access_for(user))
    assert_restricted(client.get("/api/employees"))


def test_existing_token_observes_flag_set_after_issuance(session):
    client, _, user = session
    user["must_change_password"] = False
    token = access_for(user)
    user["must_change_password"] = True
    set_cookie(client, "access_token", token)
    assert_restricted(client.get("/api/employees"))


def test_legacy_token_and_forged_requirement_claim_do_not_bypass(session):
    client, _, user = session
    payload = jwt.decode(access_for(user), auth.get_jwt_secret(), algorithms=["HS256"])
    payload.pop("pwd")
    payload["must_change_password"] = False
    set_cookie(client, "access_token", jwt.encode(payload, auth.get_jwt_secret(), algorithm="HS256"))
    assert_restricted(client.get("/api/employees"))


def test_refresh_rotates_but_remains_restricted(session):
    client, db, user = session
    original = refresh_for(user)
    set_cookie(client, "refresh_token", original)
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200 and refreshed.json()["must_change_password"] is True
    assert_restricted(client.get("/api/employees"))
    assert client.get("/api/auth/me").status_code == 200
    set_cookie(client, "refresh_token", original)
    assert client.post("/api/auth/refresh").status_code == 401
    assert db.revoked_refresh_tokens.writes > 0


def test_refresh_token_cannot_be_used_as_access_token(session):
    client, _, user = session
    set_cookie(client, "access_token", refresh_for(user))
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/employees").status_code == 401


@pytest.mark.parametrize("current,new", [("wrong-local-password", UPDATED), (INITIAL, "short"), (INITIAL, INITIAL)])
def test_failed_password_change_keeps_restriction_and_password(session, current, new):
    client, db, user = session
    old_hash = user["password_hash"]
    set_cookie(client, "access_token", access_for(user))
    changed = client.post("/api/auth/password/change", json={"current_password": current, "new_password": new})
    assert changed.status_code == 400
    assert user["must_change_password"] is True and user["password_hash"] == old_hash
    assert_restricted(client.get("/api/employees"))
    assert db.notifications.writes == 0


def test_completion_revokes_old_access_refresh_and_allows_immediate_new_login(session):
    client, db, user = session
    assert sign_in(client).status_code == 200
    old_access = client.cookies.get("access_token")
    old_refresh = client.cookies.get("refresh_token")
    changed = client.post("/api/auth/password/change", json={"current_password": INITIAL, "new_password": UPDATED})
    assert changed.status_code == 200
    assert user["must_change_password"] is False and auth.verify_password(UPDATED, user["password_hash"])
    assert user["password_history"] and user["password_changed_at"]
    assert not client.cookies.get("access_token") and not client.cookies.get("refresh_token")
    set_cookie(client, "access_token", old_access)
    assert client.get("/api/auth/me").status_code == 401
    set_cookie(client, "refresh_token", old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
    assert sign_in(client).status_code == 401
    assert sign_in(client, UPDATED).json()["must_change_password"] is False
    assert client.get("/api/auth/me").status_code == 200
    # No one-second wait is needed after password-change invalidation.
    assert client.get("/api/access/matrix").status_code == 200
    assert db.notifications.writes == 0


def test_password_snapshot_closes_late_token_issuance_race(session):
    client, _, user = session
    old_stamp = user.get("password_changed_at")
    user["must_change_password"] = False
    user["password_changed_at"] = datetime.now(timezone.utc).isoformat()
    # Minted AFTER the change, but from a pre-change login/refresh user snapshot.
    late_access = auth.create_access_token(str(user["_id"]), user["email"], user["role"], old_stamp)
    late_refresh = auth.create_refresh_token(str(user["_id"]), old_stamp)[0]
    set_cookie(client, "access_token", late_access)
    assert client.get("/api/auth/me").status_code == 401
    set_cookie(client, "refresh_token", late_refresh)
    assert client.post("/api/auth/refresh").status_code == 401


def test_password_timestamp_is_effective_if_revocation_store_write_fails(session):
    client, _, user = session
    old_access = access_for(user)
    old_refresh = refresh_for(user)
    set_cookie(client, "access_token", old_access)
    with patch.object(auth_routes, "revoke_all_user_refresh_tokens", AsyncMock(side_effect=RuntimeError("synthetic write failure"))):
        with pytest.raises(RuntimeError):
            client.post("/api/auth/password/change", json={"current_password": INITIAL, "new_password": UPDATED})
    assert user["must_change_password"] is False
    assert client.get("/api/auth/me").status_code == 401
    set_cookie(client, "refresh_token", old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401


def test_concurrent_password_change_cannot_overwrite_newer_credential(session):
    client, _, user = session
    set_cookie(client, "access_token", access_for(user))
    with patch.object(auth_routes.get_db().users, "update_one", AsyncMock(return_value=type("Result", (), {"modified_count": 0})())):
        response = client.post("/api/auth/password/change", json={"current_password": INITIAL, "new_password": UPDATED})
    assert response.status_code == 409 and user["must_change_password"] is True


def test_normal_legacy_user_without_flag_or_timestamp_keeps_login_and_refresh(session):
    client, _, user = session
    user.pop("must_change_password")
    assert sign_in(client).json()["must_change_password"] is False
    assert client.get("/api/auth/me").json()["employee_id"] == "staff"
    assert client.get("/api/access/matrix").status_code == 200
    assert client.post("/api/auth/refresh").json()["must_change_password"] is False
    assert client.get("/api/auth/me").status_code == 200


def test_recorded_expired_password_uses_the_same_gate(session):
    client, _, user = session
    user["must_change_password"] = False
    user["password_changed_at"] = (datetime.now(timezone.utc) - timedelta(days=366)).isoformat()
    assert sign_in(client).json()["must_change_password"] is True
    assert_restricted(client.get("/api/employees"))


def test_employee_link_conflict_does_not_prevent_own_password_recovery(session):
    client, _, user = session
    user["employee_id"] = "missing-employee"
    assert sign_in(client).status_code == 200
    assert client.get("/api/auth/me").json()["must_change_password"] is True
    assert client.post("/api/auth/password/change", json={"current_password": INITIAL, "new_password": UPDATED}).status_code == 200
    # Password completion does not repair or bypass the integrity conflict.
    assert sign_in(client, UPDATED).status_code == 409


def test_new_provisioned_account_requires_change_and_provisioning_preserves_existing_flag(session):
    import asyncio
    client, db, _ = session
    db.users.docs.clear()
    actor = {"id": "synthetic-it", "tenant_id": "solvit", "role": "it_admin"}
    created = asyncio.run(provision_employee_account(db, "staff", INITIAL, actor))
    assert created["created"] is True and db.users.docs[0]["must_change_password"] is True
    before = db.users.docs[0]["password_hash"]
    asyncio.run(provision_employee_account(db, "staff", UPDATED, actor))
    assert db.users.docs[0]["password_hash"] == before and db.users.docs[0]["must_change_password"] is True
    assert sign_in(client).json()["must_change_password"] is True
    assert_restricted(client.get("/api/employees"))


def test_logout_remains_available_and_burns_restricted_refresh_token(session):
    client, _, user = session
    set_cookie(client, "access_token", access_for(user))
    old_refresh = refresh_for(user)
    set_cookie(client, "refresh_token", old_refresh)
    assert client.post("/api/auth/logout").status_code == 200
    assert not client.cookies.get("access_token") and not client.cookies.get("refresh_token")
    set_cookie(client, "refresh_token", old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401


@pytest.mark.parametrize("transport", ["cookie", "bearer", "refresh_only"])
def test_logout_revokes_copied_current_pair_without_ending_another_session(session, transport):
    client, _, user = session
    user["must_change_password"] = False
    first_refresh, first_jti = auth.create_refresh_token(str(user["_id"]))
    first_access = auth.create_access_token(str(user["_id"]), user["email"], user["role"], session_jti=first_jti)
    second_refresh, second_jti = auth.create_refresh_token(str(user["_id"]))
    second_access = auth.create_access_token(str(user["_id"]), user["email"], user["role"], session_jti=second_jti)
    headers = {}
    if transport == "cookie":
        set_cookie(client, "access_token", first_access)
        set_cookie(client, "refresh_token", first_refresh)
    elif transport == "bearer":
        headers["Authorization"] = "Bearer " + first_access
    else:
        set_cookie(client, "refresh_token", first_refresh)
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    set_cookie(client, "access_token", first_access)
    assert client.get("/api/auth/me").status_code == 401
    set_cookie(client, "refresh_token", first_refresh)
    assert client.post("/api/auth/refresh").status_code == 401
    set_cookie(client, "access_token", second_access)
    set_cookie(client, "refresh_token", second_refresh)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/refresh").status_code == 200


def test_legacy_access_logout_uses_safe_user_cutoff(session):
    client, _, user = session
    payload = jwt.decode(access_for(user), auth.get_jwt_secret(), algorithms=["HS256"])
    for key in ("pwd", "jti", "sid"):
        payload.pop(key, None)
    old_access = jwt.encode(payload, auth.get_jwt_secret(), algorithm="HS256")
    old_refresh = refresh_for(user)
    set_cookie(client, "access_token", old_access)
    assert client.post("/api/auth/logout").status_code == 200
    set_cookie(client, "access_token", old_access)
    assert client.get("/api/auth/me").status_code == 401
    set_cookie(client, "refresh_token", old_refresh)
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.clear()
    assert sign_in(client).status_code == 200


def test_legacy_logout_revokes_tokens_issued_at_exactly_the_cutoff_clock_tick(session):
    client, _, user = session
    fixed = datetime.now(timezone.utc) - timedelta(seconds=2)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    with patch.object(auth, "datetime", FixedClock), patch.object(security, "datetime", FixedClock):
        payload = jwt.decode(access_for(user), auth.get_jwt_secret(), algorithms=["HS256"])
        for key in ("pwd", "jti", "sid"):
            payload.pop(key, None)
        old_access = jwt.encode(payload, auth.get_jwt_secret(), algorithm="HS256")
        old_refresh = refresh_for(user)
        set_cookie(client, "access_token", old_access)
        assert client.post("/api/auth/logout").status_code == 200
        set_cookie(client, "access_token", old_access)
        assert client.get("/api/auth/me").status_code == 401
        set_cookie(client, "refresh_token", old_refresh)
        assert client.post("/api/auth/refresh").status_code == 401


def test_normal_refresh_does_not_revoke_an_unexpired_access_token(session):
    client, _, user = session
    user["must_change_password"] = False
    assert sign_in(client).status_code == 200
    original_access = client.cookies.get("access_token")
    assert client.post("/api/auth/refresh").status_code == 200
    set_cookie(client, "access_token", original_access)
    assert client.get("/api/auth/me").status_code == 200


def test_only_minimal_auth_handlers_are_exempt_and_global_gate_covers_new_routes(session):
    client, _, user = session
    exempt_auth = {endpoint.__name__ for endpoint in SESSION_EXEMPT_ENDPOINTS if endpoint.__module__ == auth_routes.__name__}
    assert exempt_auth == {"login", "logout", "refresh_token", "get_me", "change_password", "forgot_password", "reset_password"}

    async def unguarded_probe(request: Request):
        raise AssertionError("A restricted session reached an unguarded business handler")

    app.add_api_route("/api/test-password-probe", unguarded_probe, methods=["GET"])
    try:
        set_cookie(client, "access_token", access_for(user))
        assert_restricted(client.get("/api/test-password-probe"))
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/solver-intake/counties").status_code == 200
    finally:
        app.router.routes[:] = [route for route in app.router.routes if route.endpoint is not unguarded_probe]


def test_forged_token_role_is_rejected_before_protected_application_access(session):
    client, _, user = session
    payload = jwt.decode(access_for(user), auth.get_jwt_secret(), algorithms=["HS256"])
    payload["role"] = "hr_admin"
    set_cookie(client, "access_token", jwt.encode(payload, auth.get_jwt_secret(), algorithm="HS256"))
    assert client.get("/api/employees").status_code == 401
