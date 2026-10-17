"""Leave-file guards and independent-process permission regressions, synthetic only."""
import asyncio
import hashlib
import multiprocessing
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Depends, HTTPException, UploadFile
from fastapi.testclient import TestClient
from bson import ObjectId
from routes import leave
from utils import auth, document_uploads, access_matrix
from .integrity_fakes import Collection, Database, account
from .test_leave_management import fixture, run
from .test_employee_integrity_mongo import local_database

PDF = b"%PDF-1.7\nSynthetic supporting evidence\n%%EOF"


def upload(db, actor, content=PDF, name="evidence.pdf", mime="application/pdf"):
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actor)):
        return run(leave.upload_leave_evidence(None, UploadFile(BytesIO(content), filename=name, headers={"content-type": mime}), "medical_certificate", None))


def download(db, actor, key):
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actor)):
        return run(leave.download_leave_evidence(key, None))


def stored(db, root, **changes):
    path = root / "legacy.pdf"; path.write_bytes(PDF)
    row = {"_id": ObjectId(), "id": "legacy", "tenant_id": "solvit", "employee_id": "staff", "storage_name": path.name, **changes}
    db.leave_evidence.docs.append(row)
    return row


@pytest.mark.parametrize("status", [422, 503])
def test_leave_upload_scanner_rejection_never_persists(tmp_path, monkeypatch, status):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path))
    with patch.object(document_uploads, "scan_content", AsyncMock(side_effect=HTTPException(status, "Synthetic scan rejection"))):
        with pytest.raises(HTTPException) as error: upload(db, actors["staff"])
    assert error.value.status_code == status
    assert not db.leave_evidence.docs and not db.document_audit.docs and not list(tmp_path.iterdir())


def test_leave_missing_scanner_configuration_fails_closed(tmp_path, monkeypatch):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path)); monkeypatch.delenv("DOC_SCANNER_HOST", raising=False)
    with pytest.raises(HTTPException) as error: upload(db, actors["staff"])
    assert error.value.status_code == 503 and not db.leave_evidence.docs


@pytest.mark.parametrize("content,name,mime,status", [(b"%PDF-spoof", "evidence.pdf", "application/pdf", 400), (PDF,"../evil.pdf","application/pdf",400), (PDF,"evidence.pdf","text/html",400), (b"x"*(5*1024*1024+1),"evidence.pdf","application/pdf",422)], ids=["malformed-pdf", "path-name", "mime-spoof", "oversize"])
def test_leave_rejects_unsafe_content_before_scanning(tmp_path, monkeypatch, content, name, mime, status):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path))
    with patch.object(document_uploads, "scan_content", AsyncMock()) as scan:
        with pytest.raises(HTTPException) as error: upload(db, actors["staff"], content, name, mime)
    assert error.value.status_code == status and not scan.called and not db.leave_evidence.docs


def test_leave_upload_download_audits_and_private_metadata(tmp_path, monkeypatch):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path))
    with patch.object(document_uploads, "scan_content", AsyncMock()) as scan:
        result = upload(db, actors["staff"])
        response = download(db, actors["staff"], result["id"])
    assert scan.await_count == 2
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.media_type == "application/pdf"
    assert "storage_name" not in result and "content_sha256" not in result
    assert db.leave_evidence.docs[0]["publication_state"] == "Ready"
    assert [row["action"] for row in db.document_audit.docs] == ["uploaded", "downloaded"]
    assert all(row["source"] == "leave_evidence" and row["content_sha256"] == hashlib.sha256(PDF).hexdigest() for row in db.document_audit.docs)
    assert all(not {"storage_name", "stored_path", "file_name", "content"} & row.keys() for row in db.document_audit.docs)


@pytest.mark.parametrize("role", ["boss", "other", "other-boss"])
def test_leave_unrelated_staff_and_managers_denied_before_file_scan(tmp_path, monkeypatch, role):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path)); stored(db, tmp_path)
    with patch.object(document_uploads, "scan_content", AsyncMock()) as scan:
        with pytest.raises(HTTPException) as error: download(db, actors[role], "legacy")
    assert error.value.status_code == 403 and not scan.called and not db.document_audit.docs


