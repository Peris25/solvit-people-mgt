"""Read-time Solver compatibility and evidence-backed induction controls.

No roster import, guessed job statistics, or historical score recalculation.
"""
from datetime import datetime, timezone
import math
from fastapi import HTTPException
from utils.employee_integrity import tenant_of, tenant_query, resolve_user_employee
from utils.solver_access import (solver_access, solver_key, solver_aliases, HR_ROLES,
                                audit_solver)
from utils.staff_directory import normalized, visible_state, employment_type
from utils.access_matrix import RUNTIME_OVERRIDES

STATES = ('Registering', 'Active', 'Suspended', 'Inactive', 'Deactivated')
GATES = ('contact', 'video', 'code_quiz', 'agreement', 'vehicle_assessment')


def now():
    return datetime.now(timezone.utc).isoformat()


def view(record):
    """Aliases are a projection only; never rewrite imported records on a read."""
    row = dict(record)
    for target, aliases in {
        'region': ('county',), 'area_covered': ('area', 'sub_county'),
        'vehicle_categories': ('vehicle_categories_certified',),
        'zones_covered': ('nairobi_zones_covered',),
        'performance_tier': ('overall_performance_tier',),
        'jobs_completed': ('jobs_completed_total',),
        'lifecycle_state': ('status',),
    }.items():
        if row.get(target) is None:
            row[target] = next((row[a] for a in aliases if row.get(a) is not None), None)
    for key in ('zones_covered', 'vehicle_categories'):
        value = row.get(key)
        row[key] = [str(v) for v in value if isinstance(v, (str, int))] if isinstance(value, list) else [value] if isinstance(value, str) and value.strip() else []
    state = next((s for s in STATES if normalized(s) == normalized(row.get('lifecycle_state'))), None)
    row['lifecycle_state'] = state or row.get('lifecycle_state') or 'Unknown'
    legacy_states = {normalized(record.get(key)) for key in ('lifecycle_state', 'status') if record.get(key)}
    if len(legacy_states) > 1:
        row['lifecycle_state'] = 'Requires review'
    if record.get('activation_publication_state') not in (None, 'Ready'):
        row['lifecycle_state'] = 'Requires review'
    return row


async def directory_access(db, user):
    try:
        return await solver_access(db, user)
    except HTTPException as error:
        if error.status_code != 403:
            raise
    # Brief 5.6 grants a CONTACT directory, not M02 administration, to Operations
    # and Account Management FTEs. Explicit runtime revocations still take priority.
    if user.get('role') not in {'employee', 'line_manager'} or ('M02', user.get('role')) in RUNTIME_OVERRIDES:
        raise HTTPException(403, 'No access to the Solver directory')
    employee = await resolve_user_employee(db, user)
    if not employee or not visible_state(employee) or employment_type(employee.get('employment_type')) != 'Full_Time' or normalized(employee.get('department')) not in {'operations', 'accountmanagement'}:
        raise HTTPException(403, 'Solver directory is restricted to HR, Operations and Account Management')
    return {'level': 'Read', 'scope': 'directory_only'}


def directory_view(record):
    row = view(record)
    fields = ('full_name', 'phone_number', 'email', 'region', 'area_covered',
              'lifecycle_state', 'vehicle_categories', 'zones_covered')
    return {**{key: row.get(key) for key in fields}, 'id': str(record['_id']),
            'canonical_id': solver_key(record)}


def task_query(record):
    return {'$and': [tenant_query(tenant_of(record)),
                    {'entity_type': 'solver', 'entity_id': {'$in': solver_aliases(record)}}]}


async def notify(db, record, event, version):
    # Stable IDs prevent retries from delivering the same event twice. Generic
    # Notification Centre previews never contain contact, scores or statutory data.
    for role in ('hr_admin', 'hr_manager', 'solver'):
        key = f'solver:{tenant_of(record)}:{solver_key(record)}:{event}:{version}:{role}'
        recipient = {'recipient_type': 'solver', 'recipient_id': solver_key(record)} if role == 'solver' else {'recipient_role': role}
        await db.notifications.update_one({'_id': key}, {'$setOnInsert': {
            'id': key, 'tenant_id': tenant_of(record), **recipient,
            'category': 'Onboarding', 'created_at': now(), 'is_read': False,
            'data': {'solver_id': solver_key(record), 'solver_workflow': True},
        }}, upsert=True)


