"""Direct HTTP regressions for legacy privacy and integrity boundaries."""
import asyncio
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
import jwt
import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server import app
from routes import recruitment, recognition, calendar, disciplinary, surveys, policies, compliance, budget, retention, projects, auth_routes
from utils import auth
from utils.access_matrix import RUNTIME_OVERRIDES
from utils.employee_integrity import integrity_write
from .integrity_fakes import Database, Collection, employee, account

MODULES = [recruitment, recognition, calendar, disciplinary, surveys, policies, compliance, budget, retention, projects, auth_routes]

class Counted(Collection):
    async def find_one(self, query, projection=None, **kwargs):
        return await super().find_one(query, projection)

    async def count_documents(self, query):
        return len((await self.find(query).to_list(None)))

@pytest.fixture
def sut(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "synthetic-task18-local-jwt-signing-key")
    monkeypatch.setenv("CORS_ORIGINS", "https://staff.example.test")
    staff = employee("staff", line_manager_id="manager", department="Operations")
    manager = employee("manager", "manager@example.test", department="Operations")
    outsider = employee("other", "other@example.test", department="Valuation")
    users = {}
    for role, key in [("employee", "staff"), ("line_manager", "manager"), ("hr_admin", None), ("finance", None), ("executive", None), ("it_admin", None)]:
        u=account(email=role+"@example.test", role=role, employee_id=key, account_type="system" if key is None else "employee", is_active=True)
        u["id"]=str(u["_id"])
        users[role]=u
    db=Database([staff,manager,outsider],list(users.values()))
    for name in ("recognitions", "solver_awards", "solvers", "calendar_events", "public_holidays", "leave_requests", "survey_windows", "survey_responses", "policies", "policy_acknowledgements", "disciplinary_cases", "case_documents", "statutory_compliance", "gp_records", "budget_allocations", "stay_interviews", "projects", "form_submissions", "notifications", "tasks"):
        setattr(db,name,Counted())
    with ExitStack() as stack:
        stack.enter_context(patch("database.get_db", return_value=db))
        for module in MODULES: stack.enter_context(patch.object(module,"get_db",return_value=db))
        stack.enter_context(patch("utils.email_triggers.fire_and_forget",AsyncMock()))
        client=TestClient(app,base_url="http://127.0.0.1:18089")
        def as_role(role):
            client.cookies.clear()
            u=users[role]
            client.headers["Authorization"]="Bearer "+auth.create_access_token(u["id"],u["email"],u["role"])
            return client
        yield db,users,as_role,client
        client.close()


def add(collection, **row):
    row.setdefault("_id",ObjectId());row.setdefault("tenant_id","solvit")
    collection.docs.append(row)
    return row

@pytest.mark.parametrize("role",["employee","finance","it_admin","executive"])
@pytest.mark.parametrize("path",["/recruitment/candidate", "/disciplinary/case", "/retention/stay-interviews"])
def test_confidential_records_reject_unauthorized_roles(sut,role,path):
    db,users,as_role,_=sut
    add(db.candidates,id="candidate",department="Operations",national_id_number="SECRET")
    add(db.disciplinary_cases,id="case",employee_id="other",allegation_details="SECRET")
    result=as_role(role).get("/api"+path)
    assert result.status_code in (403,404)
    assert "SECRET" not in result.text

@pytest.mark.parametrize("reference",["canonical","storage"])
def test_candidate_detail_and_manager_scope(sut,reference):
    db,_,as_role,_=sut
    row=add(db.candidates,id="candidate",department="Valuation",email="SECRET",full_name="Private")
    ref="candidate" if reference=="canonical" else str(row["_id"])
    assert as_role("line_manager").get("/api/recruitment/"+ref).status_code==403
    assert as_role("hr_admin").get("/api/recruitment/"+ref).status_code==200
    row["department"]="Operations"
    response=as_role("line_manager").get("/api/recruitment/"+ref)
    assert response.status_code==200 and "SECRET" not in response.text


def test_manager_cannot_update_recruitment_and_hr_cannot_skip_stages(sut):
    db,_,as_role,_=sut
    add(db.candidates,id="candidate",department="Operations",status="Active",current_stage=recruitment.PIPELINE_STAGES[0])
    assert as_role("line_manager").put("/api/recruitment/candidate",json={"stage":"Offer Accepted"}).status_code==403
    assert as_role("hr_admin").put("/api/recruitment/candidate",json={"stage":"Offer Accepted"}).status_code==409
    assert db.candidates.writes==0


