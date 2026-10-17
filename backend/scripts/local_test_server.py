"""Disposable full-suite SUT. Refuses production URLs/databases and outbound traffic."""
import ast
import asyncio
import os
import socket
import sys
import uuid
import re
from pathlib import Path

if os.environ.get("MONGO_URL") != "mongodb://127.0.0.1:27089/" or not os.environ.get("DB_NAME", "").startswith("codex_integrity_suite_"):
    raise SystemExit("Disposable localhost database configuration is required")
if os.environ.get("SOLVIT_LOCAL_INTEGRATION") != "1":
    raise SystemExit("Explicit local integration opt-in is required")

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
original_connect = socket.socket.connect


def local_connect(sock, address):
    if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "localhost", "::1"):
        raise OSError("External network access is disabled in the test SUT")
    return original_connect(sock, address)


socket.socket.connect = local_connect


async def initialize_synthetic_fixtures():
    from motor.motor_asyncio import AsyncIOMotorClient
    from utils.auth import hash_password
    from automation import seed_data
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await seed_data.seed_demo_employees(db)
    await seed_data.seed_pay_bands(db)
    await seed_data.seed_holidays(db)
    await seed_data.seed_automation_rules(db)
    await seed_data.seed_policies(db)
    # Addresses are legacy FIXTURE identifiers from the repository, not production
    # records. Passwords and account/employee IDs are freshly generated test values.
    roles = {}
    known = {"hr_admin", "hr_manager", "it_admin", "line_manager", "finance", "employee", "solver", "executive", "board"}
    for path in (Path(__file__).resolve().parents[1] / "tests").glob("test*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in known and isinstance(value, ast.Constant) and isinstance(value.value, str) and "@" in value.value:
                        roles[value.value.lower()] = key.value
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"[^\s@]+@solvit\.co\.ke", node.value):
                email = node.value.lower()
                local = email.split("@")[0]
                if local not in {"support", "itadmin", "jmining", "jessica", "hr", "hradmin", "hrmanager", "hr_manager", "hr.manager", "manager", "finance", "board", "md", "ed", "executive", "solver", "employee"}:
                    continue
                inferred = "it_admin" if local in ("support", "itadmin") else "hr_admin" if local in ("jmining", "jessica", "hr", "hradmin") else "hr_manager" if local in ("hrmanager", "hr_manager", "hr.manager") else "line_manager" if local == "manager" else "finance" if local == "finance" else "board" if local == "board" else "executive" if local in ("md", "ed", "executive") else "solver" if local == "solver" else "employee"
                roles.setdefault(email, inferred)
    password_hash = hash_password(os.environ["DEMO_SEED_PASSWORD"])
    for email, role in roles.items():
        employee = await db.employees.find_one({"work_email": email})
        if employee is None and role != "solver":
            employee = {"id": str(uuid.uuid4()), "tenant_id": "solvit", "work_email": email,
                        "full_name": "Synthetic " + role, "department": "Operations", "role_title": role,
                        "role_level": "L3", "lifecycle_state": "Active", "employment_type": "Full_Time", "start_date": "2025-01-01"}
            await db.employees.insert_one(employee)
        await db.users.insert_one({"tenant_id": "solvit", "email": email, "full_name": "Synthetic " + role,
                                   "role": role, "password_hash": password_hash, "is_active": True,
                                   "employee_id": employee["id"] if employee else None})
    # Supply the governance metadata explicitly required by the old HTTP
    # fixtures. These writes exist only in this disposable test initializer.
    seeded = await db.employees.find({}).to_list(None)
    for record in seeded:
        title = record.get("role_title", "").lower()
        if title in ("managing director", "executive director"):
            await db.employees.update_one({"_id": record["_id"]}, {"$set": {
                "board_only": True, "is_md": title == "managing director", "is_ed": title == "executive director"}})
        if title == "solvers manager":
            await db.employees.update_one({"_id": record["_id"]}, {"$set": {"reports_to_finance_ops": True}})
    await seed_data.seed_performance_reviews(db)
    await seed_data.seed_notifications_and_stay_interviews(db)
    baseline = {}
    for collection in await db.list_collection_names():
        baseline[collection] = await db[collection].find({}).to_list(None)
    client.close()
    return baseline


if __name__ == "__main__":
    # Only this guarded, outbound-blocked synthetic SUT substitutes the malware
    # verdict. Production routes retain fail-closed scanning; content validation
    # still runs unchanged in this local integration process.
    from utils import document_uploads
    async def synthetic_document_scan(content):
        return None
    document_uploads.scan_content = synthetic_document_scan
    fixture_baseline = asyncio.run(initialize_synthetic_fixtures())
    from server import app, SESSION_EXEMPT_ENDPOINTS
    from utils import security

    @app.post("/__test__/reset-fixtures")
    async def reset_test_fixtures():
        from database import get_db
        from utils.access_matrix import RUNTIME_OVERRIDES, CUSTOM_ROLE_DEFINITIONS
        db = get_db()
        # This process accepts only a disposable localhost DB. Reset between
        # modules, preserving intentional multi-step tests within each module.
        for collection in await db.list_collection_names():
            await db[collection].delete_many({})
        for collection, documents in fixture_baseline.items():
            if documents:
                from copy import deepcopy
                await db[collection].insert_many(deepcopy(documents))
        RUNTIME_OVERRIDES.clear()
        CUSTOM_ROLE_DEFINITIONS.clear()
        return {"test_only": True}

    @app.post("/__test__/reset-auth-limits")
    async def reset_test_auth_limits():
        # Test-process-only route; not registered by server.py in deployments.
        security._login_fail_cache.clear()
        security._lockout_until.clear()
        security._rate_buckets.clear()
        from database import get_db
        await get_db().auth_login_limits.delete_many({})
        return {"test_only": True}
    SESSION_EXEMPT_ENDPOINTS.update((reset_test_fixtures, reset_test_auth_limits))
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18089, log_level="warning")
