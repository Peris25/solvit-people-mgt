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


def test_hr_receives_new_leave_review_with_safe_current_notification_preview():
    from utils.notification_centre import list_inbox
    db, actors = fixture(); db.notification_receipts = Collection()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        created = run(workflow.create(db, actors["staff"], payload(notes="PRIVATE medical and banking information"), budget()))
    inbox = run(list_inbox(db, actors["hr"]))
    item = next(item for item in inbox["items"] if item["action"])
    assert item["title"] == "Leave awaiting HR review"
    assert "approve or deny" in item["message"] and "PRIVATE" not in str(inbox)
    assert "view=team" in item["link"] and item["action"]["stage"] == "hr"
    stored = db.leave_requests.docs[0]; stored["status"] = "Approved"
    updated = run(list_inbox(db, actors["hr"]))["items"][0]
    assert updated["title"] == "Leave approved" and updated["action"] is None


def test_display_balance_increases_with_month_and_decreases_with_approved_usage_without_writes(monkeypatch):
    from datetime import datetime, timezone
    from utils import leave_balances
    db, _ = fixture(); employee = db.employees.docs[0]
    class Clock(datetime):
        month_value = 10
        @classmethod
        def now(cls, tz=None): return datetime(2026, cls.month_value, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(leave_balances, "datetime", Clock)
    with patch.object(leave, "_active_leave_types", AsyncMock(return_value=leave.LEAVE_TYPES)):
        october = run(balances(db, employee))
        Clock.month_value = 11
        november = run(balances(db, employee))
        db.leave_requests.docs = [{"_id": ObjectId(), "employee_id": "staff", "tenant_id": "solvit", "start_date": "2026-10-01", "leave_type": "Annual", "working_days": 2.5, "status": "Approved"}]
        after_leave = run(balances(db, employee))
    assert november["annual_available_to_request"] - october["annual_available_to_request"] == 1.75
    assert november["annual_available_to_request"] - after_leave["annual_available_to_request"] == 2.5
    assert db.leave_balances.writes == 0


def test_hr_direct_approval_requires_reason_and_policy_checks_and_records_override():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), loader))
        assert run(workflow.view(db, actors["hr"], db.leave_requests.docs[0]))["can_hr_override"]
        body = {"decision": "Approve", "hr_override": True, "stage": "hr", "reason": "Manager unavailable; HR reviewed request", "handover_reviewed": True, "policy_review_confirmed": True}
        with pytest.raises(HTTPException): run(workflow.decide(db, actors["hr"], row["id"], {**body, "reason": ""}, loader))
        with pytest.raises(HTTPException): run(workflow.decide(db, actors["hr"], row["id"], {**body, "policy_review_confirmed": False}, loader))
        approved = run(workflow.decide(db, actors["hr"], row["id"], body, loader))
        replay = run(workflow.decide(db, actors["hr"], row["id"], body, loader))
    assert approved["status"] == replay["status"] == "Approved"
    assert len(approved["approval_history"]) == 2
    assert approved["approval_history"][-1]["hr_override"] is True
    assert db.audit_logs.docs[-1]["hr_override"] is True
    assert db.employees.docs[0]["line_manager_id"] == "boss"


def test_employee_manager_and_self_cannot_forge_hr_override():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), loader))
        body = {"decision": "Approve", "hr_override": True, "reason": "Forged override", "handover_reviewed": True, "policy_review_confirmed": True}
        for actor in [actors["staff"], actors["boss"], {**actors["staff"], "role": "hr_admin"}]:
            with pytest.raises(HTTPException) as error: run(workflow.decide(db, actor, row["id"], body, loader))
            assert error.value.status_code == 403
    assert db.leave_requests.docs[0]["status"] == "Pending_Manager"


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


@pytest.mark.parametrize("kind,extra", [("Annual", {}), ("Sick", {"emergency_sick": True})])
def test_past_dates_cannot_be_submitted_even_with_emergency_or_notice_reason(kind, extra):
    db, actors = fixture()
    data = payload(leave_type=kind, start_date="2026-09-10", end_date="2026-09-11", short_notice_reason="A reason cannot authorize backdated applications", **extra)
    with pytest.raises(HTTPException, match="Past dates"):
        run(workflow.create(db, actors["staff"], data, budget()))
    assert db.leave_requests.docs == []


def test_short_notice_reason_allows_submission_but_does_not_approve_leave():
    db, actors = fixture()
    data = payload(start_date="2026-10-16", end_date="2026-10-17")
    for reason in (None, " ", "short"):
        with pytest.raises(HTTPException):
            run(workflow.create(db, actors["staff"], {**data, "short_notice_reason": reason}, budget()))
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        result = run(workflow.create(db, actors["staff"], {**data, "short_notice_reason": "Urgent family arrangements require short notice"}, budget()))
    assert result["status"] == "Pending_Manager"
    assert result["short_notice_reason"] == "Urgent family arrangements require short notice"
    assert db.leave_requests.docs[0]["policy_snapshot"]["short_notice"] is True
    assert db.leave_balances.writes == 0


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


