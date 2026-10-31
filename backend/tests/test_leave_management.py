"""Handbook policy and checked leave lifecycle; synthetic fixtures only."""
import asyncio
from copy import deepcopy
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException, UploadFile

from utils import leave_policy as policy
from utils import leave_workflow as workflow
from utils.leave_balances import balances
from routes import leave, ai_actions
from .integrity_fakes import Database, Collection, employee, account
from .test_employee_integrity_mongo import local_database


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch):
    monkeypatch.setattr(policy, "today", lambda: date(2026, 10, 14))
    monkeypatch.setattr(workflow, "today", lambda: date(2026, 10, 14))
    monkeypatch.setattr(workflow, "stamp", lambda: "2026-10-14T09:00:00+00:00")


def fixture():
    employees = [employee("staff", start_date="2020-01-01", department="Operations", line_manager_id="boss"),
                 employee("cover", email="cover@example.com", start_date="2020-01-01", department="Operations", line_manager_id="boss"),
                 employee("boss", email="boss@example.com", start_date="2019-01-01", department="Leadership"),
                 employee("hr", email="hr@example.com", start_date="2019-01-01", department="HR", line_manager_id="boss"),
                 employee("other", email="other@example.com", start_date="2020-01-01", department="Other", line_manager_id="other-boss"),
                 employee("other-boss", email="other-boss@example.com", start_date="2020-01-01", department="Other")]
    users = [account(email=row["work_email"], employee_id=row["id"], role="hr_admin" if row["id"] == "hr" else "line_manager" if "boss" in row["id"] else "employee") for row in employees]
    db = Database(employees, users)
    for name in ("leave_requests", "leave_balances", "leave_policy_profiles", "leave_evidence", "public_holidays", "notifications", "tasks", "leave_rollover", "form_submissions"):
        setattr(db, name, Collection())
    actors = {row["employee_id"]: {**row, "id": str(row["_id"])} for row in users}
    return db, actors


def payload(**values):
    return {"employee_id": "staff", "leave_type": "Annual", "start_date": "2026-11-05", "end_date": "2026-11-06",
            "notes": "Tasks, deadlines and instructions for the covering colleague", "handover_contact_id": "cover", **values}


def budget(): return AsyncMock(return_value={"Annual": {"remaining": 21}, "year": 2026, "source": "legacy_derived"})
def run(coro): return asyncio.run(coro)


@pytest.mark.parametrize("start,end,holidays,expected", [
    ("2026-10-16", "2026-10-18", (), 1.5), ("2026-10-16", "2026-10-18", ("2026-10-16",), 0.5),
    ("2026-10-18", "2026-10-18", (), 0), ("2026-10-19", "2026-10-23", (), 5),
])
def test_working_day_equivalents_include_saturday_and_exclude_sunday_and_registry_holidays(start, end, holidays, expected):
    assert policy.working_units(start, end, holidays) == expected


@pytest.mark.parametrize("start,end", [("bad", "2026-10-19"), ("2026-10-20", "2026-10-19"), ("2026-10-19T00:00:00", "2026-10-20"), ("2026-01-01", "2028-01-01")])
def test_bad_or_reversed_dates_never_silently_become_one_day(start, end):
    with pytest.raises(HTTPException): policy.working_units(start, end)


def test_monthly_accrual_cap_completed_months_and_contract_rate():
    assert policy.annual_accrual(date(2026, 1, 1), date(2026, 12, 31)) == 21
    assert policy.annual_accrual(date(2026, 1, 10), date(2026, 2, 8)) == 0
    assert policy.annual_accrual(date(2026, 1, 10), date(2026, 2, 9)) == 1.75
    assert policy.annual_accrual(date(2026, 1, 1), date(2026, 12, 31), 2.5, 30) == 30


@pytest.mark.parametrize("change", [{"start_date": "2026-10-20", "end_date": "2026-10-21"}, {"start_date": "2026-11-02", "end_date": "2026-11-14"}, {"notes": ""}, {"handover_contact_id": "staff"}, {"leave_type": "Unknown"}])
def test_notice_long_block_handover_and_type_requirements(change):
    db, _ = fixture()
    with pytest.raises(HTTPException): run(policy.preview(db, db.employees.docs[0], payload(**change)))


