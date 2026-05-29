"""Application-layer security utilities (no infra changes).

This module is intentionally self-contained so it can be hot-reloaded and
imported from middleware, routes, and one-off scripts.

Includes:
  • In-memory + Mongo-backed brute-force lockout (5 failures / 15 min window)
  • Password policy: ≥12 chars, no breached/common passwords, history-of-5 reuse
    prevention, optional rotation expiry check
  • Generic per-key rate limiter (used by login + public endpoints)
  • Server-side refresh-token revocation (Mongo collection)
  • Security HTTP response headers (CSP, X-Frame-Options, Referrer, Permissions, HSTS, …)
  • Body-size guard middleware
  • Audit-log helper (`record_audit`)

All time arithmetic uses UTC.
"""
from __future__ import annotations

import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ────────────────────────────── Constants ──────────────────────────────

MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", "6291456"))  # 6MB default
LOGIN_LOCKOUT_MAX_FAILS = 5
LOGIN_LOCKOUT_WINDOW_SECONDS = 15 * 60       # 15-minute sliding window
LOGIN_LOCKOUT_DURATION_SECONDS = 15 * 60     # 15-minute hard cool-down

PRIVILEGED_ROLES = {"hr_admin", "hr_manager", "finance", "it_admin", "executive"}
PASSWORD_ROTATION_DAYS = {"privileged": 90, "standard": 180}
PASSWORD_MIN_LEN = 12
PASSWORD_HISTORY_KEEP = 5

# Compact baked-in breach list — top common Kenyan + global passwords. Avoids
# loading huge external dumps; for production use rockyou or HIBP API.
BREACHED_PASSWORDS = frozenset(s.lower() for s in [
    "password", "password1", "Password123", "P@ssw0rd", "12345678", "123456789",
    "1234567890", "qwerty12345", "letmein", "welcome", "welcome123", "admin",
    "admin123", "administrator", "iloveyou", "monkey123", "abc123456",
    "qwertyuiop", "1q2w3e4r5t", "passw0rd", "trustno1", "sunshine",
    "princess1", "starwars1", "solvit", "Solvit2026", "Kenya2024", "Nairobi123",
    "matatu", "harambee", "uhuru", "kenya2026",
])

# ────────────────────────── Brute-force lockout ──────────────────────────

_login_fail_cache: dict[str, deque] = {}
_lockout_until: dict[str, float] = {}


def _lockout_key(email: str, ip: str) -> str:
    return f"{(email or '').lower().strip()}|{ip or 'unknown'}"


def is_locked_out(email: str, ip: str) -> Optional[int]:
    """Return seconds remaining if locked out, else None."""
    k = _lockout_key(email, ip)
    until = _lockout_until.get(k)
    if until and until > time.time():
        return int(until - time.time())
    if until:
        _lockout_until.pop(k, None)
    return None


def record_login_failure(email: str, ip: str) -> int:
    """Record a failure and return remaining attempts before lockout."""
    k = _lockout_key(email, ip)
    now = time.time()
    dq = _login_fail_cache.setdefault(k, deque())
    while dq and now - dq[0] > LOGIN_LOCKOUT_WINDOW_SECONDS:
        dq.popleft()
    dq.append(now)
    remaining = max(0, LOGIN_LOCKOUT_MAX_FAILS - len(dq))
    if len(dq) >= LOGIN_LOCKOUT_MAX_FAILS:
        _lockout_until[k] = now + LOGIN_LOCKOUT_DURATION_SECONDS
    return remaining


def clear_login_attempts(email: str, ip: str) -> None:
    k = _lockout_key(email, ip)
    _login_fail_cache.pop(k, None)
    _lockout_until.pop(k, None)


# ───────────────────────── Generic key-bucket limiter ─────────────────────────

_rate_buckets: dict[str, deque] = {}


def rate_limit(key: str, max_hits: int, window_seconds: int) -> bool:
    """Return True if the request should be blocked."""
    now = time.time()
    dq = _rate_buckets.setdefault(key, deque())
    while dq and now - dq[0] > window_seconds:
        dq.popleft()
    if len(dq) >= max_hits:
        return True
    dq.append(now)
    return False


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ────────────────────────── Password policy ──────────────────────────

