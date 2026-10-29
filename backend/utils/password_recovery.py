"""One-use email recovery. Raw reset credentials are never persisted or returned."""
import hashlib
import html
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from utils.auth import hash_password
from utils.employee_integrity import email_matches, integrity_write, normalize_email
from utils.security import validate_password_policy, PASSWORD_HISTORY_KEEP, record_audit

GENERIC = {"message": "If an eligible account exists, a password reset link will be sent. Check your work email or contact IT for help."}


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def snapshot(user):
    return digest("|".join(str(user.get(key) or "") for key in (
        "password_hash", "password_changed_at", "sessions_invalidated_at", "email", "role")))


def frontend_origin():
    value = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return None
    return value


async def allowed(db, key, limit):
    # Caller holds the persistent cross-worker integrity lock. Mongo _id is the
    # existing uniqueness constraint; no index or migration is installed here.
    key = "recovery:" + digest(key)
    bucket = int(now().timestamp()) // 900
    row = await db.password_reset_limits.find_one({"_id": key})
    hits = row.get("hits", 0) if row and row.get("bucket") == bucket else 0
    if hits >= limit:
        return False
    await db.password_reset_limits.update_one({"_id": key}, {"$set": {"bucket": bucket, "hits": hits + 1, "updated_at": now().isoformat()}}, upsert=True)
    return True


async def request_reset(db, email, ip, background=None):
    try:
        email = normalize_email(email)
    except HTTPException:
        return dict(GENERIC)
    origin = frontend_origin()
    from utils.runtime_controls import outbound_email_enabled
    try:
        async with integrity_write(db):
            if not await allowed(db, "ip:" + ip, 10) or not await allowed(db, "email:" + email, 3):
                return dict(GENERIC)
            matches = await email_matches(db.users, "email", email)
            if len(matches) != 1 or matches[0].get("is_active") is False or not origin or not outbound_email_enabled():
                return dict(GENERIC)
            user = matches[0]
            token = secrets.token_urlsafe(32)
            token_hash = digest(token)
            await db.password_resets.update_one({"_id": str(user["_id"])}, {"$set": {
                "token_hash": token_hash, "snapshot": snapshot(user), "enabled": False,
                "used_at": None, "created_at": now().isoformat(),
                "expires_at": (now() + timedelta(minutes=15)).isoformat(),
            }}, upsert=True)
        if background is not None:
            background.add_task(deliver_reset, db, str(user["_id"]), email, token, token_hash, origin, ip)
        else:
            await deliver_reset(db, str(user["_id"]), email, token, token_hash, origin, ip)
    except Exception:
        # Do not disclose account existence, transport configuration or tokens.
        await record_audit(db, actor_id=None, actor_email=None, event="auth.password.reset_request_unavailable", ip=ip, outcome="failure")
    return dict(GENERIC)


async def deliver_reset(db, user_id, email, token, token_hash, origin, ip):
    # In-process, event-driven delivery runs after the generic response. Tokens
    # are never queued durably; interrupted delivery requires a fresh request.
    try:
        link = origin + "/reset-password#token=" + token
        from utils.email_service import send_email
        result = await send_email(db, to=email, subject="Reset your Solvit People password",
            html='<p>A password reset was requested for your Solvit People account.</p>'
                 '<p><a href="' + html.escape(link, quote=True) + '">Reset password</a></p>'
                 '<p>This link expires in 15 minutes and works once. If you did not request it, ignore this email.</p>',
            template_key="system.password_reset", sensitive=True)
        await db.password_resets.update_one({"_id": user_id, "token_hash": token_hash},
                                           {"$set": {"enabled": result.get("status") == "sent"}})
        await record_audit(db, actor_id=user_id, actor_email=None,
                           event="auth.password.reset_requested", ip=ip,
                           outcome="success" if result.get("status") == "sent" else "failure")
    except Exception:
        await record_audit(db, actor_id=user_id, actor_email=None, event="auth.password.reset_delivery_unavailable", ip=ip, outcome="failure")


async def complete_reset(db, token, password, ip):
    invalid = HTTPException(400, "This reset link is invalid or expired. Request a new link.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token or ""):
        raise invalid
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(422, "Use a password no longer than 72 UTF-8 bytes.")
    async with integrity_write(db):
        if not await allowed(db, "complete-ip:" + ip, 15):
            raise HTTPException(429, "Too many reset attempts. Please try again later.")
        row = await db.password_resets.find_one({"token_hash": digest(token)})
        if not row or not row.get("enabled") or row.get("used_at"):
            raise invalid
        try:
            expired = datetime.fromisoformat(row["expires_at"]) <= now()
        except (KeyError, TypeError, ValueError):
            raise invalid
        if expired:
            raise invalid
        from bson import ObjectId
        if not ObjectId.is_valid(row["_id"]):
            raise invalid
        user = await db.users.find_one({"_id": ObjectId(row["_id"])})
        if not user or user.get("is_active") is False or row["snapshot"] != snapshot(user):
            raise invalid
        matches = await email_matches(db.users, "email", str(user.get("email") or "").strip().lower())
        if len(matches) != 1 or matches[0]["_id"] != user["_id"]:
            raise invalid
        history = [value for value in [user.get("password_hash")] + (user.get("password_history") or []) if isinstance(value, str) and value]
        validate_password_policy(password, history)
        changed_at = now().isoformat()
        changed = await db.users.update_one({"_id": user["_id"], "password_hash": user.get("password_hash"),
            "is_active": {"$ne": False}, "email": user.get("email"), "role": user.get("role"),
            "sessions_invalidated_at": user.get("sessions_invalidated_at"),
            "password_changed_at": user.get("password_changed_at")}, {"$set": {
                "password_hash": hash_password(password), "password_history": history[:PASSWORD_HISTORY_KEEP],
                "password_changed_at": changed_at, "sessions_invalidated_at": changed_at,
                "must_change_password": False,
            }})
        if changed.modified_count != 1:
            raise invalid
        await db.password_resets.update_one({"_id": row["_id"], "token_hash": row["token_hash"]},
                                           {"$set": {"enabled": False, "used_at": changed_at}})
        await record_audit(db, actor_id=str(user["_id"]), actor_email=None,
                           event="auth.password.reset_completed", ip=ip)
    return {"message": "Password updated. Please sign in again."}
