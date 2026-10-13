from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, get_authenticated_user, resolve_authenticated_employee,
    password_change_required, token_invalidated,
    ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_HOURS,
)
from utils.security import (
    is_locked_out, record_login_failure, clear_login_attempts,
    rate_limit, client_ip,
    validate_password_policy,
    revoke_refresh_jti, is_jti_revoked, revoke_all_user_refresh_tokens,
    record_audit, PASSWORD_HISTORY_KEEP,
)
import jwt
import os
from utils.employee_integrity import email_matches, resolve_user_employee, employee_key

router = APIRouter(prefix="/auth", tags=["auth"])

# Authentication cookies are HTTPS-only, including restricted first-login sessions.
_COOKIE_KW = dict(httponly=True, secure=True, samesite="none", path="/")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "employee"


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    db = get_db()
    email = req.email.lower().strip()
    ip = client_ip(request)

    # ─── Per-IP rate-limit on the login route ─── (15 attempts / 5 minutes)
    if rate_limit(f"login:{ip}", max_hits=15, window_seconds=300):
        await record_audit(db, actor_id=None, actor_email=email, event="auth.login.rate_limited",
                            ip=ip, outcome="blocked")
        raise HTTPException(status_code=429,
                             detail="Too many login attempts from this address. Please try again in a few minutes.")

    # ─── Account lockout ─── (5 failed attempts in 15 min → 15 min cool-down)
    cooldown = is_locked_out(email, ip)
    if cooldown:
        await record_audit(db, actor_id=None, actor_email=email, event="auth.login.locked_out",
                            ip=ip, outcome="blocked", detail={"cooldown_s": cooldown})
        raise HTTPException(status_code=423,
                             detail=f"Account temporarily locked due to repeated failed sign-ins. Try again in {cooldown // 60 + 1} minute(s).")

    matches = await email_matches(db.users, "email", email)
    user = matches[0] if len(matches) == 1 else None
    if not user or user.get("is_active") is False or not verify_password(req.password, user.get("password_hash", "")):
        remaining = record_login_failure(email, ip)
        await record_audit(db, actor_id=str(user["_id"]) if user else None,
                            actor_email=email, event="auth.login.failure",
                            ip=ip, outcome="failure",
                            detail={"remaining_attempts": remaining})
        # Generic error — do not leak whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    must_change = password_change_required(user)
    # An account can change its own credential even if its employee link needs
    # review. It still cannot use protected functionality with an invalid link.
    employee = await resolve_user_employee(db, user) if not must_change else None

    # Successful credential check.
    clear_login_attempts(email, ip)

    user_id = str(user["_id"])
    refresh_token, refresh_jti = create_refresh_token(user_id, user.get("password_changed_at"))
    access_token = create_access_token(user_id, email, user["role"], user.get("password_changed_at"), refresh_jti)

    response.set_cookie("access_token", access_token,
                        max_age=ACCESS_TOKEN_MINUTES * 60, **_COOKIE_KW)
    response.set_cookie("refresh_token", refresh_token,
                        max_age=REFRESH_TOKEN_HOURS * 3600, **_COOKIE_KW)

    await record_audit(db, actor_id=user_id, actor_email=email,
                        event="auth.login.success", ip=ip, outcome="success")

    identity = {
        "id": user_id,
        "email": email,
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "must_change_password": must_change,
    }
    if must_change:
        return identity
    return {
        **identity,
        "department": user.get("department", ""),
        "employee_id": employee_key(employee) if employee else None,
        "employee_reference_ids": list({employee_key(employee), str(employee["_id"])}) if employee else [],
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """End the current token pair, including copied access/bearer tokens."""
    db = get_db()
    rt = request.cookies.get("refresh_token")
    user_id = None
    access = request.cookies.get("access_token")
    if not access and request.headers.get("Authorization", "").startswith("Bearer "):
        access = request.headers["Authorization"][7:]
    for token, token_type in ((access, "access"), (rt, "refresh")):
        if not token:
            continue
        try:
            payload = jwt.decode(token, os.environ["JWT_SECRET"],
                                  algorithms=["HS256"], options={"verify_exp": False})
            if payload.get("type") != token_type or not isinstance(payload.get("sub"), str) or not ObjectId.is_valid(payload["sub"]):
                continue
            user_id = payload.get("sub")
            await revoke_refresh_jti(db, payload.get("jti", ""), user_id, reason="logout" if token_type == "refresh" else "logout_access")
            if token_type == "access":
                if payload.get("sid"):
                    await revoke_refresh_jti(db, payload["sid"], user_id, reason="logout")
                if not payload.get("jti"):
                    # Old access JWTs have no per-token identifier. The existing
                    # per-user cutoff is the safe backwards-compatible fallback.
                    await revoke_all_user_refresh_tokens(db, user_id)
        except jwt.InvalidTokenError:
            pass
    response.delete_cookie("access_token", **_COOKIE_KW)
    response.delete_cookie("refresh_token", **_COOKIE_KW)
    if user_id:
        await record_audit(db, actor_id=user_id, actor_email=None,
                            event="auth.logout", ip=client_ip(request), outcome="success")
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(request: Request):
    user = await get_authenticated_user(request)
    if user["must_change_password"]:
        return {key: user.get(key) for key in ("id", "email", "full_name", "role", "must_change_password")}
    return await resolve_authenticated_employee(user, get_db())


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    db = get_db()
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"],
                             options={"require": ["sub", "iat", "exp", "type", "jti"]})
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        jti = payload.get("jti", "")
        if not isinstance(jti, str) or not jti or not isinstance(payload["sub"], str) or not ObjectId.is_valid(payload["sub"]):
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        # Rotation: previous JTI must not have been used (revoked yet).
        if await is_jti_revoked(db, jti):
            raise HTTPException(status_code=401, detail="Refresh token already used.")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or user.get("is_active") is False:
            raise HTTPException(status_code=401, detail="User not found")
        if await token_invalidated(db, user, payload):
            raise HTTPException(status_code=401, detail="Session invalidated, please sign in again.")
        # Burn the old JTI immediately (rotation).
        await revoke_refresh_jti(db, jti, str(user["_id"]), reason="rotated")
        # Issue a fresh pair.
        new_refresh, _new_jti = create_refresh_token(str(user["_id"]), user.get("password_changed_at"))
        access = create_access_token(str(user["_id"]), user["email"], user["role"], user.get("password_changed_at"), _new_jti)
        response.set_cookie("access_token", access,
                            max_age=ACCESS_TOKEN_MINUTES * 60, **_COOKIE_KW)
        response.set_cookie("refresh_token", new_refresh,
                            max_age=REFRESH_TOKEN_HOURS * 3600, **_COOKIE_KW)
        return {"message": "Token refreshed", "must_change_password": password_change_required(user)}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/password/change")
