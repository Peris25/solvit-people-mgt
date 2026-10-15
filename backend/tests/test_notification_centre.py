"""Notification recipient, privacy, receipt and existing-event regressions."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from utils.notification_centre import list_inbox, read_notification
from automation.engine import AutomationEngine
from routes import leave
from .integrity_fakes import Database, Collection, employee, account
from .test_employee_integrity_mongo import local_database


class Receipts(Collection):
    async def update_one(self, query, update, upsert=False):
        if "$setOnInsert" in update:
            existing = await self.find_one(query)
            if not existing:
                await self.insert_one({**query, **update["$setOnInsert"]})
            return SimpleNamespace(modified_count=0)
        return await super().update_one(query, update, upsert)


def fixture():
    employees = [employee("staff", line_manager_id="boss"), employee("boss", email="boss@example.com"),
                 employee("other", email="other@example.com", line_manager_id="other-boss"),
                 employee("other-boss", email="other-boss@example.com")]
    users = [account(employee_id=emp["id"], email=emp["work_email"], role="line_manager" if "boss" in emp["id"] else "employee") for emp in employees]
    db = Database(employees, users)
    db.notifications = Collection(); db.notification_receipts = Receipts()
    db.leave_requests = Collection(); db.training_requests = Collection(); db.solvers = Collection()
    actors = {u["employee_id"]: {**u, "id": str(u["_id"])} for u in users}
    return db, actors


def notice(**values):
    return {"_id": ObjectId(), "id": str(ObjectId()), "tenant_id": "solvit", "recipient_role": "employee",
            "title": "Secret salary and medical title", "message": "PRIVATE-BANK-MEDICAL-REASON", "category": "Leave",
            "is_read": False, "created_at": "2026-10-01T10:00:00Z", **values}


def run(coro): return asyncio.run(coro)


@pytest.mark.parametrize("recipient", ["account", "employee", "storage", "native", "user_id", "role"])
def test_supported_recipient_formats_are_readable_without_private_previews(recipient):
    db, actors = fixture(); user = actors["staff"]
    values = {"recipient_id": user["id"]}
    if recipient == "employee": values["recipient_id"] = "staff"
    if recipient in ("storage", "native"): values["recipient_id"] = str(db.employees.docs[0]["_id"]) if recipient == "storage" else db.employees.docs[0]["_id"]
    if recipient == "user_id": values = {"user_id": user["id"]}
    if recipient == "role": values = {}
    row = notice(**values); db.notifications.docs = [row]
    result = run(list_inbox(db, user))
    assert result["unread_count"] == 1 and result["total"] == 1
    assert result["items"][0]["id"] == str(row["_id"])
    assert "PRIVATE" not in str(result) and "Secret" not in str(result)
    assert "data" not in result["items"][0]
    assert db.notifications.writes == db.notification_receipts.writes == 0


@pytest.mark.parametrize("case", ["different_recipient", "conflicting_user", "foreign_tenant", "other_subject", "other_role", "malformed_data", "wrong_recipient_type"])
def test_another_employees_notification_cannot_be_read_or_marked_by_forged_ids(case):
    db, actors = fixture(); user = actors["staff"]
    row = notice(recipient_id="staff")
    changes = {
        "different_recipient": {"recipient_id": "other"}, "conflicting_user": {"user_id": actors["other"]["id"]},
        "foreign_tenant": {"tenant_id": "foreign"}, "other_subject": {"data": {"employee_id": "other"}},
        "other_role": {"recipient_id": None, "recipient_role": "hr_admin"}, "malformed_data": {"data": "private"},
        "wrong_recipient_type": {"recipient_type": "account"},
    }
    row.update(changes[case]); db.notifications.docs = [row]
    assert run(list_inbox(db, user))["items"] == []
    with pytest.raises(HTTPException): run(read_notification(db, user, str(row["_id"])))
    assert db.notification_receipts.writes == 0 and db.notifications.writes == 0


@pytest.mark.parametrize("status", ["Exited", "Terminated", "Inactive", "Candidate", "unknown"])
def test_ineligible_employee_status_cannot_access_the_inbox(status):
    db, actors = fixture(); db.employees.docs[0]["lifecycle_state"] = status
    with pytest.raises(HTTPException) as error: run(list_inbox(db, actors["staff"]))
    assert error.value.status_code == 403


def test_restricted_board_record_does_not_grant_ordinary_staff_visibility():
    db, actors = fixture(); db.employees.docs[0]["board_only"] = True
    with pytest.raises(HTTPException): run(list_inbox(db, actors["staff"]))


@pytest.mark.parametrize("state", ["Active", "Suspended", "Inactive"])
def test_solver_own_inbox_uses_saved_solver_identity_and_status_without_fte_access(state):
    db, _ = fixture()
    solver = {"_id": ObjectId(), "id": "solver-one", "tenant_id": "solvit", "email": "solver@example.com", "lifecycle_state": state}
    owner = account(email="solver@example.com", role="solver", solver_id="solver-one")
    db.solvers.docs = [solver]; db.users.docs.append(owner)
    user = {**owner, "id": str(owner["_id"])}
    own = notice(recipient_id="solver-one", recipient_type="solver", category="Performance", data={"solver_id": "solver-one"})
    other = notice(recipient_role="solver", data={"employee_id": "staff"})
    db.notifications.docs = [own, other]
    if state != "Active":
        with pytest.raises(HTTPException): run(list_inbox(db, user))
    else:
        result = run(list_inbox(db, user))
        assert len(result["items"]) == 1 and result["items"][0]["id"] == str(own["_id"])


def test_broadcast_receipts_are_per_account_idempotent_and_do_not_change_source():
    db, actors = fixture(); row = notice(); db.notifications.docs = [row]
    before = deepcopy(row)
    run(read_notification(db, actors["staff"], str(row["_id"])))
    first = deepcopy(db.notification_receipts.docs)
    run(read_notification(db, actors["staff"], str(row["_id"])))
    assert db.notification_receipts.docs == first and db.notification_receipts.writes == 1
    assert run(list_inbox(db, actors["staff"]))["unread_count"] == 0
    assert run(list_inbox(db, actors["other"]))["unread_count"] == 1
    assert db.notifications.docs[0] == before


def test_legacy_read_baseline_filters_counts_and_date_sorting_are_consistent():
    db, actors = fixture()
    newer = notice(category="Training", created_at="2026-10-01T13:00:00+03:00")
    older = notice(category="Onboarding", is_read=True, created_at="2026-09-01T09:00:00Z")
    newest = notice(category="Announcement", created_at="2026-10-02T09:00:00Z")
    db.notifications.docs = [older, newer, newest]
    all_rows = run(list_inbox(db, actors["staff"], limit=1))
    assert all_rows["items"][0]["id"] == str(newest["_id"])
    assert all_rows["unread_count"] == 2 and all_rows["total"] == 3
    assert all_rows["categories"] == ["Onboarding", "Training", "Announcements"]
    result = run(list_inbox(db, actors["staff"], read_status="read"))
    assert result["filtered_total"] == 1 and result["items"][0]["is_read"] is True
    assert run(list_inbox(db, actors["staff"], category="Training", kind="Action required"))["filtered_total"] == 1
    assert run(list_inbox(db, actors["staff"], offset=1, limit=1))["items"][0]["id"] == str(newer["_id"])


def test_manager_can_only_open_and_approve_saved_direct_reports_leave():
    db, actors = fixture()
    request = {"_id": ObjectId(), "id": "leave", "tenant_id": "solvit", "employee_id": "staff", "status": "Pending_Manager"}
    db.leave_requests.docs = [request]
    own = notice(recipient_id="boss", recipient_type="employee", data={"employee_id": "staff", "leave_request_id": "leave"})
    foreign = notice(recipient_role="line_manager", data={"employee_id": "other", "leave_request_id": "leave"})
    db.notifications.docs = [own, foreign]
    result = run(list_inbox(db, actors["boss"]))
    assert len(result["items"]) == 1
    assert result["items"][0]["link"] == f"/leave?request={request['_id']}&view=team"
    assert result["items"][0]["action"] == {"kind": "leave_review", "record_id": str(request["_id"]), "stage": "manager"}
    assert result["items"][0]["kind"] == "Approvals"
    assert run(list_inbox(db, actors["other-boss"]))["items"][0]["link"] is None


@pytest.mark.parametrize("target", ["missing", "foreign", "conflicting", "external"])
def test_missing_foreign_conflicting_or_arbitrary_links_are_never_exposed(target):
    db, actors = fixture()
    row = notice(recipient_id="staff", data={"employee_id": "staff", "leave_request_id": "target"}, link="https://external.example/private", url="javascript:alert(1)")
    if target == "foreign": db.leave_requests.docs = [{"id": "target", "_id": ObjectId(), "tenant_id": "foreign", "employee_id": "staff"}]
    if target == "conflicting": db.leave_requests.docs = [{"id": "target", "_id": ObjectId(), "tenant_id": "solvit", "employee_id": "other"}]
    if target == "external": row["data"] = {}
    db.notifications.docs = [row]
    item = run(list_inbox(db, actors["staff"]))["items"][0]
    assert item["link"] is None and item["action"] is None
    assert "external.example" not in str(item) and "javascript" not in str(item)


def test_duplicate_notification_reference_cannot_mark_arbitrary_record():
    db, actors = fixture(); db.notifications.docs = [notice(id="same"), notice(id="same")]
    with pytest.raises(HTTPException) as error: run(read_notification(db, actors["staff"], "same"))
    assert error.value.status_code == 409 and db.notification_receipts.writes == 0


def test_legacy_account_employee_identifier_collision_fails_closed():
    db, actors = fixture(); user = actors["staff"]
    db.employees.docs[2]["id"] = user["id"]
    db.notifications.docs = [notice(recipient_id=user["id"])]
    assert run(list_inbox(db, user))["items"] == []


def test_existing_leave_event_is_targeted_and_repeated_dispatch_does_not_duplicate_or_email():
    db, actors = fixture(); engine = AutomationEngine(); engine.db = db
    rule = {"rule_id": "AR-LV-01", "category": "Leave", "notification_recipients_json": ["line_manager"]}
    data = {"employee_id": "staff", "leave_request_id": "source"}
    with patch("utils.email_service.send_email", AsyncMock()) as email:
        run(engine._send_notification_action(rule, data, {})); run(engine._send_notification_action(rule, data, {}))
        email.assert_not_awaited()
    assert len(db.notifications.docs) == 1 and db.notifications.docs[0]["recipient_id"] == "boss"
    assert run(list_inbox(db, actors["other-boss"]))["items"] == []
    assert run(list_inbox(db, actors["boss"]))["total"] == 1


def test_exact_leave_decision_retry_does_not_duplicate_employee_notification():
    db, actors = fixture()
    db.leave_requests.docs = [{"_id": ObjectId(), "id": "leave", "tenant_id": "solvit", "employee_id": "staff", "status": "Pending_Manager"}]
    req = SimpleNamespace(json=AsyncMock(return_value={"decision": "Reject"}))
    with patch.object(leave, "get_db", return_value=db), patch.object(leave, "get_current_user", AsyncMock(return_value=actors["boss"])), patch("utils.email_service.send_email", AsyncMock()), patch("automation.engine.automation_engine.fire_event", AsyncMock()):
        run(leave.leave_decision("leave", req)); run(leave.leave_decision("leave", req))
    assert len(db.notifications.docs) == 1 and db.leave_requests.writes == 1
    item = run(list_inbox(db, actors["staff"]))["items"][0]
    assert item["link"] and item["action"] is None


def test_real_mongo_concurrent_receipts_and_leave_event_dispatch_use_only_builtin_id_uniqueness():
    async def exercise():
        async with local_database() as db:
            fake, actors = fixture()
            await db.employees.insert_many(fake.employees.docs); await db.users.insert_many(fake.users.docs)
            row = notice(); await db.notifications.insert_one(row)
            await asyncio.gather(*(read_notification(db, actors["staff"], str(row["_id"])) for _ in range(8)))
            assert await db.notification_receipts.count_documents({}) == 1
            assert (await list_inbox(db, actors["staff"]))["unread_count"] == 0
            assert (await list_inbox(db, actors["other"]))["unread_count"] == 1
            engine = AutomationEngine(); engine.db = db
            rule = {"rule_id": "AR-LV-01", "category": "Leave", "notification_recipients_json": ["line_manager"]}
            await asyncio.gather(*(engine._send_notification_action(rule, {"employee_id": "staff", "leave_request_id": "source"}, {}) for _ in range(8)))
            assert await db.notifications.count_documents({"rule_id": "AR-LV-01"}) == 1
    run(exercise())