def test_holidays_and_verified_contract_calendar_are_used_without_rewriting_employee():
    db, _ = fixture(); before = deepcopy(db.employees.docs)
    db.public_holidays.docs = [{"tenant_id": "solvit", "date": "2026-11-06"}]
    db.leave_policy_profiles.docs = [{"employee_id": "staff", "tenant_id": "solvit", "status": "Approved", "contract_reference": "reviewed-reference", "annual_entitlement": 30, "monthly_accrual": 2.5, "saturday_weight": 0}]
    result = run(policy.preview(db, db.employees.docs[0], payload(end_date="2026-11-07")))
    assert result["working_days"] == 1 and result["policy"]["annual_entitlement"] == 30
    assert db.employees.docs == before and db.leave_policy_profiles.writes == 0


def test_annual_creation_is_serialized_idempotent_and_reserves_pending_units():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        first = run(workflow.create(db, actors["staff"], payload(request_token="one"), loader))
        second = run(workflow.create(db, actors["staff"], payload(request_token="one"), loader))
    assert first["id"] == second["id"] and db.leave_requests.writes == 1
    assert run(workflow.availability(db, db.employees.docs[0], loader.return_value)) == 19
    with pytest.raises(HTTPException): run(workflow.create(db, actors["staff"], payload(request_token="different"), loader))


def test_two_step_approval_history_no_self_approval_and_notifications_are_private():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), loader))
        with pytest.raises(HTTPException): run(workflow.decide(db, actors["staff"], row["id"], {"decision": "Approve"}, loader))
        with pytest.raises(HTTPException): run(workflow.decide(db, actors["hr"], row["id"], {"decision": "Approve", "stage": "hr"}, loader))
        pending = run(workflow.decide(db, actors["boss"], row["id"], {"decision": "Approve", "handover_reviewed": True}, loader))
        assert pending["status"] == "Pending_HR"
        approved = run(workflow.decide(db, actors["hr"], row["id"], {"decision": "Approve", "stage": "hr", "handover_reviewed": True, "policy_review_confirmed": True}, loader))
    assert approved["status"] == "Approved" and len(approved["approval_history"]) == 3
    assert len(db.audit_logs.docs) == 3 and all("Tasks, deadlines" not in str(row) for row in db.notifications.docs)


def test_hr_who_signed_as_manager_cannot_be_the_second_reviewer():
    db, actors = fixture(); db.employees.docs[0]["line_manager_id"] = "hr"
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), budget()))
        run(workflow.decide(db, actors["hr"], row["id"], {"decision": "Approve", "stage": "manager", "handover_reviewed": True}, budget()))
        with pytest.raises(HTTPException): run(workflow.decide(db, actors["hr"], row["id"], {"decision": "Approve", "stage": "hr", "handover_reviewed": True, "policy_review_confirmed": True}, budget()))


@pytest.mark.parametrize("used,requested,expected", [(0, 3, (3, 0, 0)), (29, 3, (1, 2, 0)), (43, 5, (0, 2, 3)), (45, 1, (0, 0, 1))])
def test_sick_pay_tiers(used, requested, expected):
    result = policy.sick_pay(used, requested)
    assert tuple(result.values()) == expected


@pytest.mark.parametrize("duration,used,required", [(1, 0, False), (4, 0, True), (1, 30, True)])
def test_sick_certificate_threshold_and_emergency_notice_exception(duration, used, required):
    db, _ = fixture()
    if used:
        db.leave_requests.docs = [{"_id": ObjectId(), "id": "prior", "tenant_id": "solvit", "employee_id": "staff", "leave_type": "Sick", "status": "Approved", "start_date": "2026-01-01", "end_date": "2026-02-01", "working_days": used}]
    data = payload(leave_type="Sick", start_date="2026-10-14", end_date=f"2026-10-{13+duration:02d}", emergency_sick=True, notes="", handover_contact_id=None)
    if required:
        with pytest.raises(HTTPException): run(policy.preview(db, db.employees.docs[0], data))
    else:
        result = run(policy.preview(db, db.employees.docs[0], data)); assert result["planned_handover_required"] is False