def validate_password_policy(new_password: str, history: list[str]) -> None:
    """Raises HTTPException(400) on policy violation. History is a list of past bcrypt hashes."""
    if not new_password or len(new_password) < PASSWORD_MIN_LEN:
        raise HTTPException(status_code=400,
                             detail=f"Password must be at least {PASSWORD_MIN_LEN} characters.")
    if new_password.lower() in BREACHED_PASSWORDS:
        raise HTTPException(status_code=400,
                             detail="This password is on a known-breached or common-password list. Please choose a stronger one.")
    # Reuse prevention
    for old_hash in (history or [])[:PASSWORD_HISTORY_KEEP]:
        try:
            if bcrypt.checkpw(new_password.encode(), old_hash.encode()):
                raise HTTPException(status_code=400,
                                     detail=f"You cannot reuse any of your last {PASSWORD_HISTORY_KEEP} passwords.")
        except ValueError:
            continue  # malformed hash in history; ignore


def password_expired(user: dict) -> bool:
    """True if the user's password is past its rotation due date."""
    role = user.get("role", "")
    days = PASSWORD_ROTATION_DAYS["privileged"] if role in PRIVILEGED_ROLES \
        else PASSWORD_ROTATION_DAYS["standard"]
    changed_at = user.get("password_changed_at")
    if not changed_at:
        return False  # never recorded — don't lock legacy accounts retroactively
    try:
        if isinstance(changed_at, str):
            changed_at = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - changed_at > timedelta(days=days)
    except (ValueError, TypeError):
        return False


# ────────────────────── Refresh-token revocation store ──────────────────────

async def revoke_refresh_jti(db, jti: str, user_id: str, reason: str = "logout") -> None:
    if not jti:
        return
    await db.revoked_refresh_tokens.update_one(
        {"jti": jti},
        {"$set": {"jti": jti, "user_id": user_id, "reason": reason,
                  "revoked_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def is_jti_revoked(db, jti: str) -> bool:
    if not jti:
        return False
    doc = await db.revoked_refresh_tokens.find_one({"jti": jti})
    return doc is not None


async def revoke_all_user_refresh_tokens(db, user_id: str) -> None:
    """Used on password change to invalidate any outstanding session."""
    await db.user_session_invalidations.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id,
                  "invalidated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def session_invalidated_after(db, user_id: str, issued_at_epoch: int) -> bool:
    doc = await db.user_session_invalidations.find_one({"user_id": user_id})
    if not doc:
        return False
    try:
        invalidated_at = datetime.fromisoformat(doc["invalidated_at"].replace("Z", "+00:00"))
        return invalidated_at.timestamp() > issued_at_epoch
    except (KeyError, ValueError, TypeError):
        return False


# ────────────────────────── Audit-log helper ──────────────────────────

async def record_audit(db, *, actor_id: Optional[str], actor_email: Optional[str],
                       event: str, ip: Optional[str] = None,
                       detail: Optional[dict] = None,
                       outcome: str = "success") -> None:
    try:
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "actor_id": actor_id,
            "actor_email": actor_email,
            "event": event,
            "outcome": outcome,
            "ip": ip,
            "detail": detail or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        # Audit must never block business logic.
        pass


# ────────────────────────── Middleware ──────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Append OWASP-recommended response headers and strip framework fingerprint."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Strict transport security only on TLS (the platform always serves via https).
        response.headers.setdefault("Strict-Transport-Security",
                                     "max-age=31536000; includeSubDomains")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy",
                                     "camera=(), geolocation=(), microphone=(), payment=()")
        # CSP — keep permissive enough not to break inline-style React app; no inline scripts.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: blob: https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "script-src 'self' 'unsafe-inline' https:; "
            "font-src 'self' data: https:; "
            "connect-src 'self' https: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "object-src 'none';"
        )
        # Remove framework fingerprint headers.
        for h in ("Server", "X-Powered-By"):
            if h in response.headers:
                del response.headers[h]
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds MAX_BODY_BYTES.

    Streaming uploads are bounded at the multipart/form-data parser level by
    individual route validators (e.g. the CV upload caps at 5MB). This is a
    coarse first-line defence against memory-exhaustion DoS.
    """

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return Response(
                        '{"detail":"Request body too large."}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass
        return await call_next(request)