async def verification(db, user, record):
    rows = await db.solver_verifications.find({'$and': [tenant_query(tenant_of(user)),
        {'solver_id': {'$in': solver_aliases(record)}}]}).to_list(None)
    latest = {}
    for row in sorted(rows, key=lambda r: str(r.get('created_at') or '')):
        latest[row.get('gate')] = row if row.get('publication_state') == 'Ready' else {**row, 'verified': False}
    return latest


async def activation_ready(db, user, record):
    gates = await verification(db, user, record)
    missing = [gate for gate in GATES if not gates.get(gate, {}).get('verified')]
    if missing:
        raise HTTPException(409, 'Activation requires verified contact form, induction video, code quiz, signed agreement and a recorded vehicle assessment pass')
    # Evidence can be withdrawn or quarantined after verification; recheck it.
    for gate in GATES:
        await evidence_document(db, user, record, gates[gate].get('document_id'))
    quiz = gates['code_quiz']
    if quiz.get('score') is None or quiz['score'] < 8 or quiz.get('maximum') != 10:
        raise HTTPException(409, 'The code quiz requires at least 8/10')


async def evidence_document(db, user, record, reference):
    from utils.employee_access import find_linked_record
    doc = await find_linked_record(db.solver_documents, reference, user)
    if doc.get('solver_id') not in solver_aliases(record) or doc.get('deleted_at') or doc.get('publication_state') != 'Ready' or doc.get('scan_status') != 'Clean':
        raise HTTPException(409, 'Choose a clean, available document assigned to this Solver')
    from utils.solver_documents import visible
    if not visible(doc, user):
        raise HTTPException(403, 'Evidence has not been shared with your role')
    return doc


async def verify_gate(db, user, record, body):
    if not isinstance(body, dict) or set(body) - {'gate', 'document_id', 'reference', 'score', 'maximum', 'outcome'}:
        raise HTTPException(422, 'Unknown verification fields')
    gate = body.get('gate')
    if gate not in GATES:
        raise HTTPException(422, 'Choose a documented induction requirement')
    reference = body.get('reference')
    if not isinstance(reference, str) or not 3 <= len(reference.strip()) <= 300 or any(ord(c) < 32 for c in reference):
        raise HTTPException(422, 'A verification reference is required')
    doc = await evidence_document(db, user, record, body.get('document_id'))
    expected = {'contact': 'Contact and statutory form', 'video': 'Induction video confirmation',
                'code_quiz': 'Code quiz result', 'agreement': 'Signed Solver agreement', 'vehicle_assessment': 'Vehicle assessment'}
    if doc.get('category') != expected[gate]:
        raise HTTPException(422, 'Supporting document category must match the induction requirement')
    if gate == 'code_quiz':
        score = body.get('score')
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10 or body.get('maximum') != 10:
            raise HTTPException(422, 'Record the actual quiz result out of 10')
    elif 'score' in body or 'maximum' in body:
        raise HTTPException(422, 'Scores apply only to the code quiz')
    if gate == 'vehicle_assessment':
        if body.get('outcome') not in {'Pass', 'Fail', 'Re-sit'}:
            raise HTTPException(422, 'Record the evidenced assessment decision; no score or pass mark is inferred')
    elif 'outcome' in body:
        raise HTTPException(422, 'An assessment decision applies only to vehicle assessment evidence')
    import uuid
    row = {'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user), 'solver_id': solver_key(record),
           **body, 'reference': reference.strip(), 'document_id': str(doc.get('id') or doc['_id']),
           'verified': body['score'] >= 8 if gate == 'code_quiz' else body['outcome'] == 'Pass' if gate == 'vehicle_assessment' else True,
           'verified_by': user['id'], 'created_at': now(), 'publication_state': 'Pending_Audit'}
    # Evidence records append only. They do not replace existing form answers,
    # statutory data or historical performance scores.
    await db.solver_verifications.insert_one(row)
    await audit_solver(db, user, 'solver.induction.verified', [record], [gate])
    await notify(db, record, 'verified', row['id'])
    await db.solver_verifications.update_one({'id': row['id'], 'tenant_id': tenant_of(user)}, {'$set': {'publication_state': 'Ready'}})
    row['publication_state'] = 'Ready'
    task_key = {'contact': 'S01', 'video': 'S02', 'code_quiz': 'S04', 'agreement': 'S05', 'vehicle_assessment': 'S03'}[gate]
    tasks = await db.onboarding_tasks.find(task_query(record)).to_list(None)
    for task in tasks:
        if task.get('task_key') == task_key:
            await db.onboarding_tasks.update_one({'_id': task['_id']}, {'$set': {
                'status': 'Completed' if row['verified'] else 'Pending',
                'completed_at': row['created_at'] if row['verified'] else None,
                'completed_by': user['id'], 'verification_id': row['id']}})
    return {key: value for key, value in row.items() if key != '_id'}


