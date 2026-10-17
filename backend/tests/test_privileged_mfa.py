"""Synthetic HTTP and real-Mongo MFA/session regressions; no external delivery."""
import asyncio
import base64
import hashlib
import json
import time
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
import jwt
import pytest
from bson import ObjectId
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server import app
from routes import auth_routes, mfa_routes
from utils import auth, mfa
from utils.access_matrix import RUNTIME_OVERRIDES, CUSTOM_ROLE_DEFINITIONS
from utils.employee_integrity import integrity_write
from .integrity_fakes import Database, Collection, employee, account

PASSWORD = "Original-local-security-password-2026"

@pytest.fixture(scope="module")
def password_hash(): return auth.hash_password(PASSWORD)

@pytest.fixture
def sut(monkeypatch, password_hash):
    monkeypatch.setenv("JWT_SECRET", "synthetic-local-mfa-signing-key-only")
    monkeypatch.setenv("MFA_ENFORCEMENT", "privileged")
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", Fernet.generate_key().decode())
    users={}
    for role in ("hr_admin","hr_manager","finance","it_admin","executive","employee","line_manager","solver"):
        user=account(email=role+"@example.com",role=role,password_hash=password_hash,is_active=True,
                     account_type="solver" if role=="solver" else "employee" if role=="employee" else "system",
                     employee_id="staff" if role=="employee" else None)
        user["id"]=str(user["_id"]);users[role]=user
    db=Database([employee("staff",email="employee@example.com")],list(users.values()))
    with ExitStack() as stack:
        stack.enter_context(patch("database.get_db",return_value=db))
        stack.enter_context(patch.object(auth_routes,"get_db",return_value=db))
        stack.enter_context(patch.object(mfa_routes,"get_db",return_value=db))
        stack.enter_context(patch.object(auth_routes,"rate_limit",return_value=False))
        stack.enter_context(patch.object(auth_routes,"is_locked_out",return_value=0))
        client=TestClient(app,base_url="http://127.0.0.1:18089")
        yield client,db,users
        client.close()


def login(sut,role="hr_admin"):
    client,_,_=sut;client.cookies.clear();client.headers.pop("Authorization",None)
    result=client.post("/api/auth/login",json={"email":role+"@example.com","password":PASSWORD})
    assert result.status_code==200,result.text
    return result