def test_leave_hr_legacy_download_scans_without_rewriting(tmp_path, monkeypatch):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path)); row = stored(db, tmp_path); before = deepcopy(row)
    with patch.object(document_uploads, "scan_content", AsyncMock()) as scan:
        assert download(db, actors["hr"], "legacy").body == PDF
    scan.assert_awaited_once_with(PDF)
    assert db.leave_evidence.docs[0] == before and (tmp_path / "legacy.pdf").read_bytes() == PDF
    assert db.document_audit.docs[0]["action"] == "downloaded"


@pytest.mark.parametrize("changes,status", [({"storage_name":"../outside.pdf"},404), ({"storage_name":"C:private.pdf"},404), ({"content_sha256":"bad"},503), ({"publication_state":"Pending_Audit"},503), ({"tenant_id":"foreign"},404)])
def test_leave_unsafe_stored_references_fail_closed(tmp_path, monkeypatch, changes, status):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path)); stored(db, tmp_path, **changes)
    with patch.object(document_uploads, "scan_content", AsyncMock()) as scan:
        with pytest.raises(HTTPException) as error: download(db, actors["staff"], "legacy")
    assert error.value.status_code == status and not scan.called


@pytest.mark.parametrize("status", [422,503])
def test_leave_legacy_download_requires_clean_current_verdict(tmp_path, monkeypatch, status):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path)); stored(db, tmp_path)
    with patch.object(document_uploads, "scan_content", AsyncMock(side_effect=HTTPException(status,"Synthetic rejection"))):
        with pytest.raises(HTTPException) as error: download(db, actors["staff"], "legacy")
    assert error.value.status_code == status and (tmp_path / "legacy.pdf").read_bytes() == PDF
    assert not db.document_audit.docs


def test_leave_audit_failure_blocks_publication_and_download(tmp_path, monkeypatch):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path))
    db.document_audit.insert_one = AsyncMock(side_effect=RuntimeError("Synthetic audit outage"))
    with patch.object(document_uploads, "scan_content", AsyncMock()):
        with pytest.raises(HTTPException) as error: upload(db, actors["staff"])
        assert error.value.status_code == 503
        row = db.leave_evidence.docs[0]
        assert row["publication_state"] == "Pending_Audit" and list(tmp_path.iterdir())
        with pytest.raises(HTTPException): download(db, actors["staff"], row["id"])
        stored(db, tmp_path)
        with pytest.raises(HTTPException) as error: download(db, actors["hr"], "legacy")
        assert error.value.status_code == 503


def test_request_permission_snapshots_do_not_bleed_between_concurrent_tasks():
    one, two = Database(), Database()
    one.permission_overrides.docs = [{"tenant_id":"solvit","module_id":"M18","role":"employee","removed":True}]
    two.custom_roles.docs = [{"tenant_id":"solvit","key":"custom_it","inherits_from":"it_admin"}]
    async def exercise():
        ready, finish = asyncio.Event(), asyncio.Event()
        async def first():
            async with access_matrix.request_permissions(one):
                ready.set(); await finish.wait()
                assert access_matrix.get_module_access("M18","employee") is None
                assert "custom_it" not in access_matrix.CUSTOM_ROLE_DEFINITIONS
        async def second():
            await ready.wait()
            async with access_matrix.request_permissions(two):
                assert access_matrix.get_module_access("M18","employee") is not None
                assert "custom_it" in access_matrix.CUSTOM_ROLE_DEFINITIONS
            finish.set()
        await asyncio.gather(first(),second())
    run(exercise())


def test_permission_load_failure_cannot_fall_back_to_privileged_worker_cache():
    db=Database(); db.permission_overrides.find=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("Synthetic DB outage"))
    with patch.dict(access_matrix.RUNTIME_OVERRIDES,{("M18","employee"):{"level":"Full"}}):
        with pytest.raises(HTTPException) as error: run(access_matrix.read_runtime_state(db))
    assert error.value.status_code == 503


@pytest.mark.parametrize("collection,rows", [("permission_overrides", [{"tenant_id":"solvit","module_id":"M18","role":"employee","level":"Full"}]*2), ("custom_roles",[{"tenant_id":"solvit","key":"custom","inherits_from":"unknown"}])])
def test_ambiguous_permission_settings_fail_closed(collection,rows):
    db=Database();getattr(db,collection).docs=rows
    with pytest.raises(HTTPException) as error: run(access_matrix.read_runtime_state(db))
    assert error.value.status_code == 503