def test_medical_evidence_ownership_and_private_manager_projection():
    db, actors = fixture(); doc = {"_id": ObjectId(), "id": "certificate", "tenant_id": "solvit", "employee_id": "other", "document_type": "medical_certificate"}
    db.leave_evidence.docs = [doc]
    data = payload(leave_type="Sick", start_date="2026-10-14", end_date="2026-10-19", emergency_sick=True, supporting_document_id="certificate")
    with pytest.raises(HTTPException): run(policy.preview(db, db.employees.docs[0], data))
    row = {"_id": ObjectId(), "id": "leave", "tenant_id": "solvit", "employee_id": "staff", "leave_type": "Sick", "status": "Pending_Manager", "supporting_document_id": "certificate", "notes": "PRIVATE", "sick_pay": {"private": "value"}}
    result = run(workflow.view(db, actors["boss"], row))
    assert not {"supporting_document_id", "notes", "sick_pay"} & result.keys()


def test_maternity_is_calendar_months_not_a_fixed_90_day_bank():
    db, _ = fixture(); db.leave_evidence.docs = [{"_id": ObjectId(), "id": "doc", "tenant_id": "solvit", "employee_id": "staff", "document_type": "maternity_confirmation"}]
    with patch.object(policy, "today", return_value=date(2026, 1, 1)):
        result = run(policy.preview(db, db.employees.docs[0], payload(leave_type="Maternity", start_date="2026-03-01", end_date="2026-05-31", expected_delivery_date="2026-03-20", supporting_document_id="doc")))
    assert result["calendar_days"] == 92


def test_paternity_window_and_compassionate_family_rule():
    db, _ = fixture(); db.leave_evidence.docs = [{"_id": ObjectId(), "id": "birth", "tenant_id": "solvit", "employee_id": "staff", "document_type": "birth_notification"}]
    with pytest.raises(HTTPException): run(policy.preview(db, db.employees.docs[0], payload(leave_type="Paternity", birth_date="2026-01-01", supporting_document_id="birth")))
    with pytest.raises(HTTPException): run(policy.preview(db, db.employees.docs[0], payload(leave_type="Compassionate", family_relationship="cousin")))
    result = run(policy.preview(db, db.employees.docs[0], payload(leave_type="Compassionate", family_relationship="parent", end_date="2026-11-30")))
    assert result["compassionate_paid_days"] == 14 and result["compassionate_unpaid_days"] > 0


def test_future_pending_withdrawal_is_owned_and_keeps_history_and_balance():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()): row = run(workflow.create(db, actors["staff"], payload(), loader))
    with pytest.raises(HTTPException): run(workflow.cancel(db, actors["boss"], row["id"], "forged"))
    cancelled = run(workflow.cancel(db, actors["staff"], row["id"], "Plans changed"))
    assert cancelled["status"] == "Cancelled" and len(cancelled["approval_history"]) == 2
    assert run(workflow.availability(db, db.employees.docs[0], loader.return_value)) == 21
    assert db.leave_balances.writes == 0 and db.leave_requests.docs[0]["working_days"] == 2


def test_approved_leave_cannot_be_self_cancelled_and_other_department_approval_does_not_block():
    db, actors = fixture()
    row = {"_id": ObjectId(), "id": "approved", "employee_id": "staff", "tenant_id": "solvit", "start_date": "2026-11-05", "end_date": "2026-11-06", "status": "Approved"}
    db.leave_requests.docs = [row]
    with pytest.raises(HTTPException): run(workflow.cancel(db, actors["staff"], "approved", "no"))
    db.leave_requests.docs.append({**row, "_id": ObjectId(), "id": "peer", "employee_id": "cover"})
    with pytest.raises(HTTPException): run(policy.department_cover(db, db.employees.docs[0], row))
    db.leave_requests.docs[-1]["employee_id"] = "other"
    run(policy.department_cover(db, db.employees.docs[0], row))


