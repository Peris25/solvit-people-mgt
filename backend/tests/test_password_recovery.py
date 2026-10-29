import asyncio
import re
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from utils import password_recovery as recovery, auth, email_service
from .integrity_fakes import Database, Collection, account


def run(value): return asyncio.run(value)


@pytest.fixture(scope="module")
def initial_hash(): return auth.hash_password("Synthetic-original-password-2026")


@pytest.fixture
def db(monkeypatch, initial_hash):
    monkeypatch.setenv("FRONTEND_URL", "https://portal.example.com")
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "synthetic-recovery-signing-key-not-production")
    result = Database(users=[account(password_hash=initial_hash, is_active=True, must_change_password=True)])
    result.password_resets = Collection()
    result.password_reset_limits = Collection()
    result.email_log = Collection()
    result.email_retry_queue = Collection()
    return result


def issue(db, email="staff@example.com", **kwargs):
    with patch.object(email_service, "send_email", AsyncMock(return_value={"status": "sent"})) as send:
        response = run(recovery.request_reset(db, email, "127.0.0.8", **kwargs))
    token = re.search(r'#token=([A-Za-z0-9_-]+)', send.call_args.kwargs["html"]).group(1) if send.called else None
    return response, token, send


def test_generic_response_hash_only_storage_and_trusted_fragment_link(db):
    response, token, send = issue(db, " STAFF@EXAMPLE.COM ")
    assert response == run(recovery.request_reset(db, "missing@example.com", "127.0.0.9"))
    assert token and token not in str(db.password_resets.docs)
    assert db.password_resets.docs[0]["token_hash"] == recovery.digest(token)
    assert send.call_args.kwargs["to"] == "staff@example.com"
    assert send.call_args.kwargs["sensitive"] is True
    assert "https://portal.example.com/reset-password#token=" in send.call_args.kwargs["html"]


@pytest.mark.parametrize("kind", ["disabled", "duplicate", "unknown", "invalid_email", "mail_disabled", "bad_origin"])
def test_ineligible_requests_do_not_send_or_expose_accounts(db, monkeypatch, kind):
    email = "staff@example.com"
    if kind == "disabled": db.users.docs[0]["is_active"] = False
    if kind == "duplicate": db.users.docs.append(account(email=" STAFF@EXAMPLE.COM "))
    if kind == "unknown": email = "absent@example.com"
    if kind == "invalid_email": email = "not-an-email"
    if kind == "mail_disabled": monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED", "false")
    if kind == "bad_origin": monkeypatch.setenv("FRONTEND_URL", "http://untrusted.example.com/path?value=x")
    response, token, send = issue(db, email)
    assert response == recovery.GENERIC
    assert not token and not send.called
    assert not db.password_resets.docs


def test_cross_worker_email_rate_limit_is_persistent(db):
    for attempt in range(4):
        response, token, send = issue(db)
        assert response == recovery.GENERIC
        assert send.called == (attempt < 3)


def test_delivery_occurs_after_generic_response_and_failure_cannot_enable_link(db):
    background = BackgroundTasks()
    with patch.object(email_service, "send_email", AsyncMock(return_value={"status": "skipped"})) as send:
        assert run(recovery.request_reset(db, "staff@example.com", "127.0.0.8", background)) == recovery.GENERIC
        send.assert_not_called()
        assert db.password_resets.docs[0]["enabled"] is False
        run(background())
        assert db.password_resets.docs[0]["enabled"] is False
        send.assert_awaited_once()


def test_success_is_single_use_revokes_existing_sessions_and_preserves_mfa_and_roles(db):
    user = db.users.docs[0]
    access = auth.create_access_token(str(user["_id"]), user["email"], user["role"])
    refresh, unused = auth.create_refresh_token(str(user["_id"]))
    db.auth_mfa.docs = [{"_id": user["_id"], "generation": "existing-generation", "secret": "synthetic-private-state"}]
    before_mfa = deepcopy(db.auth_mfa.docs)
    response, token, send = issue(db)
    assert run(recovery.complete_reset(db, token, "Synthetic-updated-password-2026", "127.0.0.8"))["message"].startswith("Password updated")
    updated = db.users.docs[0]
    assert auth.verify_password("Synthetic-updated-password-2026", updated["password_hash"])
    assert updated["must_change_password"] is False
    assert updated["role"] == user["role"]
    assert db.auth_mfa.docs == before_mfa
    for value in (access, refresh):
        payload = jwt.decode(value, auth.get_jwt_secret(), algorithms=["HS256"])
        assert run(auth.token_invalidated(db, updated, payload)) is True
    with pytest.raises(HTTPException): run(recovery.complete_reset(db, token, "Another-synthetic-password", "127.0.0.8"))