def test_pending_edit_resubmits_same_record_with_recalculation_and_audit():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), loader))
    stored = db.leave_requests.docs[0]
    stored.update(status="Pending_HR", manager_decision="Approve", manager_decided_by=actors["boss"]["id"])
    result = run(workflow.supplement(db, actors["staff"], row["id"], {"end_date": "2026-11-09"}, balance_loader=loader))
    assert result["id"] == row["id"] and len(db.leave_requests.docs) == 1
    assert result["status"] == "Pending_Manager" and result["working_days"] == 3.5
    assert result["manager_decision"] is None and result["can_edit"] is True
    assert result["approval_history"][-1]["stage"] == "resubmitted"
    assert "2026-11-06" in result["approval_history"][-1]["reason"]
    assert db.audit_logs.docs[-1]["action"] == "leave.resubmitted"
    assert db.leave_balances.writes == 0


@pytest.mark.parametrize("status", ["Approved", "Rejected", "Denied", "Cancelled"])
def test_finalized_request_cannot_be_edited(status):
    db, actors = fixture()
    stored = {"_id": ObjectId(), "id": "final", "tenant_id": "solvit", **payload(), "status": status, "working_days": 2}
    db.leave_requests.docs = [stored]; before = deepcopy(stored)
    with pytest.raises(HTTPException):
        run(workflow.supplement(db, actors["staff"], "final", {"end_date": "2026-11-09"}, balance_loader=budget()))
    assert stored == before
    assert run(workflow.view(db, actors["staff"], stored))["can_edit"] is False


def test_edit_rejects_forged_identity_other_employee_overlap_and_insufficient_balance():
    db, actors = fixture(); loader = budget()
    with patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        row = run(workflow.create(db, actors["staff"], payload(), loader))
    for actor, changes, available in [
        (actors["other"], {"end_date": "2026-11-09"}, loader),
        (actors["boss"], {"end_date": "2026-11-09"}, loader),
        (actors["staff"], {"employee_id": "other"}, loader),
        (actors["staff"], {"status": "Approved"}, loader),
        (actors["staff"], {"end_date": "2026-11-09"}, AsyncMock(return_value={"Annual": {"remaining": 1}, "year": 2026})),
    ]:
        before = deepcopy(db.leave_requests.docs)
        with pytest.raises(HTTPException):
            run(workflow.supplement(db, actor, row["id"], changes, balance_loader=available))
        assert db.leave_requests.docs == before
    db.leave_requests.docs.append({"_id": ObjectId(), "id": "clash", "tenant_id": "solvit", **payload(start_date="2026-11-09", end_date="2026-11-10"), "status": "Approved", "working_days": 2})
    with pytest.raises(HTTPException):
        run(workflow.supplement(db, actors["staff"], row["id"], {"end_date": "2026-11-09"}, balance_loader=loader))
    assert db.leave_balances.writes == 0 and db.leave_requests.docs[0]["working_days"] == 2


def test_started_and_historical_requests_cannot_be_resubmitted():
    for extra in ({"start_date": "2026-10-14"}, {"historical_import": True}):
        db, actors = fixture()
        record = {"_id": ObjectId(), "id": "locked", "tenant_id": "solvit", **payload(), "status": "Pending_Manager", "working_days": 2, **extra}
        db.leave_requests.docs = [record]; before = deepcopy(record)
        with pytest.raises(HTTPException):
            run(workflow.supplement(db, actors["staff"], "locked", {"start_date": "2026-11-09"}, balance_loader=budget()))
        assert record == before


def test_authorized_leave_list_does_not_silently_stop_at_200_records():
    db, actors = fixture()
    db.leave_requests.docs = [{"_id": ObjectId(), "id": str(index), "tenant_id": "solvit", **payload(), "status": "Pending_Manager", "working_days": 2} for index in range(205)]
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actors["staff"])):
        result = run(leave.list_leave_requests(SimpleNamespace()))
    assert len(result) == 205
    assert {row["employee_id"] for row in result} == {"staff"}


def test_leave_list_reuses_authorization_only_inside_one_request():
    db, actors = fixture()
    db.leave_requests.docs = [{"_id": ObjectId(), "id": str(index), "tenant_id": "solvit", **payload(), "status": "Approved", "historical_import": True, "working_days": 2} for index in range(20)]
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actors["staff"])), patch.object(leave, "authorize_employee", wraps=leave.authorize_employee) as authorize:
        result = run(leave.list_leave_requests(SimpleNamespace()))
        assert len(result) == 20 and authorize.call_count == 1
        run(leave.list_leave_requests(SimpleNamespace()))
        assert authorize.call_count == 2  # No worker-local permission cache.


def test_leave_list_overlaps_identity_lookups_with_bounded_concurrency():
    db, actors = fixture()
    db.leave_requests.docs = [{"_id": ObjectId(), "id": str(index), "tenant_id": "solvit", **payload(employee_id=employee_id), "status": "Approved", "historical_import": True, "working_days": 2} for index, employee_id in enumerate(['staff', 'cover', 'boss', 'other', 'other-boss'])]
    running = maximum = 0
    actual = leave.authorize_employee
    async def measured(*args, **kwargs):
        nonlocal running, maximum
        running += 1; maximum = max(maximum, running)
        try:
            await asyncio.sleep(0.01)
            return await actual(*args, **kwargs)
        finally: running -= 1
    with patch.object(leave, 'get_db', return_value=db), patch.object(leave, 'get_current_user', AsyncMock(return_value=actors['hr'])), patch.object(leave, 'authorize_employee', side_effect=measured):
        result = run(leave.list_leave_requests(SimpleNamespace()))
    assert len(result) == 5 and 1 < maximum <= 6


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
