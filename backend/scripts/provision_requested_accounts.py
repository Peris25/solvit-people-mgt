"""Provision Teresiah and Mary from existing employee records.

Run from the repository root with backend dependencies and MONGO_URL/DB_NAME:
  python backend/scripts/provision_requested_accounts.py --actor-id ADMIN_ID
Add --apply to create/link the reviewed accounts. The shared employee initial
password is prompted once and used for both new accounts,
never stored in source. Existing passwords and roles are preserved.
"""
import argparse
import asyncio
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import init_db, close_db
from utils.employee_accounts import provision_employee_account
from utils.employee_integrity import employee_key, normalize_email, tenant_of, tenant_query
from utils.staff_directory import visible_state

REQUESTED_ACCOUNTS = (('Teresiah', 'twangui@solvit.co.ke'), ('Mary', 'mmuriuki@solvit.co.ke'))


async def prepare(db, actor):
    employees = await db.employees.find(tenant_query(tenant_of(actor))).to_list(None)
    selected = []
    for name, email in REQUESTED_ACCOUNTS:
        matches = [e for e in employees if str(e.get('work_email') or '').strip().casefold() == email]
        if len(matches) != 1:
            raise ValueError(f'{name} ({email}): expected exactly one saved employee record; found {len(matches)}. Confirm the employee details first.')
        employee = matches[0]
        if employee.get('board_only') or not visible_state(employee):
            raise ValueError(f'{name}: employee status requires HR review.')
        normalize_email(employee.get('work_email'))
        selected.append(employee)
    return selected


async def main(args):
    from bson import ObjectId
    db = await init_db()
    try:
        actor = await db.users.find_one({'_id': ObjectId(args.actor_id)})
        if not actor or actor.get('role') not in {'it_admin', 'hr_admin'} or actor.get('is_active') is False:
            raise ValueError('Select an active IT Admin or HR Admin account as actor.')
        actor = {**actor, 'id': str(actor['_id'])}
        employees = await prepare(db, actor)
        for employee in employees:
            print(f"{employee['full_name']}: {employee['work_email']}")
        if not args.apply:
            print('Preview only. Run with --apply to provision these accounts.')
            return
        password = getpass("Existing shared employee initial password (used for both new accounts): ")
        for employee in employees:
            result = await provision_employee_account(db, employee_key(employee), password or None, actor)
            print(f"{employee['full_name']}: {'created' if result['created'] else 'linked'}")
            if result.get('warning'): print(result['warning'])
    finally:
        await close_db()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor-id', required=True)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args()))
