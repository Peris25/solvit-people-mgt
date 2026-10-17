"""Own-account MFA recovery surface; protected administration stays gated."""
import time
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr
from database import get_db
from utils import mfa
from utils.auth import get_authenticated_user, create_access_token, create_refresh_token, resolve_authenticated_employee
from utils.employee_integrity import integrity_write, tenant_of
from routes.auth_routes import _COOKIE_KW, ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_HOURS

async def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

router = APIRouter(prefix="/auth/mfa", tags=["authentication"], dependencies=[Depends(no_store)])

class PasswordProof(BaseModel):
    password: SecretStr

class CodeProof(BaseModel):
    code: SecretStr

class Verification(BaseModel):
    code: SecretStr | None = None
    recovery_code: SecretStr | None = None

class ResetProof(PasswordProof):
    reference: str

async def authenticated(request):
    user = await get_authenticated_user(request)
    if user["must_change_password"]:
        raise HTTPException(403, detail={"code":"password_change_required", "message":"Change your password first"})
    return user

async def complete_session(db, user, request, response, generation):
    old = getattr(request.state, "mfa_payload", {})
    # A successful proof never extends the password-authenticated session age.
    started = old.get("sst", old.get("iat", time.time()))
    stamp = time.time()
    refresh, family = create_refresh_token(str(user["_id"]), user.get("password_changed_at"), started, mfa_verified=True, mfa_generation=generation, mfa_at=stamp, role=user["role"], session_cutoff=user.get("sessions_invalidated_at"))
    access = create_access_token(str(user["_id"]), user["email"], user["role"], user.get("password_changed_at"), family, started, True, generation, stamp, session_cutoff=user.get("sessions_invalidated_at"))
    # End the restricted/current pair; copied partial JWTs cannot act as proof.
    from utils.security import revoke_refresh_jti
    if old.get("jti"): await revoke_refresh_jti(db, old["jti"], str(user["_id"]), reason="mfa_upgraded")
    if old.get("sid"): await revoke_refresh_jti(db, old["sid"], str(user["_id"]), reason="logout")
    response.set_cookie("access_token", access, max_age=ACCESS_TOKEN_MINUTES*60, **_COOKIE_KW)
    response.set_cookie("refresh_token", refresh, max_age=REFRESH_TOKEN_HOURS*3600, **_COOKIE_KW)
    identity = {key:user.get(key) for key in ("email","full_name","role","department","solver_id")}
    try:
        linked = await resolve_authenticated_employee({**user, "id":str(user["_id"])}, db)
    except HTTPException as error:
        if error.status_code != 409: raise
        # Security setup must not lose recovery codes because an unrelated
        # employee link needs reconciliation. Business routes still fail closed.
        linked = {}
        identity["employee_link_needs_review"] = True
    identity.update(id=str(user["_id"]), employee_id=linked.get("employee_id"), employee_reference_ids=linked.get("employee_reference_ids"),
        must_change_password=False, mfa_required=True, mfa_enrolled=True, mfa_verified=True, mfa_action=None)
    return identity

@router.get("/status")
async def status(request: Request):
    user = await authenticated(request)
    row = await mfa.state(get_db(), user)
    return {key:user.get(key) for key in ("mfa_required","mfa_enrolled","mfa_verified","mfa_action")} | {
        "configured":mfa.configured(), "privileged":mfa.privileged(user), "rollout":mfa.mode(),
        "can_reset_other":mfa.base_role(user.get("role"))=="it_admin" and bool(user.get("mfa_verified")),
        "recovery_codes_remaining":len((row or {}).get("recovery_hashes") or []),
        "support":"Use a saved recovery code or contact IT for verified account recovery. Never share codes or setup keys."}

@router.post("/enroll")
async def enroll(body: PasswordProof, request: Request):
    actor = await authenticated(request); db=get_db()
    async with integrity_write(db):
        user = await mfa.fresh_user(db, actor)
        return await mfa.begin(db, user, actor, body.password.get_secret_value())

@router.post("/confirm")
async def confirm(body: CodeProof, request: Request, response: Response):
    actor = await authenticated(request); db=get_db()
    async with integrity_write(db):
        user = await mfa.fresh_user(db, actor)
        generation, codes = await mfa.confirm(db, user, body.code.get_secret_value())
        identity = await complete_session(db, user, request, response, generation)
    return {"user":identity, "recovery_codes":codes}

@router.post("/verify")
async def verify(body: Verification, request: Request, response: Response):
    actor = await authenticated(request); db=get_db()
    async with integrity_write(db):
        user = await mfa.fresh_user(db, actor)
        generation = await mfa.verify(db,user,body.code.get_secret_value() if body.code else None,body.recovery_code.get_secret_value() if body.recovery_code else None)
        return await complete_session(db,user,request,response,generation)

@router.post("/recovery-codes")
async def recovery_codes(body: PasswordProof, request: Request):
    actor = await authenticated(request); db=get_db()
    async with integrity_write(db):
        user = await mfa.fresh_user(db, actor)
        return {"recovery_codes":await mfa.rotate_recovery(db,user,actor,body.password.get_secret_value())}

@router.post("/reset/{user_id}")
async def reset(user_id: str, body: ResetProof, request: Request):
    actor = await authenticated(request); db=get_db()
    if not ObjectId.is_valid(user_id): raise HTTPException(404,"Account not found")
    async with integrity_write(db):
        user = await mfa.fresh_user(db, actor)
        target = await db.users.find_one({"_id":ObjectId(user_id)})
        if not target or tenant_of(target)!=tenant_of(user): raise HTTPException(404,"Account not found")
        await mfa.reset_other(db,user,actor,target,body.password.get_secret_value(),body.reference)
    return {"message":"MFA reset recorded. All prior sessions are invalid; the account must sign in and enroll again."}