def _permission_worker(database_name, commands, results):
    """A separate Python process: no shared modules, permission cache or client."""
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    import database
    from server import protect_application_session
    from routes import access, auth_routes, mfa_routes
    os.environ["MFA_ENFORCEMENT"]="privileged"
    @asynccontextmanager
    async def lifespan(app):
        client=AsyncIOMotorClient("mongodb://127.0.0.1:27089/")
        database._db=client[database_name]
        await access_matrix.load_runtime_state(database._db)  # Deliberately seed worker-local old state.
        try: yield
        finally: client.close()
    app=FastAPI(lifespan=lifespan,dependencies=[Depends(protect_application_session)])
    app.include_router(access.router,prefix="/api");app.include_router(auth_routes.router,prefix="/api");app.include_router(mfa_routes.router,prefix="/api")
    try:
        with TestClient(app,base_url="http://127.0.0.1:18089") as client:
            results.put({"ready":True,"pid":os.getpid()})
            while True:
                command=commands.get(timeout=60)
                if command is None: break
                response=client.request(command.get("method","GET"),command["path"],json=command.get("json"),headers={"Authorization":"Bearer "+command["token"]})
                results.put({"status":response.status_code,"body":response.json()})
    except BaseException as error:
        results.put({"error":type(error).__name__+": "+str(error)})
        raise


def test_independent_processes_observe_permission_custom_role_mfa_and_account_changes(monkeypatch):
    monkeypatch.setenv("JWT_SECRET","synthetic-pre-staging-worker-test-only");monkeypatch.setenv("MFA_ENFORCEMENT","optional")
    async def exercise():
        async with local_database() as db:
            user=account(account_type="system",is_active=True)
            await db.users.insert_one(user)
            token=auth.create_access_token(str(user["_id"]),user["email"],user["role"])
            it=account(account_type="system",role="it_admin",email="it@example.com",is_active=True)
            await db.users.insert_one(it)
            await db.auth_mfa.insert_one({"_id":str(it["_id"]),"tenant_id":"solvit","enabled":True,"generation":"ready"})
            it_token=auth.create_access_token(str(it["_id"]),it["email"],it["role"],mfa_verified=True,mfa_generation="ready",mfa_at=time.time())
            context=multiprocessing.get_context("spawn"); workers=[]
            try:
                for _ in range(2):
                    commands,results=context.Queue(),context.Queue()
                    process=context.Process(target=_permission_worker,args=(db.name,commands,results));process.start()
                    workers.append((process,commands,results))
                    assert results.get(timeout=30).get("ready") is True
                assert workers[0][0].pid != workers[1][0].pid
                def request(worker,path="/api/access/check/M18",value=token,method="GET",body=None):
                    worker[1].put({"path":path,"token":value,"method":method,"json":body});result=worker[2].get(timeout=15)
                    assert "error" not in result,result
                    return result
                for worker in workers: assert request(worker)["body"]["access"] is not None
                changed=request(workers[0],"/api/access/matrix/cell",it_token,"PUT",{"module_id":"M18","role":"employee","level":None})
                assert changed["status"] == 200 and changed["body"]["effective"] is None
                for worker in workers: assert request(worker)["body"]["access"] is None
                restored=request(workers[1],"/api/access/matrix/cell",it_token,"DELETE",{"module_id":"M18","role":"employee"})
                assert restored["status"] == 200
                for worker in workers: assert request(worker)["body"]["access"] is not None
                created=request(workers[0],"/api/access/roles",it_token,"POST",{"key":"custom_it","label":"Synthetic custom IT","inherits_from":"it_admin"})
                assert created["status"] == 200
                custom=account(account_type="system",role="custom_it",email="custom@example.com",is_active=True)
                await db.users.insert_one(custom)
                custom_token=auth.create_access_token(str(custom["_id"]),custom["email"],custom["role"])
                for worker in workers:
                    status=request(worker,"/api/auth/mfa/status",custom_token)
                    assert status["status"] == 200 and status["body"]["privileged"] is True
                    assert request(worker,value=custom_token)["status"] == 403
                await db.custom_roles.update_one({"key":"custom_it"},{"$set":{"inherits_from":"employee"}})
                for worker in workers:
                    status=request(worker,"/api/auth/mfa/status",custom_token)
                    assert status["body"]["privileged"] is False
                    assert request(worker,value=custom_token)["status"] == 200
                # Inherited base overrides must be honored, including revokes.
                await db.permission_overrides.insert_one({"tenant_id":"solvit","module_id":"M18","role":"employee","removed":True})
                for worker in workers: assert request(worker,value=custom_token)["body"]["access"] is None
                await db.permission_overrides.delete_many({})
                await db.permission_overrides.insert_one({"tenant_id":"solvit","module_id":"M10","role":"custom_it","level":"Full"})
                for worker in workers:
                    status=request(worker,"/api/auth/mfa/status",custom_token)
                    assert status["body"]["mfa_required"] is True
                    result=request(worker,value=custom_token)
                    assert result["status"] == 403 and result["body"]["detail"]["code"] == "mfa_required"
                await db.users.update_one({"_id":user["_id"]},{"$set":{"is_active":False}})
                for worker in workers: assert request(worker)["status"] == 401
            finally:
                for process,commands,results in workers:
                    commands.put(None);process.join(timeout=15)
                    if process.is_alive(): process.terminate();process.join(timeout=5)
                    commands.close();results.close()
    run(exercise())