def enroll(sut,role="hr_admin"):
    client,db,users=sut;login(sut,role)
    started=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    assert started.status_code==200,started.text
    secret=started.json()["secret"]
    confirmed=client.post("/api/auth/mfa/confirm",json={"code":mfa.totp(secret,int(time.time())//30)})
    assert confirmed.status_code==200,confirmed.text
    return secret,confirmed.json()["recovery_codes"]


def authenticate_enrolled(sut,role,codes):
    login(sut,role)
    result=sut[0].post("/api/auth/mfa/verify",json={"recovery_code":codes.pop()})
    assert result.status_code==200,result.text
    return result

@pytest.mark.parametrize("timestamp,expected",[(59,"94287082"),(1111111109,"07081804"),(1111111111,"14050471"),(1234567890,"89005924"),(2000000000,"69279037"),(20000000000,"65353130")])
def test_rfc6238_sha1_reference_vectors(timestamp,expected):
    secret=base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert mfa.totp(secret,timestamp//30,digits=8)==expected

@pytest.mark.parametrize("role",["hr_admin","hr_manager","finance","it_admin","executive"])
def test_privileged_password_login_is_restricted_until_enrollment(sut,role):
    client,_,_=sut;response=login(sut,role)
    assert response.json()["mfa_required"] and response.json()["mfa_action"]=="enroll"
    for path in ("/api/access/matrix","/api/employees","/api/policies","/api/automation/notifications"):
        blocked=client.get(path)
        assert blocked.status_code==403 and blocked.json()["detail"]["code"]=="mfa_required"
    assert client.get("/api/auth/me").status_code==200
    assert client.get("/api/auth/mfa/status").status_code==200

@pytest.mark.parametrize("role",["employee","line_manager","solver"])
def test_nonprivileged_login_preserves_existing_behavior(sut,role):
    response=login(sut,role)
    assert not response.json()["mfa_required"]
    assert sut[0].get("/api/auth/me").status_code==200


def test_optional_rollout_does_not_lock_out_unenrolled_privileged_users(sut,monkeypatch):
    monkeypatch.setenv("MFA_ENFORCEMENT","optional")
    response=login(sut,"it_admin")
    assert not response.json()["mfa_required"]
    assert sut[0].get("/api/access/matrix").status_code==200
    assert sut[1].auth_mfa.docs==[]


def test_enrollment_encrypts_secret_and_recovery_values_never_enter_storage_or_audits(sut):
    client,db,users=sut;secret,codes=enroll(sut)
    row=db.auth_mfa.docs[0]
    assert secret not in str(db.auth_mfa.docs) and secret not in str(db.audit_logs.docs)
    assert mfa.decrypt_secret(users["hr_admin"],row["secret"])==secret
    assert len(codes)==10 and len(set(codes))==10
    assert all(code not in str(db.auth_mfa.docs)+str(db.audit_logs.docs) for code in codes)
    assert not row["pending_secret"] and row["enabled"]
    response=client.get("/api/auth/me")
    assert response.json()["mfa_verified"] is True
    assert secret not in response.text and "recovery_hashes" not in response.text
    assert client.get("/api/access/matrix").status_code==200


def test_status_never_returns_setup_or_recovery_secrets(sut):
    secret,codes=enroll(sut)
    result=sut[0].get("/api/auth/mfa/status")
    assert result.status_code==200 and result.json()["recovery_codes_remaining"]==10
    assert secret not in result.text and all(code not in result.text for code in codes)
    assert result.headers["cache-control"]=="no-store"


def test_enrollment_needs_current_password_and_confirmed_totp(sut):
    client,db,_=sut;login(sut)
    assert client.post("/api/auth/mfa/enroll",json={"password":"wrong"}).status_code==400
    assert not db.auth_mfa.docs[0].get("pending_secret")
    started=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    assert started.status_code==200
    assert client.get("/api/access/matrix").status_code==403
    assert client.post("/api/auth/mfa/confirm",json={"code":"not-a-code"}).status_code==400
    assert not db.auth_mfa.docs[0].get("enabled")


def test_enrollment_expires_without_replacing_a_live_authenticator(sut):
    client,db,_=sut;login(sut)
    started=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    db.auth_mfa.docs[0]["pending_until"]=time.time()-1
    assert client.post("/api/auth/mfa/confirm",json={"code":mfa.totp(started.json()["secret"],int(time.time())//30)}).status_code==409
    assert not db.auth_mfa.docs[0].get("enabled")


def test_enrolled_accounts_require_mfa_even_when_rollout_is_optional(sut,monkeypatch):
    enroll(sut);monkeypatch.setenv("MFA_ENFORCEMENT","optional")
    response=login(sut)
    assert response.json()["mfa_action"]=="verify"
    assert sut[0].get("/api/access/matrix").status_code==403


def test_totp_accepts_valid_new_step_and_rejects_replay_from_another_login(sut):
    client,db,_=sut;secret,_=enroll(sut)
    login(sut)
    code=mfa.totp(secret,int(time.time())//30+1)
    assert client.post("/api/auth/mfa/verify",json={"code":code}).status_code==200
    login(sut)
    assert client.post("/api/auth/mfa/verify",json={"code":code}).status_code==400
    assert client.get("/api/access/matrix").status_code==403


def test_totp_drift_is_bounded_and_previous_steps_cannot_be_reused():
    secret=base64.b32encode(b"synthetic-20-byte-key").decode().rstrip("=")
    now=1700000010;step=now//30
    for offset in (-1,0,1): assert mfa.matching_counter(secret,mfa.totp(secret,step+offset),timestamp=now)==step+offset
    assert mfa.matching_counter(secret,mfa.totp(secret,step+2),timestamp=now) is None
    assert mfa.matching_counter(secret,mfa.totp(secret,step),last=step,timestamp=now) is None


def test_persistent_attempt_limit_survives_new_logins_and_worker_local_cache_reset(sut):
    from utils import security
    client,db,_=sut;enroll(sut);login(sut)
    for _ in range(5): assert client.post("/api/auth/mfa/verify",json={"code":"invalid"}).status_code==400
    security._rate_buckets.clear();security._login_fail_cache.clear()
    login(sut)
    assert client.post("/api/auth/mfa/verify",json={"code":"invalid"}).status_code==429
    assert db.auth_mfa.docs[0]["locked_until"]>time.time()


def test_recovery_code_is_one_use_and_does_not_disable_authenticator(sut):
    client,db,_=sut;_,codes=enroll(sut);value=codes[0];login(sut)
    assert client.post("/api/auth/mfa/verify",json={"recovery_code":value}).status_code==200
    assert db.auth_mfa.docs[0]["enabled"] and len(db.auth_mfa.docs[0]["recovery_hashes"])==9
    login(sut)
    assert client.post("/api/auth/mfa/verify",json={"recovery_code":value}).status_code==400


def test_recovery_rotation_requires_password_recent_mfa_and_invalidates_old_codes(sut):
    client,db,_=sut;_,old=enroll(sut)
    assert client.post("/api/auth/mfa/recovery-codes",json={"password":"wrong"}).status_code==400
    result=client.post("/api/auth/mfa/recovery-codes",json={"password":PASSWORD})
    assert result.status_code==200 and len(result.json()["recovery_codes"])==10
    login(sut)
    assert client.post("/api/auth/mfa/verify",json={"recovery_code":old[0]}).status_code==400
    assert client.post("/api/auth/mfa/recovery-codes",json={"password":PASSWORD}).status_code==403


def test_replacement_preserves_old_secret_until_confirmation_then_invalidates_old_sessions(sut):
    client,db,_=sut;old_secret,old_codes=enroll(sut)
    old_access=client.cookies.get("access_token")
    started=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    assert started.status_code==200
    assert db.auth_mfa.docs[0]["secret"] and old_secret!=started.json()["secret"]
    confirmation=client.post("/api/auth/mfa/confirm",json={"code":mfa.totp(started.json()["secret"],int(time.time())//30)})
    assert confirmation.status_code==200
    client.cookies.clear();client.headers["Authorization"]="Bearer "+old_access
    assert client.get("/api/auth/me").status_code==401
    login(sut)
    assert client.post("/api/auth/mfa/verify",json={"recovery_code":old_codes[0]}).status_code==400


def test_first_login_password_change_precedes_mfa_and_cannot_be_bypassed(sut):
    client,db,_=sut;db.users.docs[0]["must_change_password"]=True
    login(sut)
    blocked=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    assert blocked.status_code==403 and blocked.json()["detail"]["code"]=="password_change_required"
    response=client.post("/api/auth/password/change",json={"current_password":PASSWORD,"new_password":"Updated-local-security-password-2026"})
    assert response.status_code==200 and not db.users.docs[0]["must_change_password"]


def test_unverified_enrolled_user_cannot_change_password_without_mfa(sut):
    client,_,_=sut;enroll(sut);login(sut)
    response=client.post("/api/auth/password/change",json={"current_password":PASSWORD,"new_password":"Updated-local-security-password-2026"})
    assert response.status_code==403


def test_password_change_invalidates_verified_access_and_refresh(sut):
    client,_,_=sut;enroll(sut)
    access=client.cookies.get("access_token");refresh=client.cookies.get("refresh_token")
    assert client.post("/api/auth/password/change",json={"current_password":PASSWORD,"new_password":"Updated-local-security-password-2026"}).status_code==200
    client.cookies.clear();client.headers["Authorization"]="Bearer "+access
    assert client.get("/api/auth/me").status_code==401
    client.headers.pop("Authorization");client.cookies.set("refresh_token",refresh,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401


def test_deactivation_invalidates_verified_sessions(sut):
    client,db,_=sut;enroll(sut);db.users.docs[0]["is_active"]=False
    assert client.get("/api/auth/me").status_code==401
    assert client.post("/api/auth/refresh").status_code==401


def test_refresh_cannot_upgrade_an_unverified_session_and_preserves_verified_proof(sut):
    client,_,_=sut;_,codes=enroll(sut);login(sut)
    old=client.cookies.get("refresh_token")
    response=client.post("/api/auth/refresh")
    assert response.status_code==200 and response.json()["mfa_verified"] is False
    assert client.get("/api/access/matrix").status_code==403
    assert client.post("/api/auth/mfa/verify",json={"recovery_code":codes[0]}).status_code==200
    assert client.post("/api/auth/refresh").json()["mfa_verified"] is True
    assert client.get("/api/access/matrix").status_code==200
    client.cookies.clear();client.cookies.set("refresh_token",old,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401


def test_legacy_access_and_refresh_tokens_do_not_bypass_enrolled_mfa(sut):
    client,_,users=sut;enroll(sut);u=users["hr_admin"]
    access=auth.create_access_token(u["id"],u["email"],u["role"])
    payload=jwt.decode(access,auth.get_jwt_secret(),algorithms=["HS256"])
    for field in ("mfa","mver","mat"):payload.pop(field,None)
    client.cookies.clear();client.headers["Authorization"]="Bearer "+jwt.encode(payload,auth.get_jwt_secret(),algorithm="HS256")
    assert client.get("/api/access/matrix").status_code==401
    refresh,_=auth.create_refresh_token(u["id"])
    client.headers.pop("Authorization");client.cookies.set("refresh_token",refresh,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401


def test_live_role_promotion_and_custom_privileges_do_not_bypass_mfa(sut):
    client,db,users=sut;login(sut,"employee")
    next(row for row in db.users.docs if row["role"]=="employee")["role"]="finance"
    assert client.get("/api/access/matrix").status_code==401
    with patch.dict(CUSTOM_ROLE_DEFINITIONS,{"custom_it":{"inherits_from":"it_admin"}}):
        assert mfa.privileged({"role":"custom_it"})
    with patch.dict(RUNTIME_OVERRIDES,{("M10","employee"):{"level":"Full","scope":None}}):
        assert mfa.privileged({"role":"employee"})


def test_admin_reset_needs_verified_it_identity_password_ticket_and_other_account(sut):
    client,db,users=sut;_,hr_codes=enroll(sut,"hr_admin")
    target=users["hr_admin"]["id"]
    _,it_codes=enroll(sut,"it_admin")
    assert client.post("/api/auth/mfa/reset/"+target,json={"password":"wrong","reference":"APPROVED-TEST-REF"}).status_code==400
    assert client.post("/api/auth/mfa/reset/"+target,json={"password":PASSWORD,"reference":""}).status_code==422
    assert client.post("/api/auth/mfa/reset/"+users["it_admin"]["id"],json={"password":PASSWORD,"reference":"APPROVED-TEST-REF"}).status_code==403
    result=client.post("/api/auth/mfa/reset/"+target,json={"password":PASSWORD,"reference":"APPROVED-TEST-REF"})
    assert result.status_code==200
    row=next(row for row in db.auth_mfa.docs if row["_id"]==target)
    assert row["required"] and not row["enabled"] and not row["secret"] and not row["recovery_hashes"]
    login(sut,"hr_admin")
    assert client.get("/api/auth/me").json()["mfa_action"]=="enroll"
    assert client.get("/api/access/matrix").status_code==403


def test_hr_cannot_reset_another_accounts_mfa(sut):
    client,_,users=sut;enroll(sut)
    assert client.post("/api/auth/mfa/reset/"+users["finance"]["id"],json={"password":PASSWORD,"reference":"APPROVED-TEST-REF"}).status_code==403


def test_reset_invalidates_target_sessions_even_during_optional_rollout(sut,monkeypatch):
    client,db,users=sut;enroll(sut,"hr_admin")
    old_access=client.cookies.get("access_token");old_refresh=client.cookies.get("refresh_token")
    enroll(sut,"it_admin")
    assert client.post("/api/auth/mfa/reset/"+users["hr_admin"]["id"],json={"password":PASSWORD,"reference":"APPROVED-TEST-REF"}).status_code==200
    monkeypatch.setenv("MFA_ENFORCEMENT","optional")
    client.cookies.clear();client.headers["Authorization"]="Bearer "+old_access
    assert client.get("/api/auth/me").status_code==401
    client.headers.pop("Authorization");client.cookies.set("refresh_token",old_refresh,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401
    assert login(sut).json()["mfa_required"]

@pytest.mark.parametrize("path",["/auth/mfa/status","/auth/mfa/enroll","/auth/mfa/confirm","/auth/mfa/verify","/auth/mfa/recovery-codes"])
def test_mfa_endpoints_require_password_authenticated_identity(sut,path):
    client,_,_=sut
    response=client.get("/api"+path) if path.endswith("status") else client.post("/api"+path,json={"password":PASSWORD,"code":"123456"})
    assert response.status_code==401


def test_missing_encryption_key_fails_closed_without_enabling_mfa(sut,monkeypatch):
    client,db,_=sut;login(sut);monkeypatch.delenv("MFA_ENCRYPTION_KEYS")
    result=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    assert result.status_code==503 and not db.auth_mfa.docs[0]["enabled"]
    assert client.get("/api/access/matrix").status_code==403


def test_key_rotation_decrypts_old_key_and_binds_secret_to_account(sut,monkeypatch):
    _,_,users=sut;u=users["hr_admin"];secret=base64.b32encode(b"12345678901234567890").decode()
    old=Fernet.generate_key().decode();new=Fernet.generate_key().decode()
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS",old);encrypted=mfa.encrypt_secret(u,secret)
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS",new+","+old)
    assert mfa.decrypt_secret(u,encrypted)==secret
    with pytest.raises(HTTPException):mfa.decrypt_secret(users["finance"],encrypted)
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS",new)
    with pytest.raises(HTTPException):mfa.decrypt_secret(u,encrypted)


def test_old_access_token_cannot_outlive_current_fifteen_minute_policy(sut):
    client,_,users=sut;u=users["employee"]
    payload=jwt.decode(auth.create_access_token(u["id"],u["email"],u["role"]),auth.get_jwt_secret(),algorithms=["HS256"])
    payload.update(iat=time.time()-901,exp=time.time()+3600,sst=time.time()-901)
    client.headers["Authorization"]="Bearer "+jwt.encode(payload,auth.get_jwt_secret(),algorithm="HS256")
    assert client.get("/api/auth/me").status_code==401


def test_audit_failure_never_enables_or_publishes_recovery_codes(sut):
    client,db,_=sut;login(sut)
    result=client.post("/api/auth/mfa/enroll",json={"password":PASSWORD})
    code=mfa.totp(result.json()["secret"],int(time.time())//30)
    with patch.object(db.audit_logs,"insert_one",AsyncMock(side_effect=HTTPException(503,"Audit unavailable"))):
        result=client.post("/api/auth/mfa/confirm",json={"code":code})
    assert result.status_code==503 and not db.auth_mfa.docs[0]["enabled"]


def test_stale_inflight_security_request_is_denied_after_reset(sut):
    _,db,users=sut;enroll(sut)
    actor={**db.users.docs[0],"_mfa_generation":db.auth_mfa.docs[0]["generation"]}
    db.auth_mfa.docs[0]["generation"]="changed-by-reset"
    with pytest.raises(HTTPException):asyncio.run(mfa.fresh_user(db,actor))


def test_concurrent_totp_and_recovery_consumption_real_mongo(monkeypatch,password_hash):
    from .test_employee_integrity_mongo import local_database
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS",Fernet.generate_key().decode())
    async def exercise():
        async with local_database() as db:
            u=account(role="hr_admin",password_hash=password_hash);await db.users.insert_one(u)
            secret=base64.b32encode(b"12345678901234567890").decode()
            codes,hashes=mfa.recovery_codes(u)
            await db.auth_mfa.insert_one({"_id":str(u["_id"]),"tenant_id":"solvit","enabled":True,"generation":"generation","secret":mfa.encrypt_secret(u,secret),"last_counter":-1,"recovery_hashes":hashes})
            async def attempt(**proof):
                try:
                    async with integrity_write(db):return await mfa.verify(db,u,**proof)
                except HTTPException as error:return error.status_code
            results=await asyncio.gather(*[attempt(code=mfa.totp(secret,int(time.time())//30)) for _ in range(2)])
            assert results.count("generation")==1 and any(x in (400,409) for x in results)
            results=await asyncio.gather(*[attempt(recovery=codes[0]) for _ in range(2)])
            assert results.count("generation")==1 and any(x in (400,409) for x in results)
            row=await mfa.state(db,u);assert len(row["recovery_hashes"])==9
    asyncio.run(exercise())


def test_password_lockout_survives_worker_cache_clear(sut):
    from utils import security
    client,db,_=sut
    for _ in range(5):
        assert client.post("/api/auth/login",json={"email":"hr_admin@example.com","password":"wrong"}).status_code==401
        security._login_fail_cache.clear();security._lockout_until.clear()
    assert client.post("/api/auth/login",json={"email":"hr_admin@example.com","password":PASSWORD}).status_code==423
    db.auth_login_limits.docs[0]["locked_until"]=time.time()-1
    assert client.post("/api/auth/login",json={"email":"hr_admin@example.com","password":PASSWORD}).status_code==200


def test_role_change_invalidates_prior_access_and_refresh(sut):
    from routes import access
    client,db,users=sut;login(sut,"employee")
    old_access=client.cookies.get("access_token");old_refresh=client.cookies.get("refresh_token")
    request=SimpleNamespace(json=AsyncMock(return_value={"role":"finance"}))
    with patch.object(access,"get_db",return_value=db),patch.object(access,"get_current_user",AsyncMock(return_value=users["it_admin"])):
        result=asyncio.run(access.update_user_role(users["employee"]["id"],request))
    assert result["role"]=="finance"
    assert client.get("/api/auth/me").status_code==401
    assert client.post("/api/auth/refresh").status_code==401


def test_unverified_mfa_challenge_expires_and_cannot_be_extended_by_refresh(sut):
    client,_,_=sut;enroll(sut);login(sut)
    access=jwt.decode(client.cookies.get("access_token"),auth.get_jwt_secret(),algorithms=["HS256"])
    refresh=jwt.decode(client.cookies.get("refresh_token"),auth.get_jwt_secret(),algorithms=["HS256"])
    access["sst"]=time.time()-301;refresh["sst"]=access["sst"]
    client.cookies.clear();client.headers["Authorization"]="Bearer "+jwt.encode(access,auth.get_jwt_secret(),algorithm="HS256")
    assert client.get("/api/auth/me").status_code==401
    client.headers.pop("Authorization");client.cookies.set("refresh_token",jwt.encode(refresh,auth.get_jwt_secret(),algorithm="HS256"),domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401


def test_permission_cutoff_snapshot_blocks_tokens_minted_during_role_change_race(sut):
    client,db,users=sut;u=users["employee"]
    next(row for row in db.users.docs if row["_id"]==u["_id"])["sessions_invalidated_at"]=datetime.now(timezone.utc).isoformat()
    late_access=auth.create_access_token(u["id"],u["email"],u["role"],session_cutoff=None)
    late_refresh,_=auth.create_refresh_token(u["id"],role=u["role"],session_cutoff=None)
    client.headers["Authorization"]="Bearer "+late_access
    assert client.get("/api/auth/me").status_code==401
    client.headers.pop("Authorization");client.cookies.set("refresh_token",late_refresh,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401


def test_secret_encryption_uses_aes256_gcm_and_rejects_tampering(sut,monkeypatch):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key=Fernet.generate_key();monkeypatch.setenv("MFA_ENCRYPTION_KEYS",key.decode())
    user=sut[2]["hr_admin"];secret="A"*32
    value=mfa.encrypt_secret(user,secret);packed=base64.urlsafe_b64decode(value[3:])
    assert len(mfa.cipher()[0])==32
    payload=json.loads(AESGCM(base64.urlsafe_b64decode(key)).decrypt(packed[:12],packed[12:],b"solvit-mfa-v1"))
    assert payload["secret"]==secret and payload["user"]==str(user["_id"])
    damaged=packed[:-1]+bytes([packed[-1]^1])
    with pytest.raises(HTTPException):mfa.decrypt_secret(user,"v1."+base64.urlsafe_b64encode(damaged).decode())