async def submit_code_quiz(db, user, body, schema):
    """FRD Form03: own answers, 8/10, seven-day retry, three-failure review."""
    from datetime import timedelta
    from utils.solver_access import own_solver, authorize_solver
    import uuid
    if user.get('role') != 'solver':
        raise HTTPException(403, 'Only the subject Solver may answer this quiz')
    record = await own_solver(db, user)
    await authorize_solver(db, user, solver_key(record))
    for ref in (body.get('solver_id'), (body.get('data') or {}).get('solver_id')):
        if ref:
            chosen = await authorize_solver(db, user, ref)
            if chosen['_id'] != record['_id']:
                raise HTTPException(403, 'Conflicting Solver identity')
    answers = body.get('data') or body.get('answers') or {}
    if not isinstance(answers, dict):
        raise HTTPException(422, 'Quiz answers must be an object')
    questions = [field for section in schema['sections'] for field in section['fields'] if field.get('correct_answer')]
    if len(questions) != 10:
        raise HTTPException(409, 'The approved ten-question code quiz is unavailable')
    if any(answers.get(field['id']) not in field.get('options', []) for field in questions):
        raise HTTPException(422, 'Answer all ten questions using the available choices')
    previous = await db.form_submissions.find({'$and': [tenant_query(tenant_of(user)),
        {'subject_solver_id': {'$in': solver_aliases(record)}, 'form_id': 'form-03'}]}).to_list(None)
    previous.sort(key=lambda row: str(row.get('submitted_at') or ''))
    if previous:
        if previous[-1].get('passed'):
            raise HTTPException(409, 'The code quiz is already passed; historical results are preserved')
        if len(previous) >= 3:
            raise HTTPException(409, 'Three failed attempts require Solvers Manager review before another attempt')
        try:
            last = datetime.fromisoformat(previous[-1]['submitted_at'].replace('Z', '+00:00'))
            if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            raise HTTPException(409, 'Historical attempt timing needs HR verification')
        if datetime.now(timezone.utc) < last + timedelta(days=7):
            raise HTTPException(409, 'Wait seven days after a failed code quiz before retrying')
    score = sum(answers.get(field['id']) == field['correct_answer'] for field in questions)
    row = {'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user), 'form_id': 'form-03',
           'form_title': schema['title'], 'subject_solver_id': solver_key(record),
           'submitted_by': user['id'], 'data': {field['id']: answers[field['id']] for field in questions},
           'score': score, 'pass_mark': 8, 'passed': score >= 8, 'status': 'Submitted', 'submitted_at': now()}
    await db.form_submissions.insert_one(row)
    await audit_solver(db, user, 'solver.assessment.submitted', [record], ['form-03'])
    await notify(db, record, 'quiz_submitted', row['id'])
    return {key: value for key, value in row.items() if key not in {'_id', 'data'}}