def test_recruitment_rejects_tenant_idor_and_ambiguous_ids(sut):
    db,_,as_role,_=sut
    add(db.candidates,id="candidate",tenant_id="foreign",department="Operations")
    assert as_role("hr_admin").get("/api/recruitment/candidate").status_code==404
    add(db.candidates,id="duplicate");add(db.candidates,id="duplicate")
    assert as_role("hr_admin").get("/api/recruitment/duplicate").status_code==409


def test_normalized_candidate_duplicate_is_blocked(sut):
    db,_,as_role,_=sut
    add(db.candidates,id="candidate",email="  APPLICANT@example.com ")
    payload=dict(full_name="Synthetic",email="applicant@example.com",position_applied="Role",department="Operations",role_level="L1")
    result=as_role("hr_admin").post("/api/recruitment",json=payload)
    assert result.status_code==409 and len(db.candidates.docs)==1


def test_pending_recognition_is_not_visible_to_nominee_or_other_staff(sut):
    db,_,as_role,_=sut
    add(db.recognitions,id="private",nominee_id="staff",nominator_id="someone",status="Pending",specific_behaviour="SECRET")
    assert as_role("employee").get("/api/recognition").json()==[]
    assert as_role("line_manager").get("/api/recognition").json()==[]
    assert len(as_role("hr_admin").get("/api/recognition").json())==1


def test_manager_recognition_cannot_forge_money_or_workflow(sut):
    db,_,as_role,_=sut
    result=as_role("line_manager").post("/api/recognition/manager",json={"nominee_id":"staff","amount_kes":999,"status":"Paid"})
    assert result.status_code==422 and not db.recognitions.docs


def test_calendar_keeps_unpublished_legacy_events_hr_only(sut):
    db,_,as_role,_=sut
    today=datetime.now(timezone.utc).date().isoformat()
    add(db.calendar_events,id="private",start_date=today,title="SECRET HR hearing",event_type="disciplinary",salary=999)
    for role in ("employee","line_manager","finance","executive","it_admin"):
        result=as_role(role).get("/api/calendar")
        assert result.status_code==200 and "SECRET" not in result.text
    result=as_role("hr_admin").get("/api/calendar")
    assert "SECRET HR hearing" in result.text and "salary" not in result.text


def test_notice_requires_real_authorized_case_and_rejects_forgery(sut):
    db,_,as_role,_=sut
    add(db.disciplinary_cases,id="foreign",tenant_id="foreign",employee_id="other")
    client=as_role("hr_admin")
    assert client.post("/api/disciplinary/foreign/issue-notice",json={"content":"Notice"}).status_code==404
    add(db.disciplinary_cases,id="case",employee_id="staff",status="Investigation")
    assert client.post("/api/disciplinary/case/issue-notice",json={"content":"Notice","employee_id":"other"}).status_code==422
    assert not db.case_documents.docs


def test_manager_case_projection_omits_confidential_content(sut):
    db,_,as_role,_=sut
    add(db.disciplinary_cases,id="case",employee_id="staff",status="Investigation",allegation_details="SECRET",medical="SECRET")
    result=as_role("line_manager").get("/api/disciplinary/case")
    assert result.status_code==200 and "SECRET" not in result.text and result.json()["status"]=="Investigation"


def window(db,**updates):
    today=datetime.now(timezone.utc).date()
    return add(db.survey_windows,id="window",survey_type="alignment_fte",status="Open",open_date=(today-timedelta(days=1)).isoformat(),close_date=(today+timedelta(days=1)).isoformat(),**updates)


def answers(**updates):
    return dict(survey_window_id="window",respondent_type="FTE",responses={"q"+str(i):4 for i in range(1,13)},**updates)


def test_survey_subject_is_server_owned_and_repeat_submission_blocked(sut):
    db,_,as_role,_=sut;window(db)
    client=as_role("employee")
    forged=answers();forged["respondent_type"]="Solver"
    assert client.post("/api/surveys/respond",json=forged).status_code==403
    assert client.post("/api/surveys/respond",json=answers()).status_code==200
    assert client.post("/api/surveys/respond",json=answers()).status_code==409
    assert len(db.survey_responses.docs)==1 and db.survey_responses.docs[0]["subject_id"]=="staff"
    assert db.survey_windows.docs[0]["response_count"]==1

@pytest.mark.parametrize("bad",[0,6,-1])
def test_survey_rejects_invalid_scores(sut,bad):
    db,_,as_role,_=sut;window(db)
    data=answers();data["responses"]["q1"]=bad
    assert as_role("employee").post("/api/surveys/respond",json=data).status_code==422
    assert not db.survey_responses.docs


