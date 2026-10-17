import os
import uuid
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request
from bson import ObjectId

JWT_ALGORITHM = "HS256"
ROLES = ["hr_admin", "hr_manager", "line_manager", "finance", "employee",
         "solver", "executive", "it_admin", "board"]

# Short-lived access; refresh is bounded by a stable original session age.
ACCESS_TOKEN_MINUTES = min(15, max(1, int(os.environ.get("ACCESS_TOKEN_MINUTES", "15"))))
REFRESH_TOKEN_HOURS = min(24, max(1, int(os.environ.get("REFRESH_TOKEN_HOURS", "12"))))


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    # bcrypt default cost is 12 — meets policy.
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"),
                              hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def password_state(value):
    """Stable JWT snapshot of the existing password_changed_at field."""
    return value.isoformat() if isinstance(value, datetime) else str(value) if value is not None else None


def password_change_required(user: dict) -> bool:
    from utils.security import password_expired
    return bool(user.get("must_change_password")) or password_expired(user)


def create_access_token(user_id: str, email: str, role: str, password_changed_at=None, session_jti=None, session_started_at=None, mfa_verified=False, mfa_generation=None, mfa_at=None, session_cutoff=None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now.timestamp(),
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
        "jti": str(uuid.uuid4()),
        "sid": session_jti,
        "sst": session_started_at if session_started_at is not None else now.timestamp(),
        "pwd": password_state(password_changed_at),
        "mfa": mfa_verified is True,
        "mver": mfa_generation,
        "mat": mfa_at,
        "cut": password_state(session_cutoff),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, password_changed_at=None, session_started_at=None, session_id=None, mfa_verified=False, mfa_generation=None, mfa_at=None, role=None, session_cutoff=None) -> tuple[str, str]:
    """Returns (token, jti). The jti is persisted server-side for rotation/revocation."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "jti": jti,
        "sid": session_id or jti,
        "sst": session_started_at if session_started_at is not None else now.timestamp(),
        "iat": now.timestamp(),
        "exp": now + timedelta(hours=REFRESH_TOKEN_HOURS),
        "type": "refresh",
        "role": role,
        "pwd": password_state(password_changed_at),
        "mfa": mfa_verified is True,
        "mver": mfa_generation,
        "mat": mfa_at,
        "cut": password_state(session_cutoff),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM), jti


async def token_invalidated(db, user, payload) -> bool:
    """Check live password state, including tokens minted during a change race.

    Older JWTs without a password snapshot retain timestamp-based compatibility.
    The password timestamp is changed atomically with the hash and required flag,
    so invalidation does not depend on a later revocation-store write succeeding.
    """
    from utils.security import session_invalidated_after, is_jti_revoked
    if payload.get("jti") and await is_jti_revoked(db, payload["jti"]):
        return True
    if payload.get("sid"):
        session = await db.revoked_refresh_tokens.find_one({"jti": payload["sid"]})
        if session and session.get("reason") == "logout":
            return True
    if "pwd" in payload and payload["pwd"] != password_state(user.get("password_changed_at")):
        return True
    from utils import mfa
    row = await mfa.state(db, user)
    if row and row.get("generation") and payload.get("mver") != row["generation"]:
        return True
    if payload.get("role") is not None and payload["role"] != user.get("role"):
        return True
    if "cut" in payload and payload["cut"] != password_state(user.get("sessions_invalidated_at")):
        return True
    issued = float(payload["iat"])
    if payload.get("type") == "access" and datetime.now(timezone.utc).timestamp() - issued >= ACCESS_TOKEN_MINUTES * 60:
        return True
    # Refresh preserves the original session start; rotation cannot extend it.
    try:
        started = float(payload.get("sst", issued))
        hours = 8 if mfa.privileged(user) else 24 if user.get("role") == "solver" else 12
        if not 0 < started <= issued or datetime.now(timezone.utc).timestamp() - started >= hours * 3600:
            return True
        status = mfa.session_status(user, row, payload)
        if not password_change_required(user) and status["mfa_required"] and not status["mfa_verified"] and datetime.now(timezone.utc).timestamp() - started >= mfa.CHALLENGE_SECONDS:
            return True
    except (ValueError, TypeError):
        return True
    cutoff = user.get("sessions_invalidated_at")
    if cutoff:
        try:
            if datetime.fromisoformat(cutoff.replace("Z", "+00:00")).timestamp() >= issued: return True
        except (ValueError, TypeError, AttributeError): return True
    changed = user.get("password_changed_at")
    if changed:
        try:
            if isinstance(changed, str):
                changed = datetime.fromisoformat(changed.replace("Z", "+00:00"))
            if changed.tzinfo is None:
                changed = changed.replace(tzinfo=timezone.utc)
            if changed.timestamp() > issued:
                return True
        except (ValueError, TypeError, AttributeError):
            pass  # Preserve compatibility with malformed historical metadata.
    return await session_invalidated_after(db, str(user["_id"]), issued)


async def get_authenticated_user(request: Request) -> dict:
    """Authenticate only. Auth recovery handlers may call this directly.

    Business routes must use get_current_user, which enforces password completion.
    Do not make the exception depend on a URL or a client-supplied flag.
    """
    from database import get_db
    state = getattr(request, "state", None)
    cached = getattr(state, "authenticated_user", None) if state is not None else None
    if cached is not None:
        return cached
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM],
                             options={"require": ["sub", "iat", "exp", "type"]})
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        db = get_db()
        if not isinstance(payload["sub"], str) or not ObjectId.is_valid(payload["sub"]):
            raise HTTPException(status_code=401, detail="Invalid token subject")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or user.get("is_active") is False:
            raise HTTPException(status_code=401, detail="User not found")
        # Honour password-change session invalidation.
        if await token_invalidated(db, user, payload):
            raise HTTPException(status_code=401, detail="Session invalidated, please sign in again.")
        from utils import mfa
        user.update(mfa.session_status(user, await mfa.state(db, user), payload))
        if state is not None: state.mfa_payload = payload
        user["id"] = str(user["_id"])
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        user.pop("password_history", None)
        for secret in ("mfa_secret", "totp_secret", "mfa_pending_secret", "recovery_codes", "otp_secret", "refresh_token", "access_token"):
            user.pop(secret, None)
        user["must_change_password"] = password_change_required(user)
        if state is not None:
            state.authenticated_user = user
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def resolve_authenticated_employee(user, db):
    from utils.employee_integrity import resolve_user_employee, employee_key
    employee = await resolve_user_employee(db, user)
    user["employee_id"] = employee_key(employee) if employee else None
    user["employee_reference_ids"] = list({employee_key(employee), str(employee["_id"])}) if employee else []
    return user


async def require_password_change_completed(request: Request) -> dict:
    user = await get_authenticated_user(request)
    if user["must_change_password"]:
        raise HTTPException(status_code=403, detail={
            "code": "password_change_required",
            "message": "Change your password before accessing the application.",
        })
    if user.get("mfa_required") and not user.get("mfa_verified"):
        raise HTTPException(403, detail={"code": "mfa_required", "message": "Complete MFA before accessing the application.", "action": user.get("mfa_action")})
    if user.get('role') == 'solver':
        from database import get_db
        from utils.solver_access import own_solver
        from utils.solver_workflows import view
        record = await own_solver(get_db(), user)
        if view(record)['lifecycle_state'] not in {'Active', 'Registering'}:
            raise HTTPException(403, 'Solver application access is unavailable for this lifecycle state')
    return user


async def get_current_user(request: Request) -> dict:
    from database import get_db
    user = await require_password_change_completed(request)
    return await resolve_authenticated_employee(user, get_db())


def require_roles(*roles):
    async def checker(request: Request) -> dict:
        user = await get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


def format_doc(doc: dict) -> dict:
    if doc is None:
        return None
    doc["id"] = str(doc.get("_id", ""))
    doc["_id"] = str(doc.get("_id", ""))
    return doc
