from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, get_current_user,
    ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_HOURS,
)
from utils.security import (
    is_locked_out, record_login_failure, clear_login_attempts,
    rate_limit, client_ip,
    validate_password_policy, password_expired,
    revoke_refresh_jti, is_jti_revoked, revoke_all_user_refresh_tokens,
    record_audit, PASSWORD_HISTORY_KEEP,
)
import jwt
import os

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie security — keep `secure=False` flag so the preview ingress (which
# terminates TLS upstream) can still set the cookie. The platform's external
# URL is always HTTPS, so this is safe in this hosting.
_COOKIE_KW = dict(httponly=True, secure=False, samesite="lax", path="/")


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

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        remaining = record_login_failure(email, ip)
        await record_audit(db, actor_id=str(user["_id"]) if user else None,
                            actor_email=email, event="auth.login.failure",
                            ip=ip, outcome="failure",
                            detail={"remaining_attempts": remaining})
        # Generic error — do not leak whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Successful credential check.
    clear_login_attempts(email, ip)

    # Optional: enforce rotation policy (warn-only by setting must_change flag — we
    # surface but do not hard-block here to avoid stranding legacy accounts that
    # have never recorded a `password_changed_at`).
    must_change = bool(user.get("must_change_password")) or password_expired(user)

    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email, user["role"])
    refresh_token, refresh_jti = create_refresh_token(user_id)

    response.set_cookie("access_token", access_token,
                        max_age=ACCESS_TOKEN_MINUTES * 60, **_COOKIE_KW)
    response.set_cookie("refresh_token", refresh_token,
                        max_age=REFRESH_TOKEN_HOURS * 3600, **_COOKIE_KW)

    await record_audit(db, actor_id=user_id, actor_email=email,
                        event="auth.login.success", ip=ip, outcome="success")

    return {
        "id": user_id,
        "email": email,
        "full_name": user.get("full_name", ""),
        "role": user["role"],
        "department": user.get("department", ""),
        "employee_id": user.get("employee_id", ""),
        "must_change_password": must_change,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Revoke the refresh token server-side and clear cookies."""
    db = get_db()
    rt = request.cookies.get("refresh_token")
    user_id = None
    if rt:
        try:
            payload = jwt.decode(rt, os.environ["JWT_SECRET"],
                                  algorithms=["HS256"], options={"verify_exp": False})
            user_id = payload.get("sub")
            await revoke_refresh_jti(db, payload.get("jti", ""), user_id or "", reason="logout")
        except jwt.InvalidTokenError:
            pass
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    if user_id:
        await record_audit(db, actor_id=user_id, actor_email=None,
                            event="auth.logout", ip=client_ip(request), outcome="success")
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    db = get_db()
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        jti = payload.get("jti", "")
        # Rotation: previous JTI must not have been used (revoked yet).
        if await is_jti_revoked(db, jti):
            raise HTTPException(status_code=401, detail="Refresh token already used.")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Burn the old JTI immediately (rotation).
        await revoke_refresh_jti(db, jti, str(user["_id"]), reason="rotated")
        # Issue a fresh pair.
        access = create_access_token(str(user["_id"]), user["email"], user["role"])
        new_refresh, _new_jti = create_refresh_token(str(user["_id"]))
        response.set_cookie("access_token", access,
                            max_age=ACCESS_TOKEN_MINUTES * 60, **_COOKIE_KW)
        response.set_cookie("refresh_token", new_refresh,
                            max_age=REFRESH_TOKEN_HOURS * 3600, **_COOKIE_KW)
        return {"message": "Token refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/password/change")
async def change_password(req: PasswordChangeRequest, request: Request, response: Response):
    """Authenticated password change with policy enforcement (≥12 chars, breach
    screen, no reuse of last 5). On success: invalidates all outstanding sessions
    so the user must re-authenticate on every device."""
    user = await get_current_user(request)
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

    await db.users.update_one(
        {"_id": db_user["_id"]},
        {"$set": {"password_hash": new_hash,
                  "password_history": new_history,
                  "password_changed_at": now,
                  "must_change_password": False}},
    )
    # Force re-login on all devices (incl. current one).
    await revoke_all_user_refresh_tokens(db, str(db_user["_id"]))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await record_audit(db, actor_id=str(db_user["_id"]), actor_email=db_user.get("email"),
                        event="auth.password.changed", ip=client_ip(request),
                        outcome="success")
    return {"message": "Password updated. Please sign in again."}