def test_survey_closed_or_foreign_window_is_inaccessible(sut):
    db,_,as_role,_=sut;row=window(db)
    row["status"]="Closed"
    assert as_role("employee").post("/api/surveys/respond",json=answers()).status_code==409
    row["tenant_id"]="foreign"
    assert as_role("employee").post("/api/surveys/respond",json=answers()).status_code==404


def test_policy_audience_and_private_paths_are_not_exposed(sut):
    db,_,as_role,_=sut
    add(db.policies,id="policy",title="SECRET",status="Draft",applies_to=["all"],file_url="SECRET_PATH",file_history=["SECRET_PATH"])
    client=as_role("employee")
    assert client.get("/api/policies").json()==[]
    assert client.get("/api/policies/policy/download").status_code==403
    row=db.policies.docs[0];row["status"]="Active";row["applies_to"]=["solver"]
    assert client.get("/api/policies/policy").status_code==403
    row["applies_to"]=["FTE"]
    response=client.get("/api/policies/policy")
    assert response.status_code==200 and "SECRET_PATH" not in response.text


def test_policy_acknowledgement_is_versioned_and_idempotent(sut):
    db,_,as_role,_=sut
    row=add(db.policies,id="policy",title="Policy",status="Active",applies_to=["all"],version="1")
    client=as_role("employee")
    for _ in range(2): assert client.post("/api/policies/policy/acknowledge",json={"signature":"Synthetic"}).status_code==200
    row["version"]="2"
    assert client.post("/api/policies/policy/acknowledge",json={"signature":"Synthetic"}).status_code==200
    assert len(db.policy_acknowledgements.docs)==2
    assert {r["policy_version"] for r in db.policy_acknowledgements.docs}=={"1","2"}


def test_policy_upload_scan_failure_creates_no_metadata(sut):
    db,_,as_role,_=sut
    add(db.policies,id="policy",status="Active",applies_to=["all"])
    with patch("utils.document_uploads.scan_content",AsyncMock(side_effect=HTTPException(503,"Unavailable"))):
        result=as_role("hr_admin").post("/api/policies/policy/upload",files={"file":("policy.pdf",b"%PDF-1.7\nSynthetic\n%%EOF","application/pdf")})
    assert result.status_code==503 and db.policies.writes==0

@pytest.mark.parametrize("role",["hr_admin","employee","line_manager","it_admin"])
def test_compliance_write_requires_finance(sut,role):
    db,_,as_role,_=sut
    result=as_role(role).post("/api/compliance/statutory",json={"period":"2026-10","statutory_type":"NSSF","status":"Paid"})
    assert result.status_code==403 and not db.statutory_compliance.docs


def test_finance_statutory_fields_and_duplicates(sut):
    db,_,as_role,_=sut;client=as_role("finance")
    data={"period":"2026-10","statutory_type":"NSSF","status":"Paid","amount_kes":100}
    assert client.post("/api/compliance/statutory",json={**data,"tenant_id":"foreign"}).status_code==422
    assert client.post("/api/compliance/statutory",json=data).status_code==200
    assert client.post("/api/compliance/statutory",json=data).status_code==409


def test_origin_guard_rejects_untrusted_browser_mutations(sut):
    _,_,as_role,_=sut;client=as_role("employee")
    for path in ("/api/auth/logout","/api/auth/refresh","/api/auth/login","/api/surveys/respond"):
        assert client.post(path,json={},headers={"Origin":"https://attacker.example.test"}).status_code==403
    assert client.post("/api/auth/logout",headers={"Origin":"https://staff.example.test"}).status_code==200
    assert client.post("/api/auth/logout",headers={"Sec-Fetch-Site":"cross-site"}).status_code==403


def test_auth_me_never_returns_account_secrets(sut):
    db,users,as_role,_=sut
    db.users.docs[0].update(totp_secret="SECRET",mfa_secret="SECRET",recovery_codes=["SECRET"],custom_secret="SECRET")
    response=as_role("employee").get("/api/auth/me")
    assert response.status_code==200 and "SECRET" not in response.text


def test_session_absolute_age_is_enforced_and_access_is_fifteen_minutes(sut):
    db,users,_,_=sut;u=users["hr_admin"]
    token=auth.create_access_token(u["id"],u["email"],u["role"])
    payload=jwt.decode(token,auth.get_jwt_secret(),algorithms=["HS256"])
    assert 0 < payload["exp"]-payload["iat"] <= 900
    payload["sst"]=datetime.now(timezone.utc).timestamp()-8*3600-1
    assert asyncio.run(auth.token_invalidated(db,u,payload)) is True


