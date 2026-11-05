"""HR-maintained standard goals copied into empty, unsubmitted reviews only."""
from copy import deepcopy
from datetime import date
import uuid
from fastapi import HTTPException
from utils import performance_workflows as flow
from utils.employee_integrity import tenant_of, employee_key

CATEGORY = 'performance_kpi_template'


def query(user):
    return {'tenant_id': tenant_of(user), 'category': CATEGORY}


def view(row):
    return {'name': row['values']['name'], 'goals': deepcopy(row['values']['goals']), 'version': row['version']} if row else None


async def load(db, user):
    flow.require_hr(user)
    return view(await db.system_settings.find_one(query(user)))


def validate(body):
    if not isinstance(body, dict) or set(body) - {'name', 'goals', 'expected_version'}:
        flow.fail('Invalid KPI template fields')
    name = flow.text(body.get('name'), 'template name', 150)
    rows = body.get('goals')
    if not isinstance(rows, list) or not 3 <= len(rows) <= 5:
        flow.fail('A standard template requires three to five KPIs')
    goals = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'objective', 'metric', 'target'}:
            flow.fail('Each KPI needs an objective, measurement and target')
        goals.append({key: flow.text(row[key], key, 500) for key in ('objective', 'metric', 'target')})
    if len({row['objective'].casefold() for row in goals}) != len(goals):
        flow.fail('KPI objectives must be unique')
    return {'name': name, 'goals': goals}


async def save(db, user, body):
    flow.require_hr(user)
    values = validate(body)
    previous = await db.system_settings.find_one(query(user))
    if body.get('expected_version') != (previous or {}).get('version'):
        flow.fail('The template changed. Reload before saving.', 409)
    row = {**query(user), 'values': values, 'version': str(uuid.uuid4()),
           'updated_by': user['id'], 'updated_at': flow.now()}
    await flow.audit(db, user, 'performance.kpi_template.saved', {'id': CATEGORY},
                     before=view(previous), after=view(row))
    await db.system_settings.update_one(query(user), {'$set': row}, upsert=True)
    return view(row)


async def apply(db, user, body):
    flow.require_hr(user)
    if not isinstance(body, dict) or set(body) != {'review_ids', 'version', 'due_on'}:
        flow.fail('Select reviews, template version and a KPI due date')
    ids = body['review_ids']
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(item, str) or not item.strip() for item in ids) or len(set(ids)) != len(ids):
        flow.fail('Select one to one hundred unique reviews')
    try:
        due = date.fromisoformat(body['due_on']).isoformat()
    except (ValueError, TypeError):
        flow.fail('A valid KPI due date is required')
    template = await load(db, user)
    if not template or body['version'] != template['version']:
        flow.fail('The template changed. Reload before applying.', 409)
    result = {'applied': [], 'skipped': []}
    for reference in ids:
        try:
            row, employee = await flow.record(db, user, reference)
            await flow.employee_access(db, user, row['employee_id'], write=True)
            if employee_key(employee) == user.get('employee_id'):
                flow.fail('Another authorized manager or HR must assign your own KPIs', 403)
            if row.get('workflow_version') != 1 or row.get('cycle_type') == 'Probation':
                flow.fail('Only current mid-year and year-end reviews support this template', 409)
            if row.get('status') not in {'Draft', 'Self_Draft'} or row.get('goals_acknowledged_at'):
                flow.fail('Submitted or acknowledged reviews cannot be changed', 409)
            if row.get('section_a_kpis'):
                flow.fail('Existing KPIs are preserved; template was not applied', 409)
        except HTTPException as error:
            result['skipped'].append({'review_id': reference, 'reason': str(error.detail)})
            continue
        goals = [{**deepcopy(goal), 'id': str(uuid.uuid4()), 'due_on': due, 'progress': 0,
                  'status': 'Assigned', 'assigned_by': user['id']} for goal in template['goals']]
        await flow.save(db, user, row, {'section_a_kpis': goals,
                        'kpi_template_version': template['version']}, 'performance.goals.template_assigned')
        result['applied'].append(reference)
    return result
