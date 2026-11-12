"""HR role KPI drafts and approval, independent of legacy assessment scoring."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import uuid
from bson import ObjectId
from utils import performance_workflows as flow
from utils.employee_integrity import tenant_of, tenant_query

PREFIX = 'performance_role_kpi:'
SCOPES = {'Annual', 'Probation', 'Board', 'Reference', 'Unconfirmed'}
DIRECTIONS = {'Higher', 'Lower', 'Binary', 'Rated', 'Unconfirmed'}
ROW_FIELDS = {'id', 'objective', 'metric', 'target', 'target_value', 'weight', 'direction', 'unit', 'data_source', 'owner', 'group', 'notes'}
ENTRY_FIELDS = {'role_id', 'name', 'scope', 'goals', 'group_weights', 'notes', 'approval_reference', 'source_reference'}


@lru_cache(maxsize=1)
def catalogue():
    rows = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'role_kpi_reference.json').read_text(encoding='utf-8'))
    for entry in rows:
        for goal in entry['goals']:
            match = re.search(r'(?<![\w])\d+(?:\.\d+)?', goal['target'])
            goal['target_value'] = float(match.group()) if match and goal['direction'] in {'Higher', 'Lower'} else None
    return rows


def role_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', value):
        flow.fail('Invalid role identifier')
    return value


def identity(user, key):
    return ObjectId(hashlib.sha256(f'role-kpi:{tenant_of(user)}:{key}'.encode()).hexdigest()[:24])


def text(value, label, maximum=1000):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        flow.fail(f'Invalid {label}')
    return value.strip()


def number(value, label, maximum=1000000000):
    if value is None or value == '': return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        flow.fail(f'Invalid {label}')
    try: result = Decimal(str(value))
    except InvalidOperation: flow.fail(f'Invalid {label}')
    if not result.is_finite() or result < 0 or result > maximum: flow.fail(f'Invalid {label}')
    return float(result)


def validate(entry):
    if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS: flow.fail('Invalid role KPI fields')
    values = {key: text(entry[key], key, 250 if key == 'name' else 1500) for key in ('name', 'notes', 'approval_reference', 'source_reference')}
    values['role_id'] = role_id(entry['role_id'])
    if not values['name']: flow.fail('Enter the role name')
    if not isinstance(entry['scope'],str) or entry['scope'] not in SCOPES: flow.fail('Choose a valid review scope')
    values['scope'] = entry['scope']
    rows = entry['goals']
    if not isinstance(rows, list) or len(rows) > flow.MAX_KPIS: flow.fail('Use up to 100 KPIs per role')
    values['goals'] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS: flow.fail('Invalid KPI fields')
        goal = {key: text(row[key], key, 1500 if key in {'notes','metric','target'} else 500) for key in ROW_FIELDS - {'weight','target_value','direction'}}
        if not goal['id'] or not isinstance(row['direction'],str) or row['direction'] not in DIRECTIONS: flow.fail('Invalid KPI identity or scoring method')
        goal.update(direction=row['direction'], weight=number(row['weight'],'KPI weight',100), target_value=number(row['target_value'],'numeric target'))
        values['goals'].append(goal)
    if len({goal['id'] for goal in values['goals']}) != len(rows): flow.fail('KPI identifiers must be unique')
    groups = entry['group_weights']
    if not isinstance(groups, dict) or len(groups) > 20: flow.fail('Invalid KPI groups')
    values['group_weights'] = {text(key,'group name',100): number(value,'group weight',100) for key,value in groups.items()}
    if any(not key for key in values['group_weights']): flow.fail('Enter a group name')
    return values


def issues(values):
    problems = []
    rows = values['goals']
    if not rows: problems.append('Add at least one KPI.')
    if values['scope'] not in {'Annual','Probation'}: problems.append('Confirm an Annual or Probation scope before publishing. Board and recruitment references stay in draft.')
    seen = set()
    for i, goal in enumerate(rows, 1):
        missing = [label for key,label in [('objective','objective'),('metric','measurement'),('target','target'),('unit','unit'),('data_source','data source'),('owner','owner')] if not goal[key]]
        if missing: problems.append(f'KPI {i}: complete ' + ', '.join(missing) + '.')
        if goal['objective'].casefold() in seen: problems.append(f'KPI {i}: use a unique objective.')
        seen.add(goal['objective'].casefold())
        if goal['weight'] is None or goal['weight'] <= 0: problems.append(f'KPI {i}: enter a positive weight.')
        if goal['direction'] == 'Unconfirmed': problems.append(f'KPI {i}: confirm the scoring method.')
        if goal['direction'] in {'Higher','Lower'} and (goal['target_value'] is None or goal['target_value'] <= 0): problems.append(f'KPI {i}: enter a positive numeric target. Zero-target rules need confirmation.')
    groups = values['group_weights']
    if groups:
        if any(goal['group'] not in groups for goal in rows): problems.append('Assign every KPI to a listed group.')
        if any(weight is None or weight <= 0 for weight in groups.values()) or sum(Decimal(str(w or 0)) for w in groups.values()) != 100: problems.append('Group weights must total 100%.')
        for group in groups:
            if sum(Decimal(str(g['weight'] or 0)) for g in rows if g['group'] == group) != 100: problems.append(f'{group} KPI weights must total 100%.')
    elif any(goal['group'] for goal in rows): problems.append('Define the group weights or remove the KPI group names.')
    elif sum(Decimal(str(g['weight'] or 0)) for g in rows) != 100: problems.append('KPI weights must total 100%.')
    if not values['approval_reference']: problems.append('Enter the MD/line-manager approval reference for these targets and weights.')
    return problems


def view(row):
    entry = deepcopy(row['values'])
    return {**entry, 'status':row['status'], 'version':row['version'], 'updated_at':row['updated_at'],
            'issues':issues(entry), 'has_published_version':bool(row.get('published_values'))}


async def listing(db, user):
    flow.require_hr(user)
    merged = {}
    for entry in deepcopy(catalogue()):
        entry.update(version=None, updated_at=None, issues=issues(entry), has_published_version=False)
        merged[entry['role_id']] = entry
    rows = await db.system_settings.find({'$and':[tenant_query(tenant_of(user)), {'category':'performance_role_kpi_library'}]}).to_list(None)
    for row in rows: merged[row['values']['role_id']] = view(row)
    return {'roles':sorted(merged.values(), key=lambda entry:entry['name'].casefold())}


async def save(db, user, key, body):
    flow.require_hr(user)
    role_id(key)
    if not isinstance(body, dict) or set(body) != {'entry','action','expected_version','reason'}: flow.fail('Invalid save request')
    values = validate(body['entry'])
    if values['role_id'] != key: flow.fail('The selected role does not match the saved role')
    if not isinstance(body['action'],str) or body['action'] not in {'draft','publish'}: flow.fail('Choose Save draft or Publish')
    reason = text(body['reason'],'change reason',1500)
    query = {'_id':identity(user,key), 'tenant_id':tenant_of(user)}
    previous = await db.system_settings.find_one(query)
    if body['expected_version'] != (previous or {}).get('version'): flow.fail('Another HR user changed this role. Reload before saving; your typed changes have not been discarded.',409)
    if body['action'] == 'publish':
        pending = issues(values)
        if pending: flow.fail('Cannot publish: ' + ' '.join(pending))
    if previous and previous.get('published_values') and values != previous['values'] and len(reason) < 10: flow.fail('Enter a change reason (at least 10 characters) when editing an approved role')
    row = {**query, 'category':'performance_role_kpi_library', 'values':values, 'status':'Published' if body['action']=='publish' else 'Draft',
           'version':str(uuid.uuid4()), 'updated_at':flow.now(), 'updated_by':user['id'],
           'published_values':deepcopy(values) if body['action']=='publish' else deepcopy((previous or {}).get('published_values'))}
    row['published_version'] = row['version'] if body['action'] == 'publish' else (previous or {}).get('published_version') or ((previous or {}).get('version') if (previous or {}).get('published_values') else None)
    await flow.audit(db,user,'performance.role_kpi.'+body['action'],{'id':key},before=view(previous) if previous else None,after=view(row),reason=reason)
    await db.system_settings.update_one(query,{'$set':{key:value for key,value in row.items() if key != '_id'}},upsert=True)
    if body['action'] == 'publish':
        from utils.performance_v3 import auto_assignment
        for employee in await db.employees.find(tenant_query(tenant_of(user))).to_list(None):
            await auto_assignment(db, employee, user)
    return view(row)
