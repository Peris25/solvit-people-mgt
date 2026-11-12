"""V3 performance process; existing reviews remain on their original workflow."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from bson import ObjectId
from utils import performance_workflows as flow, performance_v3_scoring as calc, role_kpi_library as library
from utils.employee_integrity import tenant_of, tenant_query, find_employee, employee_key, is_direct_report, user_employee_aliases, validate_manager
from utils.employee_access import find_linked_record, reference_ids, personal_grant
from utils.staff_views import token
from utils.profile_self_service import self_employee
from utils.runtime_controls import outbound_email_enabled

ASSIGNMENT = 'performance_employee_kpis_v3'
MANAGER_MEETING_PEER_ACCESS = True


def instant(): return datetime.now(timezone.utc)
def today(): return instant().astimezone(timezone(timedelta(hours=3))).date()
def key(*parts): return ObjectId(hashlib.sha256(':'.join(map(str, parts)).encode()).hexdigest()[:24])
def scoped(user, extra=None): return {'$and': [tenant_query(tenant_of(user)), extra or {}]}
def enabled(employee): return token(employee.get('lifecycle_state') or employee.get('status')) in {'active', 'probation', 'onboarding', 'onleave', 'pip'}
def md(employee): return bool(employee.get('is_md')) or token(employee.get('role_title')) in {'managingdirector', 'md', 'ceo', 'chiefexecutiveofficer'}
def ed(employee): return bool(employee.get('is_ed')) or token(employee.get('role_title')) == 'executivedirector'
def fte(employee): return not flow.restricted(employee.get('board_only')) and token(employee.get('employment_type')) in {'', 'fulltime', 'fte'}
def clean(row): return {k: deepcopy(v) for k, v in row.items() if k not in {'_id', 'tenant_id'}}


def fields(body, allowed):
    if not isinstance(body, dict) or set(body) - set(allowed): flow.fail('Unknown or invalid fields')


async def assignment(db, employee):
    return await db.system_settings.find_one({'_id': key(ASSIGNMENT, tenant_of(employee), employee_key(employee)), 'tenant_id': tenant_of(employee)})


async def auto_assignment(db, employee, actor):
    """Only exact, unambiguous approved-role matches; never overwrite targets."""
    if not enabled(employee) or not fte(employee) or md(employee) or await assignment(db, employee): return
    rows = await db.system_settings.find({'$and': [tenant_query(tenant_of(employee)), {'category': 'performance_role_kpi_library'}]}).to_list(None)
    matches = [r for r in rows if r.get('published_values') and token(r['published_values']['name']) == token(employee.get('role_title'))]
    if len(matches) != 1: return
    values = matches[0]['published_values']
    if values.get('scope') not in {'Annual', 'Probation'} or library.issues(values): return
    return await _assign(db, actor, employee, values, matches[0].get('published_version') or matches[0]['version'], 'Approved role assigned at account setup', None, False)


async def _assign(db, user, employee, values, source_version, reason, expected, role_change):
    previous = await assignment(db, employee)
    if expected != (previous or {}).get('version'): flow.fail('Employee KPIs changed. Reload before saving.', 409)
    open_reviews = await db.performance_reviews.find(scoped(user, {'employee_id': employee_key(employee), 'workflow_version': 3, 'status': {'$nin': ['Completed', 'Archived', 'Cancelled']}})).to_list(None)
    if open_reviews and not role_change: flow.fail('KPIs are locked during an open cycle. An approved role change is required.', 409)
    if open_reviews and any(r.get('status') != 'Self_Draft' or r.get('self_assessment') for r in open_reviews): flow.fail('Submitted reviews cannot be rewritten for a role change.', 409)
    row = {'_id': key(ASSIGNMENT, tenant_of(employee), employee_key(employee)), 'tenant_id': tenant_of(employee), 'category': ASSIGNMENT,
           'employee_id': employee_key(employee), 'values': deepcopy(values), 'source_version': source_version, 'version': str(uuid.uuid4()), 'updated_at': flow.now()}
    await flow.audit(db, user, 'performance.v3.kpis.assigned', {'id': employee_key(employee)}, before=clean(previous) if previous else None, after=clean(row), reason=reason, role_change=role_change)
    await db.system_settings.update_one({'_id': row['_id'], 'tenant_id': row['tenant_id']}, {'$set': {k: v for k, v in row.items() if k != '_id'}}, upsert=True)
    for review in open_reviews:
        await save(db, user, review, {'section_a_kpis': deepcopy(values['goals']), 'group_weights': deepcopy(values['group_weights']), 'kpi_assignment_version': row['version']}, 'role_change')
    return clean(row)


async def assign(db, user, reference, body):
    flow.require_hr(user)
    fields(body, {'role_id', 'expected_version', 'reason', 'individual', 'role_change'})
    employee = await flow.employee_access(db, user, reference, True)
    if md(employee) or not enabled(employee) or not fte(employee): flow.fail('Employee is not eligible for a platform review', 409)
    source = await db.system_settings.find_one({'_id': library.identity(user, library.role_id(body.get('role_id'))), 'tenant_id': tenant_of(user)})
    if not source or not source.get('published_values'): flow.fail('Publish and approve the role KPIs first', 409)
    values = deepcopy(source['published_values'])
    if values['scope'] not in {'Annual', 'Probation'}: flow.fail('Board/recruitment references cannot be assigned as employee performance KPIs')
    reason = flow.text(body.get('reason'), 'assignment/change reason', 1500)
    if len(reason) < 10: flow.fail('Enter a clear reason of at least 10 characters')
    if 'individual' in body:
        if user.get('employee_id') in reference_ids(employee): flow.fail('Another HR approver must change your individual targets', 403)
        values = library.validate(body['individual'])
        if values.get('role_id') != source['published_values']['role_id'] or values.get('scope') != source['published_values']['scope']:
            flow.fail('Individual overrides must retain the approved role and review scope')
        if library.issues(values): flow.fail('Individual KPIs need complete approved targets, weights and an approval reference')
    if body.get('role_change') not in (None, False, True): flow.fail('Invalid role-change confirmation')
    return await _assign(db, user, employee, values, source.get('published_version') or source['version'], reason, body.get('expected_version'), body.get('role_change') is True)


async def setup(db, user):
    flow.require_hr(user)
    employees = []
    for employee in await db.employees.find(tenant_query(tenant_of(user))).to_list(None):
        if not enabled(employee) or not fte(employee) or md(employee): continue
        await flow.employee_access(db, user, employee_key(employee))
        saved = await assignment(db, employee)
        employees.append({'id': employee_key(employee), 'name': employee.get('full_name'), 'role': employee.get('role_title'), 'department': employee.get('department'), 'assignment': clean(saved) if saved else None})
    return {'employees': employees, 'roles': (await library.listing(db, user))['roles']}


async def my_kpis(db, user):
    personal_grant(user, 'M05')
    employee = await self_employee(db, user)
    if not enabled(employee): flow.fail('Employee is not eligible to view active role KPIs', 403)
    row = await assignment(db, employee)
    if not row: return None
    # Do not expose HR approval notes, actor IDs or internal settings metadata.
    values = row['values']
    return {'name': values['name'], 'scope': values['scope'], 'goals': deepcopy(values['goals']),
            'group_weights': deepcopy(values.get('group_weights', {})), 'updated_at': row.get('updated_at')}


async def cycle(db, user, reference): return await find_linked_record(db.performance_cycles, reference, user)


async def create_cycle(db, user, body):
    flow.require_hr(user)
    fields(body, {'cycle_type', 'cycle_year', 'starts_on', 'approval_reference', 'alignment_confirmed'})
    if body.get('cycle_type') not in {'Mid_Year', 'Year_End'}: flow.fail('Choose Mid-Year or Year-End')
    year = body.get('cycle_year')
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100: flow.fail('Choose a valid year')
    try: start = date.fromisoformat(body['starts_on'])
    except (KeyError, TypeError, ValueError): flow.fail('Choose a valid cycle start')
    if start.year != year or start < today(): flow.fail('Choose a start in the cycle year, not in the past')
    reference = flow.text(body.get('approval_reference'), 'MD/HR 50/30/20 approval reference', 500)
    if body.get('alignment_confirmed') is not True: flow.fail('HR must confirm the displayed Alignment Survey questions')
    for existing in await db.performance_cycles.find(tenant_query(tenant_of(user))).to_list(None):
        if existing.get('status') in {'Archived', 'Cancelled'}: continue
        if existing.get('cycle_type') == body['cycle_type'] and existing.get('cycle_year') == year: flow.fail('A cycle exists for this period. Archive only an unused cycle first.', 409)
        if existing.get('starts_on', 'z') <= (start + timedelta(days=27)).isoformat() and existing.get('ends_on', '') >= start.isoformat(): flow.fail('Review cycles cannot overlap', 409)
    row = {'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user), 'workflow_version': 3, 'cycle_type': body['cycle_type'], 'cycle_year': year,
           'starts_on': start.isoformat(), 'self_due_on': (start + timedelta(days=6)).isoformat(), 'peer_due_on': (start + timedelta(days=6)).isoformat(),
           'manager_due_on': (start + timedelta(days=13)).isoformat(), 'ends_on': (start + timedelta(days=27)).isoformat(), 'status': 'Configured',
           'scoring_policy': {'weights': [50, 30, 20], 'source': 'performance_v3', 'section_c': 'Company NPS and CSAT', 'approval_reference': reference, 'approved_by': user['id']}, 'created_at': flow.now(), 'created_by': user['id']}
    await flow.audit(db, user, 'performance.v3.cycle.created', row, dates={k: v for k, v in row.items() if k.endswith('_on')})
    await db.performance_cycles.insert_one(row)
    return clean(row)


async def archive(db, user, reference, body):
    flow.require_hr(user); fields(body, {'reason'})
    row = await cycle(db, user, reference); reason = flow.text(body.get('reason'), 'archive reason', 1500)
    if len(reason) < 10: flow.fail('Enter a clear archive reason')
    if row.get('status') == 'Archived': return clean(row)
    reviews = await db.performance_reviews.find(scoped(user, {'cycle_id': row['id']})).to_list(None)
    if any(r.get('status') != 'Draft' or r.get('self_assessment') or r.get('released_at') for r in reviews): flow.fail('Only unused cycles with unsubmitted draft reviews can be archived', 409)
    await flow.audit(db, user, 'performance.v3.cycle.archived', row, reason=reason)
    for review in reviews: await db.performance_reviews.update_one({'_id': review['_id']}, {'$set': {'status': 'Archived', 'archive_reason': reason}})
    await db.performance_cycles.update_one({'_id': row['_id']}, {'$set': {'status': 'Archived', 'archive_reason': reason}})
    return {'status': 'Archived'}


async def notice(db, row, event, kind, recipient, title):
    identity = key('v3-notice', tenant_of(row), row['id'], event, kind, recipient)
    await db.notifications.update_one({'_id': identity}, {'$setOnInsert': {'id': str(identity), 'tenant_id': tenant_of(row), 'category': 'Performance',
        'recipient_type': kind, 'recipient_id': recipient, 'title': title, 'message': 'Open the authorized performance item for details.',
        'data': {**({'performance_peer_task_id': row['peer_task_id']} if row.get('peer_task_id') else
                   {'performance_alignment_cycle_id': row['cycle_id']} if row.get('alignment') else
                   {'performance_review_id': row.get('review_id') or row['id']}),
                 'employee_id': row.get('employee_id'), 'cycle_id': row.get('cycle_id'), 'performance_v3': True},
        'is_read': False, 'created_at': flow.now(), 'v3_email_pending': outbound_email_enabled()}}, upsert=True)


async def hr_notice(db, row, event, title):
    subject = await find_employee(db, row.get('employee_id'), tenant_of(row)) if row.get('employee_id') else None
    needs_gm = bool(subject and await db.users.find_one(scoped(row, {'employee_id': {'$in': reference_ids(subject)},
        'role': {'$in': ['hr_admin', 'hr_manager']}, 'is_active': {'$ne': False}})))
    for role in ('hr_admin', 'hr_manager', 'general_manager'):
        identity = key('v3-hr', tenant_of(row), row['id'], event, role)
        await db.notifications.update_one({'_id': identity}, {'$setOnInsert': {'id': str(identity), 'tenant_id': tenant_of(row), 'category': 'Performance',
            'recipient_role': role, 'title': title, 'message': 'A performance workflow requires HR attention.',
            'data': {'performance_review_id': row.get('review_id') or row['id'], 'employee_id': row.get('employee_id'), 'cycle_id': row.get('cycle_id'), 'performance_v3': True},
            'is_read': False, 'created_at': flow.now(), 'v3_email_pending': (role != 'general_manager' or needs_gm) and outbound_email_enabled()}}, upsert=True)


async def save(db, user, row, update, event):
    await flow.audit(db, user, 'performance.v3.' + event, row, employee_id=row.get('employee_id'), changed_fields=sorted(update))
    result = await db.performance_reviews.update_one({'_id': row['_id'], 'version': row.get('version')}, {'$set': {**update, 'version': str(uuid.uuid4()), 'updated_at': flow.now()}})
    if not result.modified_count: flow.fail('This review changed. Reload before saving.', 409)
    return await db.performance_reviews.find_one({'_id': row['_id']})


async def peer_task(db, user, review, reviewer, deadline):
    if employee_key(reviewer) == review['employee_id'] or ed(reviewer) or not enabled(reviewer) or not fte(reviewer): return
    identity = key('v3-peer', tenant_of(user), review['id'], employee_key(reviewer))
    if await db.performance_peer_tasks.find_one({'_id': identity}): return
    await db.performance_peer_tasks.insert_one({'_id': identity, 'id': str(identity), 'tenant_id': tenant_of(user), 'cycle_id': review['cycle_id'],
        'review_id': review['id'], 'reviewer_employee_id': employee_key(reviewer), 'employee_id': review['employee_id'], 'status': 'Assigned', 'due_on': deadline})
    await notice(db, {**review, 'peer_task_id': str(identity)}, 'peer-assigned:' + str(identity), 'employee', employee_key(reviewer), 'Complete an anonymous 360 review')


async def open_cycle(db, user, reference, employee_ids=None):
    flow.require_hr(user); window = await cycle(db, user, reference)
    if window.get('workflow_version') != 3: flow.fail('Use a V3 cycle for the revised workflow', 409)
    if window['status'] == 'Open' and employee_ids is None: return clean(window)
    if window['status'] not in {'Configured', 'Opening', 'Open'}: flow.fail('This cycle cannot be opened', 409)
    if today() > date.fromisoformat(window['self_due_on']): flow.fail('Week 1 has ended; configure valid cycle dates', 409)
    employees = [e for e in await db.employees.find(tenant_query(tenant_of(user))).to_list(None) if enabled(e) and fte(e) and not md(e)]
    candidates = employees
    if employee_ids is not None:
        if not isinstance(employee_ids, list) or not employee_ids or len(employee_ids) > 200 or any(not isinstance(i, str) for i in employee_ids): flow.fail('Select eligible employees')
        if set(employee_ids) - {employee_key(e) for e in employees}: flow.fail('One or more employees are not eligible', 409)
        candidates = [e for e in employees if employee_key(e) in employee_ids]
    ready, missing = [], []
    for employee in candidates:
        saved = await assignment(db, employee)
        manager = await find_employee(db, employee.get('line_manager_id'), tenant_of(user))
        try: await validate_manager(db, employee.get('line_manager_id'), employee, tenant_of(user))
        except flow.HTTPException:
            missing.append(employee.get('full_name') or employee_key(employee)); continue
        if not saved or saved['values']['scope'] != 'Annual' or library.issues(saved['values']) or not manager or not enabled(manager) or employee_key(manager) == employee_key(employee):
            missing.append(employee.get('full_name') or employee_key(employee)); continue
        existing = await db.performance_reviews.find(scoped(user, {'employee_id': {'$in': reference_ids(employee)}, 'cycle_type': window['cycle_type'], 'cycle_year': window['cycle_year'], 'status': {'$nin': ['Archived', 'Cancelled']}})).to_list(None)
        if any(r.get('cycle_id') != window['id'] for r in existing): flow.fail('A live review already exists for ' + str(employee.get('full_name')) + '. Archive only unused drafts first.', 409)
        ready.append((employee, saved, manager))
    if missing: flow.fail('Assign approved Annual KPIs and valid managers first: ' + ', '.join(missing), 409)
    if not ready: flow.fail('No eligible employee reviews are ready', 409)
    from routes.surveys import FTE_ALIGNMENT_QUESTIONS
    survey_id = str(key('v3-alignment', tenant_of(user), window['id']))
    await flow.audit(db, user, 'performance.v3.cycle.opened', window, employee_count=len(ready))
    await db.performance_cycles.update_one({'_id': window['_id']}, {'$set': {'status': 'Opening'}})
    for employee, saved, manager in ready:
        identity = key('v3-review', tenant_of(user), window['id'], employee_key(employee))
        row = await db.performance_reviews.find_one({'_id': identity})
        if not row:
            row = {'_id': identity, 'id': str(identity), 'tenant_id': tenant_of(user), 'cycle_id': window['id'], 'cycle_type': window['cycle_type'], 'cycle_year': window['cycle_year'],
                'workflow_version': 3, 'status': 'Self_Draft', 'employee_id': employee_key(employee), 'line_manager_id': employee_key(manager),
                'section_a_kpis': deepcopy(saved['values']['goals']), 'group_weights': deepcopy(saved['values']['group_weights']), 'kpi_assignment_version': saved['version'],
                'starts_on': window['starts_on'], 'self_due_on': window['self_due_on'], 'peer_due_on': window['peer_due_on'], 'manager_due_on': window['manager_due_on'], 'review_due_on': window['ends_on'],
                'scoring_policy': deepcopy(window['scoring_policy']), 'version': str(uuid.uuid4()), 'created_at': flow.now()}
            await db.performance_reviews.insert_one(row)
        for colleague in employees:
            if colleague.get('department') and colleague.get('department') == employee.get('department'): await peer_task(db, user, row, colleague, window['peer_due_on'])
        if md(manager): await peer_task(db, user, row, manager, window['peer_due_on'])
        await notice(db, row, 'opened', 'employee', employee_key(employee), 'Complete your performance self-review')
        await notice(db, row, 'manager-week2', 'employee', employee_key(manager), 'Your team performance cycle is open')
        await notice(db, {**row, 'alignment': True}, 'alignment:' + employee_key(employee), 'employee', employee_key(employee), 'Complete the Alignment Survey')
    await db.survey_windows.update_one({'_id': ObjectId(survey_id)}, {'$setOnInsert': {'id': survey_id, 'tenant_id': tenant_of(user), 'survey_type': 'alignment_fte',
        'title': f"{window['cycle_type']} {window['cycle_year']} Alignment Survey", 'performance_workflow_version': 3, 'cycle_id': window['id'],
        'open_date': window['starts_on'], 'close_date': window['self_due_on'], 'status': 'Open', 'questions': deepcopy(FTE_ALIGNMENT_QUESTIONS), 'created_at': flow.now()}}, upsert=True)
    await db.performance_cycles.update_one({'_id': window['_id']}, {'$set': {'status': 'Open', 'alignment_window_id': survey_id}})
    return clean(await db.performance_cycles.find_one({'_id': window['_id']}))


def projection(row, user, employee):
    own = user.get('employee_id') in reference_ids(employee)
    hr = user.get('role') in flow.HR and not own
    manager = not own and is_direct_report(employee, user) and row.get('line_manager_id') in user_employee_aliases(user)
    result = {k: deepcopy(row[k]) for k in ('id', 'employee_id', 'cycle_id', 'cycle_type', 'cycle_year', 'workflow_version', 'status', 'version', 'starts_on', 'self_due_on', 'peer_due_on', 'manager_due_on', 'review_due_on', 'section_a_kpis', 'group_weights', 'self_assessment', 'review_meeting', 'meeting_proposal', 'meeting_completed_at', 'ack_due_on', 'acknowledged_at') if k in row}
    if own or hr:
        if row.get('dispute'): result['dispute'] = deepcopy(row['dispute'])
    if hr: result['actual_corrections'] = deepcopy(row.get('actual_corrections', []))
    result.update(employee_name=employee.get('full_name'), department=employee.get('department'), role_title=employee.get('role_title'), scores_released=flow.released(row), can_self_assess=own and row['status'] == 'Self_Draft', can_manage=manager, can_hr_review=hr, can_delete=False)
    try: personal_grant(user, 'M05', write=True)
    except flow.HTTPException:
        for flag in ('can_self_assess', 'can_manage', 'can_hr_review'): result[flag] = False
    if hr or flow.released(row):
        for field in ('manager_assessment', 'section_a_kpi_scores', 'section_a_score', 'section_b_score', 'section_c_score', 'overall_score', 'rating', 'nine_box_placement', 'hr_summary', 'scoring_policy', 'released_at', 'outcomes'):
            if field in row: result[field] = deepcopy(row[field])
    elif manager:
        result['manager_assessment'] = deepcopy(row.get('manager_assessment'))
        result['section_a_kpi_scores'] = deepcopy(row.get('section_a_kpi_scores'))
        result['section_a_score'] = row.get('section_a_score')
    if 'scoring_policy' in result and not hr:
        result['scoring_policy'] = {field: result['scoring_policy'].get(field) for field in ('source', 'weights', 'section_c')}
    summary = row.get('peer_summary') or {}
    # Do not reveal rolling averages: comparing successive results could identify
    # a respondent. The collection period and minimum count apply to HR too.
    try:
        peers_closed = today() > date.fromisoformat(row['peer_due_on'])
    except (KeyError, TypeError, ValueError):
        peers_closed = False
    count = summary.get('response_count')
    enough_peers = isinstance(count, int) and not isinstance(count, bool) and count >= 3
    may_see_peers = flow.released(row) or hr or (manager and MANAGER_MEETING_PEER_ACCESS)
    if may_see_peers and peers_closed and enough_peers:
        summary = {field: deepcopy(summary[field]) for field in (
            'score', 'response_count', 'averages', 'dimension_scores', 'gaps',
            'flagged', 'comments', 'retention_average') if field in summary}
        if summary:
            if not hr: summary.pop('retention_average', None)
            secrets.SystemRandom().shuffle(summary.get('comments', []))
        result['peer_summary'] = summary
    return result


async def record(db, user, reference):
    row, employee = await flow.record(db, user, reference)
    if row.get('workflow_version') != 3: flow.fail('Use the original workflow for this earlier review', 409)
    return row, employee


async def evidence_options(db, user):
    employee = await self_employee(db, user)
    rows = await db.employee_documents.find(scoped(user, {'employee_id': {'$in': reference_ids(employee)}, 'publication_state': 'Ready', 'scan_status': 'Clean', 'deleted_at': None, 'visibility': 'hr_employee_manager', 'confidential': False})).to_list(None)
    from routes.documents import _restricted
    return [{'id': str(r.get('id') or r['_id']), 'name': r.get('file_name') or 'Evidence document'} for r in rows if not _restricted(r)]


async def evidence(db, user, references):
    if not isinstance(references, list) or len(references) > 10 or any(not isinstance(x, str) for x in references): flow.fail('Select up to ten authorized evidence documents')
    allowed = {r['id'] for r in await evidence_options(db, user)}
    if set(references) - allowed: flow.fail('Evidence must be your clean documents explicitly shared with the manager', 403)
    return list(dict.fromkeys(references))


def check_window(row, field):
    if today() < date.fromisoformat(row['starts_on']) or today() > date.fromisoformat(row[field]): flow.fail('This assessment window is not open', 409)
