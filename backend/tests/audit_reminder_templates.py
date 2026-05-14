"""Focused audit for reminder.* templates.

The Reminder Engine fires `fire_and_forget(db, rule['template_key'], extra=...)`
where `extra` is `{k: v for k, v in target.items() if scalar}`. So every
placeholder in a reminder template body must be either:
  • a standard tag (auto-supplied by triggers.py), or
  • declared in the template's own merge_tags list (since the engine forwards
    every scalar key from the rule's target dict — and the merge_tags list is
    the contract for what each rule produces).

Exits 0 if green, 1 otherwise.
"""
import os
import re
import sys
import asyncio
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

THIS_DIR = Path(__file__).resolve().parent
load_dotenv(THIS_DIR.parent / ".env")

STANDARD_TAGS = {
    "employee_name", "employee_first_name", "employee_email", "employee_role",
    "employee_department", "role_title", "department", "start_date",
    "line_manager_name", "line_manager_email", "manager_name", "manager_email",
    "hr_name", "company_name", "platform_link", "login_url", "action_date",
    "due_date", "current_year", "today",
}
PH = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    failures = []
    ok = 0
    async for t in db.email_templates.find({"tenant_id": "solvit",
                                            "key": {"$regex": "^reminder\\."}}):
        body = (t.get("body") or "") + " " + (t.get("subject") or "")
        ph = set(PH.findall(body))
        supplied = STANDARD_TAGS | set(t.get("merge_tags") or [])
        missing = ph - supplied
        if missing:
            failures.append((t["key"], sorted(missing)))
        else:
            ok += 1
    print(f"reminder templates OK: {ok}")
    if failures:
        print(f"FAIL ({len(failures)}):")
        for k, m in failures:
            print(f"  {k}: missing {m}")
        sys.exit(1)
    print("All reminder templates render with documented merge_tags.")


if __name__ == "__main__":
    asyncio.run(main())