def test_refresh_keeps_original_session_start_and_logout_revokes_family(sut):
    db,users,as_role,client=sut;u=users["employee"]
    original,jti=auth.create_refresh_token(u["id"])
    payload=jwt.decode(original,auth.get_jwt_secret(),algorithms=["HS256"])
    client.cookies.set("refresh_token",original,domain="127.0.0.1",path="/")
    result=client.post("/api/auth/refresh")
    assert result.status_code==200
    refreshed=jwt.decode(client.cookies.get("refresh_token"),auth.get_jwt_secret(),algorithms=["HS256"])
    assert refreshed["sst"]==payload["sst"] and refreshed["sid"]==jti
    access=client.cookies.get("access_token")
    client.cookies.set("refresh_token",original,domain="127.0.0.1",path="/")
    assert client.post("/api/auth/refresh").status_code==401
    client.cookies.clear();client.headers["Authorization"]="Bearer "+access
    assert client.post("/api/auth/logout").status_code==200
    assert client.get("/api/auth/me").status_code==401


def test_module_revocation_cannot_be_bypassed_by_legacy_routes(sut):
    db,_,as_role,_=sut
    add(db.candidates,id="candidate",department="Operations")
    # HTTP authorization reads persisted settings, not a patched worker cache.
    db.permission_overrides.docs = [{"tenant_id":"solvit","module_id":"M03","role":"hr_admin","removed":True},
                                   {"tenant_id":"solvit","module_id":"M11","role":"employee","removed":True}]
    assert as_role("hr_admin").get("/api/recruitment/candidate").status_code==403
    assert as_role("employee").get("/api/recognition").status_code==403


@pytest.mark.parametrize("endpoint",["/recruitment", "/recognition", "/calendar", "/surveys/windows", "/policies", "/compliance/statutory"])
def test_legacy_endpoints_require_authentication(sut,endpoint):
    _,_,_,client=sut
    assert client.get("/api"+endpoint).status_code==401


def test_financial_get_does_not_seed_a_baseline_and_it_is_denied(sut):
    db,_,as_role,_=sut
    assert as_role("it_admin").get("/api/budget/envelope").status_code==403
    response=as_role("finance").get("/api/budget/envelope")
    assert response.status_code==200 and db.gp_records.writes==0
    assert response.json()["finance_input_received"] is False


def test_hr_cannot_edit_approved_allocation_amount_or_spend_unapproved_funds(sut):
    db,_,as_role,_=sut
    row=add(db.budget_allocations,id="allocation",status="Approved",amount_kes=100,created_by="hr")
    client=as_role("hr_admin")
    assert client.put("/api/budget/allocations/allocation",json={"amount_kes":999999}).status_code==409
    row["status"]="Pending_Finance"
    assert client.put("/api/budget/allocations/allocation",json={"status":"Spent","spent_amount_kes":100}).status_code==409
    assert db.budget_allocations.writes==0


def test_budget_cancellation_preserves_history_and_rejects_other_tenants(sut):
    db,_,as_role,_=sut
    row=add(db.budget_allocations,id="allocation",status="Pending_Finance",amount_kes=100)
    client=as_role("hr_admin")
    assert client.delete("/api/budget/allocations/allocation").status_code==200
    assert len(db.budget_allocations.docs)==1 and db.budget_allocations.docs[0]["status"]=="Cancelled"
    row["tenant_id"]="foreign"
    assert client.delete("/api/budget/allocations/allocation").status_code==404


def test_project_direct_report_cannot_forge_reward_release(sut):
    db,_,as_role,_=sut
    add(db.projects,id="project",employee_id="staff",status="In Progress",reward_on_completion="HR approved terms")
    client=as_role("line_manager")
    assert client.put("/api/projects/project",json={"reward_on_completion":"Unlimited"}).status_code==403
    assert client.put("/api/projects/project",json={"status":"Completed - Reward Released"}).status_code==409
    assert not db.projects.writes


def test_generic_forms_do_not_disclose_new_assessment_snapshot_or_confidential_case(sut):
    from routes import forms
    db,users,as_role,_=sut
    add(db.form_submissions,id="assessment",submitted_by=users["employee"]["id"],workflow_kind="solver_assessment_v1",form_id="form-02",configuration={"answer_key":"SECRET"})
    add(db.form_submissions,id="notice",subject_employee_id="staff",form_id="form-17",data={"employee_id":"staff","allegation":"SECRET"},status="Completed")
    with patch.object(forms,"get_db",return_value=db):
        response=as_role("employee").get("/api/forms/submissions/"+users["employee"]["id"])
    assert response.status_code==200 and "SECRET" not in response.text