@pytest.mark.parametrize("change", ["expired", "password", "email", "role", "disabled", "new_request"])
def test_stale_or_ineligible_reset_links_cannot_change_credentials(db, change):
    unused, token, send = issue(db)
    if change == "expired": db.password_resets.docs[0]["expires_at"] = (recovery.now() - timedelta(seconds=1)).isoformat()
    if change == "password": db.users.docs[0]["password_hash"] = "changed-concurrently"
    if change == "email": db.users.docs[0]["email"] = "different@example.com"
    if change == "role": db.users.docs[0]["role"] = "line_manager"
    if change == "disabled": db.users.docs[0]["is_active"] = False
    if change == "new_request": issue(db)
    before = deepcopy(db.users.docs)
    with pytest.raises(HTTPException) as error:
        run(recovery.complete_reset(db, token, "Synthetic-updated-password", "127.0.0.8"))
    assert error.value.status_code == 400
    assert db.users.docs == before


@pytest.mark.parametrize("password", ["short", "Synthetic-original-password-2026", "a" * 73, "🔒" * 20])
def test_password_policy_and_bcrypt_byte_limit_leave_token_unconsumed(db, password):
    unused, token, send = issue(db)
    with pytest.raises(HTTPException): run(recovery.complete_reset(db, token, password, "127.0.0.8"))
    assert db.password_resets.docs[0]["enabled"] is True
    assert not db.password_resets.docs[0]["used_at"]
    assert not db.integrity_locks.docs


def test_public_http_recovery_routes_need_no_session_and_do_not_issue_tokens(db):
    from server import app
    from routes import auth_routes
    with patch("database.get_db", return_value=db), patch.object(auth_routes, "get_db", return_value=db), patch.object(email_service, "send_email", AsyncMock(return_value={"status": "sent"})) as send:
        client = TestClient(app, base_url="https://127.0.0.1")  # No lifespan/startup: synthetic repositories only.
        response = client.post("/api/auth/password/forgot", json={"email": "staff@example.com"})
        assert response.status_code == 200 and response.json() == recovery.GENERIC
        token = re.search(r'#token=([A-Za-z0-9_-]+)', send.call_args.kwargs["html"]).group(1)
        changed = client.post("/api/auth/password/reset", json={"token": token, "new_password": "Synthetic-updated-password-2026"})
        assert changed.status_code == 200
        assert "access_token" not in changed.json()
        assert client.get("/api/employees").status_code == 401
        assert client.post("/api/auth/password/reset", json={"token": token, "new_password": "Different-synthetic-password"}).status_code == 400
        client.close()


def test_sensitive_email_never_queues_a_raw_link_or_logs_provider_error(db):
    production = ("production", {"smtp_host": "smtp.example.test", "password": "synthetic-mail-secret", "from_email": "no-reply@example.com"})
    with patch.object(email_service, "_resolve_smtp", AsyncMock(return_value=production)) as config, patch.object(email_service, "_attempt_send", AsyncMock(side_effect=RuntimeError("raw-reset-link-secret"))), patch.object(email_service, "_MIN_INTERVAL_S", 0):
        result = run(email_service.send_email(db, "staff@example.com", subject="Password reset", html="reset-token-synthetic", template_key="system.password_reset", sensitive=True))
    assert result["status"] == "failed"
    assert config.call_args.args[1] is True
    assert not db.email_retry_queue.docs
    assert "raw-reset-link-secret" not in str(db.email_log.docs)
    assert "reset-token-synthetic" not in str(db.email_log.docs)


def test_two_workers_cannot_consume_the_same_link(db):
    unused, token, send = issue(db)
    async def compete():
        return await asyncio.gather(recovery.complete_reset(db, token, "Synthetic-updated-password-2026", "127.0.0.8"), recovery.complete_reset(db, token, "Other-synthetic-password-2026", "127.0.0.9"), return_exceptions=True)
    results = run(compete())
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) for result in results) == 1
    assert sum(row.get("event") == "auth.password.reset_completed" for row in db.audit_logs.docs) == 1
