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

# OWASP-aligned session controls — kept short to satisfy "absolute lifetime 12h"
# while preserving usability. Refresh tokens rotate (see auth_routes.refresh).
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_HOURS = int(os.environ.get("REFRESH_TOKEN_HOURS", "12"))


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


def create_access_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (token, jti). The jti is persisted server-side for rotation/revocation."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(hours=REFRESH_TOKEN_HOURS),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM), jti


async def get_current_user(request: Request) -> dict:
    from database import get_db
    from utils.security import session_invalidated_after
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        db = get_db()
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Honour password-change session invalidation.
        iat = payload.get("iat", 0)
        if await session_invalidated_after(db, str(user["_id"]), iat):
            raise HTTPException(status_code=401, detail="Session invalidated, please sign in again.")
        user["id"] = str(user["_id"])
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        user.pop("password_history", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


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