def test_concurrent_survey_submissions_real_mongo_are_unique():
    from .test_employee_integrity_mongo import local_database
    async def exercise():
        async with local_database() as db:
            staff=employee("staff");await db.employees.insert_one(staff)
            user={"id":"synthetic-user","role":"employee","employee_id":"staff","tenant_id":"solvit"}
            day=datetime.now(timezone.utc).date().isoformat()
            await db.survey_windows.insert_one({"id":"window","tenant_id":"solvit","survey_type":"alignment_fte","status":"Open","open_date":day,"close_date":day})
            with patch.object(surveys,"get_db",return_value=db),patch.object(surveys,"get_current_user",AsyncMock(return_value=user)):
                results=await asyncio.gather(*[surveys.submit_response(surveys.SurveyResponse(**answers()),None) for _ in range(2)],return_exceptions=True)
            assert sum(isinstance(x,dict) for x in results)==1
            assert await db.survey_responses.count_documents({})==1
            assert all(isinstance(x,dict) or isinstance(x,HTTPException) and x.status_code==409 for x in results)
    asyncio.run(exercise())


def test_concurrent_refresh_consumes_token_once_real_mongo(monkeypatch):
    from fastapi import Response
    from .test_employee_integrity_mongo import local_database
    monkeypatch.setenv("JWT_SECRET","synthetic-local-concurrency-signing-key")
    async def exercise():
        async with local_database() as db:
            u=account(is_active=True);await db.users.insert_one(u)
            token,_=auth.create_refresh_token(str(u["_id"]))
            request=SimpleNamespace(cookies={"refresh_token":token})
            with patch.object(auth_routes,"get_db",return_value=db):
                results=await asyncio.gather(*[auth_routes.refresh_token(request,Response()) for _ in range(2)],return_exceptions=True)
            assert sum(isinstance(x,dict) for x in results)==1
            assert all(isinstance(x,dict) or isinstance(x,HTTPException) and x.status_code in (401,409) for x in results)
    asyncio.run(exercise())


def test_storage_alias_cannot_bypass_duplicate_candidate_identity(sut):
    db,_,as_role,_=sut
    row=add(db.candidates,id="duplicate",department="Operations")
    add(db.candidates,id="duplicate",department="Operations")
    assert as_role("hr_admin").get("/api/recruitment/"+str(row["_id"])).status_code==409


def test_gp_change_preserves_prior_revision_and_requires_new_finance_confirmation(sut):
    db,_,as_role,_=sut
    add(db.gp_records,id="gp",period="2026",actual_gp_kes=1000000,form28_confirmed=True,active_tier="Tier_1")
    result=as_role("finance").post("/api/budget/gp-record",json={"period":"2026","actual_gp_kes":2000000})
    assert result.status_code==200
    row=db.gp_records.docs[0]
    assert row["form28_confirmed"] is False and row["active_tier"] is None
    assert row["revision_history"][0]["actual_gp_kes"]==1000000


def test_manager_ai_summary_cannot_disclose_case_or_medical_leave_details(sut):
    from routes import ai_agent
    db,_,as_role,_=sut
    info={"id":"staff","full_name":"Staff","open_disciplinary":[{"summary":"SECRET"}],"recent_leave":[{"type":"SECRET sick reason","status":"Approved"}]}
    with patch.object(ai_agent,"get_db",return_value=db),patch.object(ai_agent,"lookup_employee_status",AsyncMock(return_value=info)):
        response=as_role("line_manager").get("/api/ai-agent/employee-status",params={"query":"Staff"})
    assert response.status_code==200 and "SECRET" not in response.text


def test_ai_recognition_and_task_actions_recheck_target_scope(sut):
    from routes import ai_actions
    db,users,_,_=sut
    manager={**users["line_manager"],"employee_reference_ids":["manager"]}
    with pytest.raises(HTTPException):
        asyncio.run(ai_actions.execute_send_recognition(db,{"employee_id":"other","message":"Forged"},manager))
    add(db.tasks,id="private-task",employee_id="other",assigned_to="other-account",status="Open")
    with pytest.raises(HTTPException):
        asyncio.run(ai_actions.execute_mark_task(db,{"task_id":"private-task"},manager))
    assert not db.recognitions.docs and not db.tasks.writes
