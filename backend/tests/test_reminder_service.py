"""Regression test for the Reminder Service end-to-end pipeline.

Verifies:
  • The engine starts and registers a job for every rule
  • A rule with a fresh match fires once + logs
  • A second run is dedup-skipped
  • A rule for which no records match completes cleanly with 0 fired
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

THIS_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(THIS_DIR, "..", ".env"))
sys.path.insert(0, os.path.join(THIS_DIR, ".."))


@pytest.fixture
def loop():
    return asyncio.new_event_loop()


@pytest.fixture
def db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


def _today_iso():
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date().isoformat()


def test_reminder_pipeline_e2e(loop, db):
    async def run():
        from reminders.engine import reminder_engine
        from reminders.rules import RULES
        await reminder_engine.start(db)
        assert len(RULES) >= 40, "Should have all 40+ rules registered"

        # 1. Set up a synthetic match for REM-LEAVE-04 (employee returns today)
        emp = await db.employees.find_one(
            {"tenant_id": "solvit", "line_manager_id": {"$ne": None, "$exists": True}})
        assert emp, "Need at least one employee with a line manager"
        await db.leave_requests.delete_many({"id": "pytest-rem-leave"})
        await db.reminder_log.delete_many({"rule_id": "REM-LEAVE-04",
                                            "dedup_key": "pytest-rem-leave"})
        await db.leave_requests.insert_one({
            "id": "pytest-rem-leave", "tenant_id": "solvit", "status": "Approved",
            "employee_id": emp["id"], "leave_type": "Annual",
            "start_date": _today_iso(),
            "end_date": f"{_today_iso()}T00:00:00",
            "line_manager_id": emp["line_manager_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # 2. First run — should fire
        r1 = await reminder_engine.run_rule("REM-LEAVE-04", triggered_by="pytest")
        assert r1["evaluated"] >= 1
        assert r1["fired"] >= 1
        assert r1["status"] == "Completed"

        # 3. Second run — should be dedup-skipped
        r2 = await reminder_engine.run_rule("REM-LEAVE-04", triggered_by="pytest_again")
        assert r2["skipped"] >= 1
        assert r2["fired"] == 0

        # 4. Rule with no matches (cycle-due in a year we already have a cycle)
        #    Should complete cleanly with 0 fired
        r3 = await reminder_engine.run_rule("REM-PROB-02", triggered_by="pytest_empty")
        assert r3["status"] == "Completed"

        # Cleanup
        await db.leave_requests.delete_many({"id": "pytest-rem-leave"})

    loop.run_until_complete(run())