def test_database_auth_reads_are_pinned_to_primary(monkeypatch):
    import database
    from pymongo import ReadPreference
    from unittest.mock import MagicMock
    client=MagicMock(); db=object();client.get_database.return_value=db
    monkeypatch.setenv("MONGO_URL","mongodb://127.0.0.1:27089/?readPreference=secondaryPreferred")
    monkeypatch.setenv("DB_NAME","codex_integrity_test_primary")
    with patch.object(database,"AsyncIOMotorClient",return_value=client), patch.object(database,"_db",None), patch.object(database,"_client",None):
        assert run(database.init_db()) is db
        client.get_database.assert_called_once_with("codex_integrity_test_primary",read_preference=ReadPreference.PRIMARY)


def test_leave_http_anonymous_forged_owner_and_manager_download_isolation(tmp_path,monkeypatch):
    from server import app
    db,actors=fixture();monkeypatch.setenv("LEAVE_EVIDENCE_ROOT",str(tmp_path));monkeypatch.setenv("JWT_SECRET","synthetic-pre-staging-http-key-only");monkeypatch.setenv("MFA_ENFORCEMENT","optional")
    def headers(role):
        actor=actors[role]
        return {"Authorization":"Bearer "+auth.create_access_token(actor["id"],actor["email"],actor["role"])}
    with patch("database.get_db",return_value=db),patch.object(leave,"get_db",return_value=db),patch.object(document_uploads,"scan_content",AsyncMock()) as scan:
        client=TestClient(app,base_url="http://127.0.0.1:18089")
        try:
            files={"file":("evidence.pdf",PDF,"application/pdf")}
            assert client.post("/api/leave/evidence",data={"document_type":"medical_certificate"},files=files).status_code == 401
            forged=client.post("/api/leave/evidence",headers=headers("staff"),data={"document_type":"medical_certificate","employee_id":"other"},files=files)
            assert forged.status_code == 403 and not scan.called
            saved=client.post("/api/leave/evidence",headers=headers("staff"),data={"document_type":"medical_certificate"},files=files)
            assert saved.status_code == 200,saved.text
            url="/api/leave/evidence/"+saved.json()["id"]
            assert client.get(url,headers=headers("boss")).status_code == 403
            assert client.get(url,headers=headers("other")).status_code == 403
            assert client.get(url,headers=headers("staff")).content == PDF
            assert client.get(url,headers=headers("hr")).content == PDF
            assert len(db.document_audit.docs) == 3
        finally: client.close()


def test_leave_legacy_native_document_and_employee_aliases(tmp_path,monkeypatch):
    db,actors=fixture();monkeypatch.setenv("LEAVE_EVIDENCE_ROOT",str(tmp_path))
    row=stored(db,tmp_path,id=ObjectId(),employee_id=str(db.employees.docs[0]["_id"]))
    before=deepcopy(row)
    with patch.object(document_uploads,"scan_content",AsyncMock()):
        assert download(db,actors["staff"],str(row["id"])).body == PDF
    assert db.leave_evidence.docs[0] == before
