"""Optional real Mongo tests: explicitly opted-in disposable localhost DB only."""
import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.employee_integrity import integrity_write, insert_employee, email_matches, validate_manager
from utils.integrity_audit import INDEX_PLAN
from .integrity_fakes import employee


@asynccontextmanager
async def local_database():
    uri = os.environ.get("LOCAL_MONGO_TEST_URI")
    if uri is None:
        pytest.skip("Disposable localhost MongoDB not explicitly selected")
    if uri != "mongodb://127.0.0.1:27089/":
        pytest.fail("Only the designated disposable localhost test instance is allowed")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    name = "codex_integrity_test_" + uuid.uuid4().hex
    db = client[name]
    try:
        await client.admin.command("ping")
        yield db
    finally:
        await client.drop_database(name)
        client.close()


def test_real_legacy_email_queries_and_cross_worker_lock():
    async def exercise():
        async with local_database() as db:
            boss = employee("boss", "boss@example.com")
            await db.employees.insert_one(boss)
            await db.employees.insert_one(employee(email=" STAFF@EXAMPLE.COM "))
            assert len(await email_matches(db.employees, "work_email", "staff@example.com", "solvit")) == 1
            async def create():
                try:
                    async with integrity_write(db):
                        return await insert_employee(db, {"id": str(uuid.uuid4()), "work_email": "new@example.com", "line_manager_id": str(boss["_id"])})
                except HTTPException as error:
                    return error.status_code
            results = await asyncio.gather(create(), create())
            assert 409 in results
            assert await db.employees.count_documents({"work_email_normalized": "new@example.com"}) == 1
            assert await db.integrity_locks.count_documents({}) == 0
            unchanged = await db.employees.find_one({"_id": boss["_id"]})
            assert unchanged == boss
    asyncio.run(exercise())


def test_proposed_unique_indexes_on_disposable_database_only():
    async def exercise():
        async with local_database() as db:
            for spec in INDEX_PLAN:
                options = {k: v for k, v in spec.items() if k not in ("collection", "keys")}
                await db[spec["collection"]].create_index(spec["keys"], **options)
            await db.employees.insert_one({"id": "staff", "tenant_id": "solvit", "work_email_normalized": "staff@example.com"})
            with pytest.raises(DuplicateKeyError):
                await db.employees.insert_one({"id": "different", "tenant_id": "solvit", "work_email_normalized": "staff@example.com"})
            await db.users.insert_one({"tenant_id": "solvit", "employee_id": "staff", "email_normalized": "staff@example.com"})
            with pytest.raises(DuplicateKeyError):
                await db.users.insert_one({"tenant_id": "solvit", "employee_id": "staff", "email_normalized": "other@example.com"})
            with pytest.raises(DuplicateKeyError):
                await db.users.insert_one({"tenant_id": "other", "email_normalized": "staff@example.com"})
            # Missing links/keys in legacy and explicit system records are allowed.
            await db.users.insert_one({"account_type": "system"})
            await db.users.insert_one({"account_type": "system"})
    asyncio.run(exercise())


def test_concurrent_reporting_changes_cannot_create_cycle():
    from routes import employees
    async def exercise():
        async with local_database() as db:
            await db.employees.insert_one(employee("first", "first@example.com"))
            await db.employees.insert_one(employee("second", "second@example.com"))
            async def assign(staff, manager):
                try:
                    return await employees.update_employee(staff, employees.EmployeeUpdate(line_manager_id=manager), None)
                except HTTPException as error:
                    return error.status_code
            with patch.object(employees, "get_db", return_value=db), patch.object(employees, "get_current_user", AsyncMock(return_value={"id": "hr", "role": "hr_admin"})):
                results = await asyncio.gather(assign("first", "second"), assign("second", "first"))
                assert sum(isinstance(r, dict) for r in results) == 1
                loser = 0 if isinstance(results[0], int) else 1
                retried = await assign("first", "second") if loser == 0 else await assign("second", "first")
                assert retried == 422
            docs = await db.employees.find({}).to_list(None)
            assert sum(bool(d.get("line_manager_id")) for d in docs) == 1
    asyncio.run(exercise())
