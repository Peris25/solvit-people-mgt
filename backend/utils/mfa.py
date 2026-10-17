"""RFC 6238 TOTP, encrypted enrolment and persistent, serialized proof state.

No provider calls, plaintext stored secrets, credential logging or automatic
rollout. All writers run under the existing cross-worker integrity lock.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode
from fastapi import HTTPException
from bson import ObjectId
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from utils.employee_integrity import tenant_of

PRIVILEGED = {"hr_admin", "hr_manager", "finance", "it_admin", "executive"}
STEP = 30
WINDOW = 15 * 60
PENDING_SECONDS = 5 * 60
CHALLENGE_SECONDS = 5 * 60
RECENT_SECONDS = 5 * 60


def base_role(role):
    from utils.access_matrix import CUSTOM_ROLE_DEFINITIONS
    seen = set()
    while role in CUSTOM_ROLE_DEFINITIONS:
        if role in seen: raise HTTPException(403, "Role configuration needs review")
        seen.add(role)
        role = CUSTOM_ROLE_DEFINITIONS[role].get("inherits_from")
    return role


def privileged(user):
    from utils.access_matrix import get_module_access
    role = user.get("role")
    if base_role(role) in PRIVILEGED: return True
    # Runtime/custom grants must not turn a base account into an MFA exception.
    return any((get_module_access(module, role) or {}).get("level") == "Full"
               for module in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M10", "M12", "M14", "M16", "M19"))


def mode():
    value = os.environ.get("MFA_ENFORCEMENT", "optional")
    if value not in {"optional", "privileged"}:
        raise HTTPException(503, "MFA rollout configuration needs administrator review")
    return value


def cipher():
    values = [x.strip() for x in os.environ.get("MFA_ENCRYPTION_KEYS", "").split(",") if x.strip()]
    try:
        if not values or len(values) > 5: raise ValueError()
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{43}=", value) for value in values): raise ValueError()
        keys = [base64.urlsafe_b64decode(value) for value in values]
        if any(len(key) != 32 for key in keys): raise ValueError()
        return keys
    except (ValueError, UnicodeError):
        raise HTTPException(503, "MFA encryption is not configured; contact IT support")


def configured():
    try: cipher(); return True
    except HTTPException: return False


def encrypt_secret(user, secret):
    content = json.dumps({"user": str(user["_id"]), "tenant": tenant_of(user), "secret": secret}).encode()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(cipher()[0]).encrypt(nonce, content, b"solvit-mfa-v1")
    return "v1." + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_secret(user, value):
    keys = cipher()
    try:
        if not isinstance(value, str) or not value.startswith("v1."): raise ValueError()
        encrypted = base64.urlsafe_b64decode(value[3:])
        if len(encrypted) < 29: raise ValueError()
        content = None
        for key in keys:
            try:
                content = AESGCM(key).decrypt(encrypted[:12], encrypted[12:], b"solvit-mfa-v1")
                break
            except InvalidTag: continue
        if content is None: raise ValueError()
        data = json.loads(content)
        if data["user"] != str(user["_id"]) or data["tenant"] != tenant_of(user): raise ValueError()
        if not isinstance(data["secret"], str) or not re.fullmatch(r"[A-Z2-7]{32}", data["secret"]): raise ValueError()
        return data["secret"]
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        raise HTTPException(503, "MFA credentials need administrator review")


def totp(secret, counter, digits=6, algorithm="sha1"):
    key = base64.b32decode(secret + "=" * ((-len(secret)) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), algorithm).digest()
    offset = digest[-1] & 15
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return str(number % (10 ** digits)).zfill(digits)


def matching_counter(secret, code, last=-1, timestamp=None):
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code): return None
    current = int(time.time() if timestamp is None else timestamp) // STEP
    matches = [n for n in (current - 1, current, current + 1) if n >= 0 and n > last and hmac.compare_digest(totp(secret, n), code)]
    return max(matches) if matches else None


async def state(db, user):
    row = await db.auth_mfa.find_one({"_id": str(user["_id"])})
    if row and tenant_of(row) != tenant_of(user): raise HTTPException(409, "MFA identity needs review")
    return row


def session_status(user, row, payload):
    enrolled = bool(row and row.get("enabled"))
    required = enrolled or bool(row and row.get("required")) or mode() == "privileged" and privileged(user)
    verified = bool(enrolled and payload.get("mfa") is True and payload.get("mver") == row.get("generation"))
    return {"mfa_required": bool(required), "mfa_enrolled": enrolled, "mfa_verified": verified,
            "mfa_action": ("verify" if enrolled else "enroll") if required and not verified else None,
            "_mfa_at": payload.get("mat") if verified else None, "_mfa_generation": payload.get("mver")}


def ensure_recent(user):
    try:
        recent = user.get("mfa_verified") is True and 0 <= time.time() - float(user.get("_mfa_at")) <= RECENT_SECONDS
    except (ValueError, TypeError): recent = False
    if not recent: raise HTTPException(403, "Sign in again and verify MFA before changing security settings")


async def fresh_user(db, authenticated):
    from utils.auth import password_state
    user = await db.users.find_one({"_id": ObjectId(str(authenticated["_id"]))})
    if not user or user.get("is_active") is False or tenant_of(user) != tenant_of(authenticated):
        raise HTTPException(401, "Session is unavailable")
    if password_state(user.get("password_changed_at")) != password_state(authenticated.get("password_changed_at")):
        raise HTTPException(401, "Sign in again before changing security settings")
    if user.get("role") != authenticated.get("role") or user.get("sessions_invalidated_at") != authenticated.get("sessions_invalidated_at"):
        raise HTTPException(401, "Account permissions changed; sign in again")
    row = await state(db, user)
    if row and row.get("generation") and authenticated.get("_mfa_generation") != row["generation"]:
        raise HTTPException(401, "MFA changed; sign in again")
    return user


async def create_state(db, user):
    row = await state(db, user)
    if row is None:
        row = {"_id": str(user["_id"]), "tenant_id": tenant_of(user), "enabled": False, "generation": None,
               "failures": 0, "window_started": time.time(), "locked_until": 0}
        await db.auth_mfa.insert_one(row)
    return row


def check_limit(row):
    if float(row.get("locked_until") or 0) > time.time():
        raise HTTPException(429, "Too many MFA attempts. Wait 15 minutes and try again")


async def failure(db, row):
    now = time.time()
    count = int(row.get("failures") or 0) if now - float(row.get("window_started") or 0) < WINDOW else 0
    started = row.get("window_started") if count else now
    count += 1
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": {"failures": count, "window_started": started,
        "locked_until": now + WINDOW if count >= 5 else 0}})
    await db.audit_logs.insert_one({"tenant_id":tenant_of(row), "actor_id":row["_id"], "event":"auth.mfa.denied", "timestamp":datetime.now(timezone.utc).isoformat()})
    raise HTTPException(400, "The security verification was not accepted")


async def password_proof(db, user, row, password):
    from utils.auth import verify_password
    check_limit(row)
    if not isinstance(password, str) or not verify_password(password, user.get("password_hash", "")):
        await failure(db, row)


def recovery_hash(user, code):
    normalized = str(code).replace("-", "").replace(" ", "").upper()
    return hashlib.sha256((str(user["_id"]) + ":" + normalized).encode()).hexdigest()


def recovery_codes(user):
    values = [secrets.token_hex(16).upper() for _ in range(10)]
    return ["-".join(value[n:n+8] for n in range(0,32,8)) for value in values], [recovery_hash(user, value) for value in values]


async def security_audit(db, actor, event, target=None, reference=None):
    # Never include OTPs, passwords, secrets, URI or recovery values in evidence.
    await db.audit_logs.insert_one({"tenant_id": tenant_of(actor), "actor_id": str(actor["_id"]),
        "event": event, "entity_id": str(target or actor["_id"]), "reference": reference,
        "timestamp": datetime.now(timezone.utc).isoformat()})


async def begin(db, user, authenticated, password):
    row = await create_state(db, user)
    await password_proof(db, user, row, password)
    if row.get("enabled"): ensure_recent(authenticated)
    # New URI/secret is returned only here, after fresh password proof. Existing
    # live secret remains effective until the replacement is confirmed.
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    encrypted = encrypt_secret(user, secret)
    await security_audit(db, user, "auth.mfa.enrollment_started")
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": {"pending_secret": encrypted,
        "pending_until": time.time() + PENDING_SECONDS, "pending_id": str(uuid.uuid4())}})
    label = quote("Solvit People:" + user.get("email", "Account"), safe="")
    uri = "otpauth://totp/" + label + "?" + urlencode({"secret": secret, "issuer": "Solvit People", "algorithm": "SHA1", "digits": 6, "period": STEP})
    return {"secret": secret, "otpauth_uri": uri, "expires_in": PENDING_SECONDS}


async def confirm(db, user, code):
    row = await state(db, user)
    if not row: raise HTTPException(409, "Start MFA enrollment first")
    check_limit(row)
    if not row.get("pending_secret") or float(row.get("pending_until") or 0) < time.time():
        raise HTTPException(409, "Enrollment expired. Start enrollment again")
    secret = decrypt_secret(user, row["pending_secret"])
    counter = matching_counter(secret, code)
    if counter is None: await failure(db, row)
    values, hashes = recovery_codes(user)
    generation = str(uuid.uuid4())
    await security_audit(db, user, "auth.mfa.enrolled")
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": {"enabled": True, "required": True,
        "secret": row["pending_secret"], "generation": generation, "last_counter": counter,
        "recovery_hashes": hashes, "pending_secret": None, "pending_until": 0,
        "failures": 0, "locked_until": 0, "enabled_at": datetime.now(timezone.utc).isoformat()}})
    return generation, values


async def verify(db, user, code=None, recovery=None):
    row = await state(db, user)
    if not row or not row.get("enabled"): raise HTTPException(409, "Enroll an authenticator first")
    check_limit(row)
    update = {"failures": 0, "locked_until": 0}
    if bool(code) == bool(recovery): raise HTTPException(422, "Supply an authenticator code or one recovery code")
    if code:
        secret = decrypt_secret(user, row.get("secret"))
        counter = matching_counter(secret, code, int(row.get("last_counter", -1)))
        if counter is None: await failure(db, row)
        update["last_counter"] = counter
    else:
        digest = recovery_hash(user, recovery)
        hashes = row.get("recovery_hashes") or []
        match = next((value for value in hashes if hmac.compare_digest(value, digest)), None)
        if not match: await failure(db, row)
        update["recovery_hashes"] = [value for value in hashes if value != match]
    await security_audit(db, user, "auth.mfa.recovery_used" if recovery else "auth.mfa.verified")
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": update})
    return row["generation"]


async def rotate_recovery(db, user, authenticated, password):
    ensure_recent(authenticated)
    row = await state(db, user)
    if not row or not row.get("enabled"): raise HTTPException(409, "MFA is not enrolled")
    await password_proof(db, user, row, password)
    values, hashes = recovery_codes(user)
    await security_audit(db, user, "auth.mfa.recovery_rotated")
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": {"recovery_hashes": hashes}})
    return values


async def reset_other(db, actor, authenticated, target, password, reference):
    ensure_recent(authenticated)
    if base_role(actor.get("role")) != "it_admin" or str(target["_id"]) == str(actor["_id"]) or tenant_of(target) != tenant_of(actor):
        raise HTTPException(403, "Only verified IT administrators may reset another account in their company")
    if not isinstance(reference, str) or not 8 <= len(reference.strip()) <= 200:
        raise HTTPException(422, "An approved support ticket or recovery reference is required")
    actor_state = await state(db, actor)
    await password_proof(db, actor, actor_state, password)
    row = await create_state(db, target)
    await security_audit(db, actor, "auth.mfa.admin_reset", target["_id"], reference.strip())
    await db.auth_mfa.update_one({"_id": row["_id"]}, {"$set": {"enabled": False, "required": True,
        "generation": str(uuid.uuid4()), "secret": None, "pending_secret": None, "pending_until": 0,
        "recovery_hashes": [], "last_counter": -1, "failures": 0, "locked_until": 0}})


async def password_lockout(db, user):
    row = await db.auth_login_limits.find_one({"_id": str(user["_id"])})
    if row and float(row.get("locked_until") or 0) > time.time():
        raise HTTPException(423, "Sign-in is temporarily locked. Wait 15 minutes and try again")


async def password_failure(db, user):
    # Caller serializes with the same persistent lock as other auth mutations.
    row = await db.auth_login_limits.find_one({"_id": str(user["_id"])})
    now = time.time()
    if row is None:
        row = {"_id": str(user["_id"]), "tenant_id": tenant_of(user), "failures": 0, "window_started": now}
        await db.auth_login_limits.insert_one(row)
    count = int(row.get("failures") or 0) if now - float(row.get("window_started") or 0) < WINDOW else 0
    count += 1
    await db.auth_login_limits.update_one({"_id": row["_id"]}, {"$set": {"failures": count,
        "window_started": row.get("window_started") if count > 1 else now,
        "locked_until": now + WINDOW if count >= 5 else row.get("locked_until", 0)}})


async def clear_password_failures(db, user):
    await db.auth_login_limits.update_one({"_id": str(user["_id"])}, {"$set": {"failures": 0, "locked_until": 0, "window_started": time.time()}})
