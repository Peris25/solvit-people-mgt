"""Synthetic history transcription, authorization and correction regressions."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from utils import leave_history as history
from utils.leave_workflow import decide, cancel, supplement, view
from .test_leave_management import fixture, run


def row(**values):
    return {"work_email": "staff@example.com", "source_key": "synthetic-workbook:sheet:2", "source_reference": "Synthetic workbook / sheet / row 2",
            "leave_type": "Annual", "start_date": "2026-01-05", "end_date": "2026-01-06", "working_days": 1.5,
            "status": "Recorded", **values}


def import_one(db, user, **values):
    batch = history.HistoricalBatch(rows=[row(**values)])
    _, digest = run(history.prepare(db, user, batch))
    batch.preview_digest = digest
    return run(history.import_rows(db, user, batch))


@pytest.mark.parametrize("role", ["employee", "line_manager", "finance", "executive", "it_admin"])
def test_only_hr_can_import_or_correct_history(role):
    db, actors = fixture()
    actor = {**actors["staff"], "role": role}
    with pytest.raises(HTTPException) as error:
        run(history.prepare(db, actor, history.HistoricalBatch(rows=[row()])))
    assert error.value.status_code == 403 and not db.leave_requests.docs


def test_legacy_identity_match_keeps_units_does_not_notify_or_change_snapshots():
    db, actors = fixture()
    before = deepcopy(db.employees.docs)
    result = import_one(db, actors["hr"], work_email=" STAFF@EXAMPLE.COM ")
    assert result == {"created": 1, "skipped": 0}
    record = db.leave_requests.docs[0]
    assert record["employee_id"] == "staff" and record["working_days"] == 1.5 and record["status"] == "Recorded"
    assert not db.notifications.docs and not db.leave_balances.docs and db.employees.docs == before
    assert db.audit_logs.docs[0]["action"] == "leave.history.import"
    assert run(view(db, actors["hr"], record))["can_correct_history"] is True
    assert run(view(db, actors["staff"], record))["can_correct_history"] is False
    with pytest.raises(HTTPException): run(view(db, actors["other"], record))


def test_import_retry_skips_existing_and_missing_preview_writes_nothing():
    db, actors = fixture()
    with pytest.raises(HTTPException): run(history.import_rows(db, actors["hr"], history.HistoricalBatch(rows=[row()])))
    assert not db.leave_requests.docs
    import_one(db, actors["hr"])
    assert import_one(db, actors["hr"]) == {"created": 0, "skipped": 1}
    assert len(db.leave_requests.docs) == 1


@pytest.mark.parametrize("email", ["missing@example.com", "ambiguous@example.com"])
def test_missing_or_duplicate_employees_block_import(email):
    db, actors = fixture()
    if email.startswith("ambiguous"):
        for employee in db.employees.docs[:2]: employee["work_email"] = email
    with pytest.raises(HTTPException): import_one(db, actors["hr"], work_email=email)
    assert not db.leave_requests.docs


def test_duplicate_source_or_overlapping_period_is_rejected():
    db, actors = fixture()
    with pytest.raises(HTTPException): run(history.prepare(db, actors["hr"], history.HistoricalBatch(rows=[row(), row()])))
    import_one(db, actors["hr"])
    with pytest.raises(HTTPException): import_one(db, actors["hr"], source_key="different-source-row")
    assert len(db.leave_requests.docs) == 1


def test_correction_requires_revision_and_reason_and_preserves_source_identity():
    db, actors = fixture(); import_one(db, actors["hr"])
    record = deepcopy(db.leave_requests.docs[0])
    fields = {key: record.get(key) for key in history.HistoricalFields.model_fields}
    body = history.HistoricalCorrection(**{**fields, "working_days": 2}, revision=1, reason="Verified source correction")
    updated = run(history.correct(db, actors["hr"], record["id"], body))
    assert updated["working_days"] == 2 and updated["revision"] == 2
    assert db.leave_requests.docs[0]["employee_id"] == record["employee_id"]
    assert db.leave_requests.docs[0]["source_key"] == record["source_key"]
    assert db.audit_logs.docs[-1]["before"]["working_days"] == 1.5
    with pytest.raises(HTTPException): run(history.correct(db, actors["hr"], record["id"], body))
    assert import_one(db, actors["hr"])["skipped"] == 1
    assert db.leave_requests.docs[0]["working_days"] == 2


def test_non_hr_correction_is_denied_and_live_records_cannot_be_rewritten():
    db, actors = fixture(); import_one(db, actors["hr"])
    record = db.leave_requests.docs[0]
    fields = {key: record.get(key) for key in history.HistoricalFields.model_fields}
    body = history.HistoricalCorrection(**fields, revision=1, reason="Synthetic correction")
    for actor in [actors["staff"], actors["boss"]]:
        with pytest.raises(HTTPException) as error: run(history.correct(db, actor, record["id"], body))
        assert error.value.status_code == 403
    record["historical_import"] = False
    with pytest.raises(HTTPException) as error: run(history.correct(db, actors["hr"], record["id"], body))
    assert error.value.status_code == 409


def test_saved_balance_is_preserved_and_requires_reconciliation_after_import():
    from utils.leave_balances import balances
    from datetime import datetime, timezone
    db, actors = fixture()
    year = datetime.now(timezone.utc).year
    db.leave_balances.docs = [{"employee_id": "staff", "tenant_id": "solvit", "year": year, "Annual": {"remaining": 12}}]
    before = deepcopy(db.leave_balances.docs)
    import_one(db, actors["hr"], start_date=f"{year}-01-05", end_date=f"{year}-01-06", status="Approved")
    result = run(balances(db, db.employees.docs[0]))
    assert result["Annual"]["remaining"] == 12
    assert result["annual_available_to_request"] is None and result["historical_balance_review"] is True
    assert db.leave_balances.docs == before


def test_historical_pending_cannot_use_live_approval_cancel_or_supplement():
    db, actors = fixture(); import_one(db, actors["hr"], status="Pending")
    record = db.leave_requests.docs[0]
    for action in [decide(db, actors["hr"], record["id"], {"decision": "Approve"}, AsyncMock()),
                   cancel(db, actors["staff"], record["id"], "Withdraw"), supplement(db, actors["staff"], record["id"], {})]:
        with pytest.raises(HTTPException) as error: run(action)
        assert error.value.status_code == 409


def test_audit_failure_prevents_import_write():
    db, actors = fixture(); db.audit_logs.insert_one = AsyncMock(side_effect=RuntimeError("synthetic unavailable audit"))
    with pytest.raises(RuntimeError): import_one(db, actors["hr"])
    assert not db.leave_requests.docs


@pytest.mark.parametrize("changes", [{"working_days": -1}, {"working_days": float('nan')}, {"working_days": True},
    {"working_days": 4}, {"status": "Invented"}, {"end_date": "2025-01-01"}, {"employee_id": "forged"}])
def test_bad_values_and_identity_fields_are_rejected(changes):
    with pytest.raises(ValidationError): history.HistoricalRow(**row(**changes))