async def change_password(req: PasswordChangeRequest, request: Request, response: Response):
    """Authenticated password change with policy enforcement (≥12 chars, breach
    screen, no reuse of last 5). On success: invalidates all outstanding sessions
    so the user must re-authenticate on every device."""
    user = await get_authenticated_user(request)
    db = get_db()
    db_user = await db.users.find_one({"_id": ObjectId(user["id"])})
    if not db_user or not verify_password(req.current_password,
                                            db_user.get("password_hash", "")):
        await record_audit(db, actor_id=user["id"], actor_email=user.get("email"),
                            event="auth.password.change_denied", ip=client_ip(request),
                            outcome="failure", detail={"reason": "current_password_invalid"})
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    history = db_user.get("password_history") or []
    # Include current hash in history check so users can't immediately re-set it.
    full_history = [db_user.get("password_hash")] + history
    validate_password_policy(req.new_password, full_history)

    new_hash = hash_password(req.new_password)
    now = datetime.now(timezone.utc).isoformat()
    new_history = ([db_user.get("password_hash")] + history)[:PASSWORD_HISTORY_KEEP]

    changed = await db.users.update_one(
        {"_id": db_user["_id"], "password_hash": db_user.get("password_hash")},
        {"$set": {"password_hash": new_hash,
                  "password_history": new_history,
                  "password_changed_at": now,
                  "must_change_password": False}},
    )
    if changed.modified_count != 1:
        raise HTTPException(status_code=409, detail="Password changed concurrently. Please sign in again.")
    # Force re-login on all devices (incl. current one).
    await revoke_all_user_refresh_tokens(db, str(db_user["_id"]))
    response.delete_cookie("access_token", **_COOKIE_KW)
    response.delete_cookie("refresh_token", **_COOKIE_KW)
    await record_audit(db, actor_id=str(db_user["_id"]), actor_email=db_user.get("email"),
                        event="auth.password.changed", ip=client_ip(request),
                        outcome="success")
    return {"message": "Password updated. Please sign in again."}
