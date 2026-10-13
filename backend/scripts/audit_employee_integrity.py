"""Explicit read-only audit. Snapshot mode never initializes the application."""
import argparse
import asyncio
import json
import os
import sys
from bson.json_util import loads as load_snapshot
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.integrity_audit import audit_records


async def read_database():
    # Only executed by an explicit --database invocation. No dotenv, startup,
    # seeding, index creation, or write operations are invoked.
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=10000)
    try:
        db = client[os.environ["DB_NAME"]]
        employees = await db.employees.find({}, {
            "id": 1, "tenant_id": 1, "work_email": 1, "work_email_normalized": 1,
            "employee_code": 1, "line_manager_id": 1, "is_board_chair": 1, "lifecycle_state": 1,
        }).to_list(None)
        users = await db.users.find({}, {
            "id": 1, "tenant_id": 1, "email": 1, "email_normalized": 1,
            "employee_id": 1, "account_type": 1,
        }).to_list(None)
        report = audit_records(employees, users)
        report["installed_indexes"] = {}
        for collection in ("employees", "users"):
            report["installed_indexes"][collection] = [{
                "name": index["name"], "keys": dict(index["key"]),
                "unique": bool(index.get("unique")), "has_partial_filter": bool(index.get("partialFilterExpression")),
            } async for index in db[collection].list_indexes()]
        return report
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="Restricted JSON with employees/users arrays; no database access")
    source.add_argument("--database", action="store_true", help="Requires separate authorization and read-only MongoDB credentials")
    args = parser.parse_args()
    try:
        if args.snapshot:
            data = load_snapshot(args.snapshot.read_text(encoding="utf-8"))
            report = audit_records(data["employees"], data["users"])
        else:
            report = asyncio.run(read_database())
    except Exception:
        print("Audit failed. Check input, read permissions and connection configuration; details suppressed to protect identity data.", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