def test_stored_balance_values_are_preserved_and_unknown_snapshot_period_does_not_grant_new_credit():
    db, _ = fixture(); snapshot = {"_id": ObjectId(), "employee_id": "staff", "tenant_id": "solvit", "annual_remaining_days": 9.25, "sick_remaining_days": 12.5}
    db.leave_balances.docs = [snapshot]; before = deepcopy(snapshot)
    with patch("routes.leave._active_leave_types", AsyncMock(return_value=leave.LEAVE_TYPE_DETAILS)):
        result = run(balances(db, db.employees.docs[0]))
    assert result["annual_days_remaining"] == 9.25 and result["sick_days_remaining"] == 12.5
    assert result["annual_available_to_request"] is None
    assert db.leave_balances.docs == [before] and db.leave_balances.writes == 0


def test_missing_manager_and_ineligible_employee_have_no_request_writes():
    db, actors = fixture(); db.employees.docs[0]["line_manager_id"] = "missing"
    with pytest.raises(HTTPException): run(workflow.create(db, actors["staff"], payload(), budget()))
    db.employees.docs[0]["line_manager_id"] = "boss"; db.employees.docs[0]["lifecycle_state"] = "Exited"
    with pytest.raises(HTTPException): run(workflow.create(db, actors["staff"], payload(), budget()))
    assert db.leave_requests.writes == 0


def test_ai_cannot_skip_checked_approval_and_cannot_reject_foreign_or_own_requests():
    db, actors = fixture()
    assert run(ai_actions.execute_approve_leave(db, {"leave_id": "forged"}, actors["hr"]))["ok"] is False
    db.leave_requests.docs = [{"_id": ObjectId(), "id": "leave", "tenant_id": "solvit", "employee_id": "staff", "status": "Pending_Manager"}]
    with pytest.raises(HTTPException): run(ai_actions.execute_reject_leave(db, {"leave_id": "leave"}, actors["staff"]))
    assert db.leave_requests.writes == 0


def test_uploaded_evidence_is_private_and_cannot_be_downloaded_by_manager(tmp_path, monkeypatch):
    db, actors = fixture(); monkeypatch.setenv("LEAVE_EVIDENCE_ROOT", str(tmp_path))
    upload = UploadFile(file=BytesIO(b"%PDF-1.7\nSynthetic test document\n%%EOF"), filename="unsafe-name.pdf")
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actors["staff"])), patch.object(leave.document_uploads, "scan_content", AsyncMock()):
        doc = run(leave.upload_leave_evidence(None, upload, "medical_certificate", None))
        assert run(leave.download_leave_evidence(doc["id"], None)).headers["cache-control"] == "no-store"
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actors["boss"])):
        with pytest.raises(HTTPException): run(leave.download_leave_evidence(doc["id"], None))
    assert "storage_name" not in doc and len(list(tmp_path.iterdir())) == 1


def test_actual_mongo_serializes_overlapping_creation_across_writers():
    async def exercise():
        async with local_database() as db:
            fake, actors = fixture(); await db.employees.insert_many(fake.employees.docs); await db.users.insert_many(fake.users.docs)
            async def create_one():
                try: return await workflow.create(db, actors["staff"], payload(), budget())
                except HTTPException as error: return error.status_code
            with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()): results = await asyncio.gather(create_one(), create_one())
            assert 409 in results and await db.leave_requests.count_documents({}) == 1
    run(exercise())


def test_late_manager_handover_signoff_is_rejected_without_approval(monkeypatch):
    db, actors = fixture()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), budget()))
        monkeypatch.setattr(workflow, "today", lambda: date(2026, 11, 5))
        with pytest.raises(HTTPException) as error:
            run(workflow.decide(db, actors["boss"], row["id"], {"decision": "Approve", "handover_reviewed": True}, budget()))
    assert error.value.status_code == 422
    assert db.leave_requests.docs[0]["status"] == "Pending_Manager"


def test_legacy_form_cannot_bypass_checked_leave_workflow():
    from routes import forms
    db, actors = fixture()
    request = SimpleNamespace(json=AsyncMock(return_value={"employee_id": "staff", "data": {}}))
    with patch.object(forms, "get_db", return_value=db), patch.object(forms, "get_current_user", AsyncMock(return_value=actors["staff"])):
        for operation in (forms.start_form_submission, forms.submit_form):
            with pytest.raises(HTTPException) as error:
                run(operation("form-15", request))
            assert error.value.status_code == 409
    assert db.form_submissions.writes == 0
