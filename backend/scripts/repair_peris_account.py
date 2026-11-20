"""Explicit operator repair for the Peris duplicate; never runs at app startup.

Uses MONGO_URL and DB_NAME already supplied to the operator process. Default is
read-only planning. --apply requires a reviewed plan fingerprint and a MongoDB
transaction. Credentials, passwords, bank details and history are never printed.
Applied on 19 November 2026 with a reviewed fingerprint and verified saved state.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from bson import ObjectId, json_util
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import init_db, close_db
from utils.employee_integrity import (
    employee_key, email_matches, integrity_write, tenant_of, tenant_query,
    validate_manager, resolve_user_employee,
)

OLD_EMAIL = 'support@solvit.co.ke'
NEW_EMAIL = 'podhiambo@solvit.co.ke'
MARTIN_EMAIL = 'mkiarie@solvit.co.ke'
MERCY_EMAIL = 'mparkire@solvit.co.ke'
REFERENCE_FIELDS = {
    'employee_id', 'employee_ids', 'line_manager_id', 'manager_id',
    'reviewer_employee_id', 'reviewer_ids', 'recipient_id', 'owner_employee_id',
    'handover_contact_id', 'nominated_employee_id', 'nominator_employee_id',
    'mentor_employee_id', 'subject_employee_id', 'assignee_employee_id',
    'reports_to', 'approver_employee_id', 'staff_id',
}
# Audit evidence and recovery snapshots retain their original identifiers.
HISTORICAL = {
    'audit_logs', 'removed_employee_records', 'integrity_locks',
    'employee_merge_recovery',
}


def require(condition, message):
    if not condition:
        raise HTTPException(409, message)


async def unique_employee(db, email, tenant):
    rows = await email_matches(db.employees, 'work_email', email, tenant)
    require(len(rows) == 1, f'Expected exactly one employee for {email}.')
    return rows[0]


def references(value, aliases, canonical, path=()):
    """Rewrite only explicit employee links; unknown exact references block apply."""
    if isinstance(value, dict):
        return {key: references(item, aliases, canonical, (*path, key))
                for key, item in value.items()}
    if isinstance(value, list):
        return [references(item, aliases, canonical, path) for item in value]
    if isinstance(value, (str, ObjectId)) and str(value) in aliases:
        field = path[-1] if path else ''
        require(field in REFERENCE_FIELDS,
                'Unmapped employee reference requires operator review: ' + '.'.join(path))
        return canonical
    return value


async def prepare(db, actor):
    tenant = tenant_of(actor)
    retained = await unique_employee(db, OLD_EMAIL, tenant)
    duplicate = await unique_employee(db, NEW_EMAIL, tenant)
    require(retained['_id'] != duplicate['_id'], 'The records are already consolidated.')
    require(all('peris' in str(row.get('full_name', '')).casefold()
                for row in (retained, duplicate)), 'Employee names need review.')
    require(retained.get('role_title') == 'IT Lead', 'Retained title must be IT Lead.')
    require(not retained.get('board_only') and not duplicate.get('board_only'),
            'Protected employee records cannot be repaired with this script.')
    canonical = employee_key(retained)
    aliases = {employee_key(duplicate), str(duplicate['_id'])}
    require(canonical not in aliases, 'Employee identifiers collide.')
    accounts = await email_matches(db.users, 'email', OLD_EMAIL, tenant)
    require(len(accounts) == 1, 'Expected exactly one existing support login.')
    account = accounts[0]
    require(account['_id'] != actor['_id'], 'Use a different administrator for this repair.')
    require(account.get('role') == 'it_admin', 'Existing account role requires review.')
    require(account.get('is_active') is not False, 'Existing account activation requires review.')
    resolved = await resolve_user_employee(db, account)
    require(resolved and resolved['_id'] == retained['_id'],
            'Existing support login must resolve to the retained employee.')
    require(not await email_matches(db.users, 'email', NEW_EMAIL),
            'The requested login email already belongs to an account.')
    linked = await db.users.find({'$and': [tenant_query(tenant), {'employee_id': {'$in': list(aliases | {canonical, str(retained['_id'])})}}]}).to_list(None)
    require({row['_id'] for row in linked} <= {account['_id']},
            'Additional login accounts require an explicit account reconciliation.')
    martin = await unique_employee(db, MARTIN_EMAIL, tenant)
    mercy = await unique_employee(db, MERCY_EMAIL, tenant)
    require('martin' in martin.get('full_name', '').casefold(), 'Martin identity needs review.')
    require('mercy' in mercy.get('full_name', '').casefold(), 'Mercy identity needs review.')
    manager = await validate_manager(db, employee_key(martin), retained, tenant)
    await validate_manager(db, canonical, mercy, tenant)

    # A duplicate review or balance cannot be combined by adding numeric values.
    for collection, keys in (
        ('performance_reviews', ('cycle_type', 'cycle_year')),
        ('leave_balances', ('year',)),
        ('performance_kpi_assignments', ('scope',)),
    ):
        rows = await db[collection].find({'$and': [tenant_query(tenant), {'employee_id': {'$in': list(aliases | {canonical, str(retained['_id'])})}}]}).to_list(None)
        seen = set()
        for row in rows:
            identity = tuple(str(row.get(key)) for key in keys)
            require(identity not in seen, f'Overlapping {collection} history requires manual reconciliation.')
            seen.add(identity)

    changes = []
    for name in sorted(await db.list_collection_names()):
        if name in HISTORICAL or name.startswith('system.') or 'audit' in name:
            continue
        async for original in db[name].find(tenant_query(tenant)):
            if name == 'employees' and original['_id'] == duplicate['_id']:
                continue
            document = deepcopy(original)
            # A document's own identity must never be changed by link repair.
            content = {key: value for key, value in document.items() if key not in {'_id', 'id'}}
            rewritten = references(content, aliases, canonical)
            document.update(rewritten)
            if name == 'employees' and original['_id'] == retained['_id']:
                document.update(work_email=NEW_EMAIL, work_email_normalized=NEW_EMAIL,
                                line_manager_id=manager)
            if name == 'employees' and original['_id'] == mercy['_id']:
                document['line_manager_id'] = canonical
            if name == 'users' and original['_id'] == account['_id']:
                document.update(email=NEW_EMAIL, email_normalized=NEW_EMAIL,
                                employee_id=canonical)
            if document != original:
                changes.append((name, original, document))
    return retained, duplicate, account, changes


def fingerprint(plan):
    retained, duplicate, account, changes = plan
    payload = [retained, duplicate, account, changes]
    return hashlib.sha256(json_util.dumps(payload, sort_keys=True).encode()).hexdigest()


async def main(args):
    db = await init_db()
    try:
        require(ObjectId.is_valid(args.actor_id), 'Provide an administrator account ID.')
        actor = await db.users.find_one({'_id': ObjectId(args.actor_id)})
        require(actor and actor.get('role') in {'hr_admin', 'it_admin'} and actor.get('is_active') is not False,
                'An active HR Admin or IT Admin is required.')
        actor = {**actor, 'id': str(actor['_id'])}
        plan = await prepare(db, actor)
        digest = fingerprint(plan)
        counts = {}
        for name, _, _ in plan[3]: counts[name] = counts.get(name, 0) + 1
        print(json.dumps({'mode': 'preview', 'plan': digest, 'affected_collections': counts,
                          'retained_login_role': plan[2]['role'], 'password_preserved': True}))
        if not args.apply: return
        require(args.confirm_plan == digest, 'Review the preview and supply its exact fingerprint.')
        async with integrity_write(db):
            plan = await prepare(db, actor)
            require(fingerprint(plan) == digest, 'Records changed since preview; review a fresh plan.')
            retained, duplicate, account, changes = plan
            async with await db.client.start_session() as session:
                async with session.start_transaction():
                    now = datetime.now(timezone.utc).isoformat()
                    # Full originals remain restricted recovery copies, never public API data.
                    for name, original, _ in changes:
                        await db.removed_employee_records.insert_one({
                            'tenant_id': tenant_of(actor), 'repair_plan': digest,
                            'source_collection': name, 'original': original,
                            'actor_id': actor['id'], 'created_at': now,
                        }, session=session)
                    await db.removed_employee_records.insert_one({
                        'tenant_id': tenant_of(actor), 'repair_plan': digest,
                        'source_collection': 'employees', 'original': duplicate,
                        'actor_id': actor['id'], 'created_at': now,
                    }, session=session)
                    for name, original, replacement in changes:
                        current = await db[name].find_one({'_id': original['_id']}, session=session)
                        require(current == original, 'A linked record changed; transaction cancelled.')
                        if name == 'users' and original['_id'] == account['_id']:
                            replacement['sessions_invalidated_at'] = now
                        await db[name].replace_one({'_id': original['_id']}, replacement, session=session)
                    current = await db.employees.find_one({'_id': duplicate['_id']}, session=session)
                    require(current == duplicate, 'Duplicate changed; transaction cancelled.')
                    await db.employees.delete_one({'_id': duplicate['_id']}, session=session)
                    await db.audit_logs.insert_one({
                        'tenant_id': tenant_of(actor), 'event': 'account.peris.duplicate_repaired',
                        'actor_id': actor['id'], 'entity_id': employee_key(retained),
                        'metadata': {'repair_plan': digest, 'affected_collections': counts},
                        'timestamp': now,
                    }, session=session)
        print('Repair committed. Existing Peris sessions must sign in with the corrected email.')
    finally:
        await close_db()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor-id', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-plan')
    asyncio.run(main(parser.parse_args()))
