"""Anonymous peer submissions with separate assignment/completion tracking.

No HTTP endpoint exposes individual responses. Call mutations under the existing
integrity lock. An interrupted Submitting task fails closed for operator review.
"""
from datetime import date
from pymongo.errors import DuplicateKeyError

from utils import performance_v3 as process, performance_v3_scoring as scoring
from utils import performance_workflows as flow
from utils.employee_access import personal_grant, reference_ids
from utils.employee_integrity import employee_key


async def owned_task(db, user, reference):
    personal_grant(user, 'M05', write=True)
    employee = await process.self_employee(db, user)
    if not process.enabled(employee) or process.ed(employee) or not process.fte(employee): flow.fail('Not eligible to submit staff peer assessments', 403)
    task = await db.performance_peer_tasks.find_one(process.scoped(user, {'id': reference, 'reviewer_employee_id': {'$in': reference_ids(employee)}}))
    if not task: flow.fail('Peer assessment not found', 404)
    if task['employee_id'] in reference_ids(employee): flow.fail('Self peer-assessment is not permitted', 403)
    return task, employee


async def listing(db, user):
    personal_grant(user, 'M05')
    employee = await process.self_employee(db, user)
    if not process.enabled(employee) or process.ed(employee) or not process.fte(employee): return []
    rows = await db.performance_peer_tasks.find(process.scoped(user, {'reviewer_employee_id': {'$in': reference_ids(employee)}})).to_list(None)
    result = []
    for row in rows:
        if row.get('status') in {'Archived','Cancelled'}: continue
        subject = await process.find_employee(db, row['employee_id'], process.tenant_of(user))
        if not subject or not process.enabled(subject) or not process.fte(subject) or row['employee_id'] in reference_ids(employee): continue
        can_submit = False
        if row['status'] == 'Assigned':
            try:
                window = await process.cycle(db, user, row['cycle_id'])
                can_submit = window.get('status') == 'Open' and date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(row['due_on'])
                if can_submit: await collection_open(db, user, row)
            except (KeyError, ValueError, TypeError):
                continue
            except flow.HTTPException as error:
                if error.status_code in (404, 409): continue
                raise
        result.append({'id': row['id'], 'cycle_id': row['cycle_id'], 'employee_id': row['employee_id'], 'employee_name': subject.get('full_name'), 'department': subject.get('department'),
                       'role_title': subject.get('role_title'), 'due_on': row['due_on'], 'status': row['status'], 'can_submit': can_submit,
                       'started': bool(row.get('started_at')), 'can_remove': can_submit and not row.get('started_at'), 'draft': row.get('draft') if can_submit else None})
    return result


async def submit(db, user, reference, body):
    process.fields(body, {'scores', 'retain', 'relationship', 'comment', 'strengthens_team', 'more_effective'})
    task, employee = await owned_task(db, user, reference)
    subject = await process.find_employee(db, task['employee_id'], process.tenant_of(user))
    if not subject or not process.enabled(subject) or not process.fte(subject): flow.fail('The colleague is no longer eligible for this review', 409)
    if task['status'] != 'Assigned': flow.fail('This task was already submitted or needs recovery', 409)
    await collection_open(db, user, task)
    window = await process.cycle(db, user, task['cycle_id'])
    if window.get('status') != 'Open' or not date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(task['due_on']):
        flow.fail('Peer assessment collection is closed', 409)
    chosen = await db.performance_peer_tasks.find(process.scoped(user, {'cycle_id': task['cycle_id'], 'reviewer_employee_id': {'$in': reference_ids(employee)}, 'status': {'$in': ['Assigned', 'Submitted', 'Submitting']}})).to_list(None)
    if len({entry['employee_id'] for entry in chosen}) < 5: flow.fail('Choose at least five colleagues for this cycle before submitting peer reviews', 409)
    scores = body.get('scores')
    if not isinstance(scores, list) or len(scores) != 5: flow.fail('Complete all five values')
    scores = [float(scoring.number(value, 0, 10)) for value in scores]
    retain = scoring.number(body.get('retain'), 0, 10)
    if retain not in {0, 5, 10}: flow.fail('Choose Yes, Maybe or No for retention')
    if body.get('relationship') not in {'Peer', 'Direct_Report', 'Cross_Functional'}: flow.fail('Choose your working relationship')
    comment = body.get('comment', '')
    if not isinstance(comment, str) or len(comment) > 4000: flow.fail('Comment must contain no more than 4,000 characters')
    comments = {}
    for field in ('strengthens_team', 'more_effective'):
        value = body.get(field, '')
        if not isinstance(value, str) or len(value) > 4000: flow.fail('Each comment must contain no more than 4,000 characters')
        comments[field] = value.strip()
    # CAS prevents a second worker submitting the same assignment. Do not remove
    # this claim automatically following an uncertain database/network outcome.
    claimed = await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Assigned'}, {'$set': {'status': 'Submitting'}})
    if not claimed.modified_count: flow.fail('This task is already being submitted', 409)
    identity = process.key('v3-response', process.tenant_of(user), task['id'])
    try:
        await db.performance_peer_responses.insert_one({
            '_id': identity, 'tenant_id': process.tenant_of(user), 'review_id': task['review_id'],
            'cycle_id': task['cycle_id'], 'scores': scores, 'retain': float(retain),
            'relationship': body['relationship'], 'comment': comment.strip(), **comments,
        })
    except DuplicateKeyError:
        flow.fail('This assessment already has a response; ask HR to check completion', 409)
    await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Submitting'}, {'$set': {'status': 'Submitted'}, '$unset': {'draft': ''}})
    await flow.audit(db, user, 'performance.v3.peer.completed', {'id': task['id']}, cycle_id=task['cycle_id'])
    return {'status': 'Submitted'}


async def choices(db, user):
    personal_grant(user, 'M05')
    employee = await process.self_employee(db, user)
    if not process.enabled(employee) or process.ed(employee) or not process.fte(employee): return []
    windows = await db.performance_cycles.find(process.scoped(user, {'workflow_version': 3, 'status': 'Open'})).to_list(None)
    result = []
    colleagues = await db.employees.find(process.tenant_query(process.tenant_of(user))).to_list(None)
    for window in windows:
        if process.today() < date.fromisoformat(window['starts_on']): continue
        reviews = await db.performance_reviews.find(process.scoped(user, {'cycle_id': window['id'], 'workflow_version': 3, 'status': {'$nin': ['Archived', 'Cancelled']}})).to_list(None)
        for colleague in colleagues:
            if not process.enabled(colleague) or employee_key(colleague) in reference_ids(employee): continue
            review = next((row for row in reviews if row['employee_id'] in reference_ids(colleague)), None)
            eligible = bool(review and not review.get('peer_summary') and not review.get('released_at') and process.today() <= date.fromisoformat(review['peer_due_on']) and process.fte(colleague))
            result.append({'employee_id': employee_key(colleague), 'employee_name': colleague.get('full_name'), 'department': colleague.get('department'), 'role_title': colleague.get('role_title'),
                           'cycle_id': window['id'], 'cycle_title': f"{window['cycle_type']} {window['cycle_year']}", 'review_id': review['id'] if eligible else None,
                           'unavailable_reason': None if eligible else 'No open peer review for this cycle'})
    return result


async def choose(db, user, reference, body):
    process.fields(body, set())
    personal_grant(user, 'M05', write=True)
    employee = await process.self_employee(db, user)
    option = next((item for item in await choices(db, user) if item['review_id'] == reference), None)
    if not option: flow.fail('Choose a colleague with an open peer review', 409)
    review = await db.performance_reviews.find_one(process.scoped(user, {'id': reference}))
    await process.peer_task(db, user, review, employee, review['peer_due_on'])
    return {'status': 'Selected'}


async def remove(db, user, reference, body):
    process.fields(body, set())
    task, employee = await owned_task(db, user, reference)
    if task['status'] != 'Assigned' or task.get('started_at'): flow.fail('Only an unstarted review can be removed', 409)
    await collection_open(db, user, task)
    # Once any review has been submitted, keep the chosen list at five or more.
    others = await db.performance_peer_tasks.find(process.scoped(user, {'cycle_id': task['cycle_id'], 'reviewer_employee_id': {'$in': reference_ids(employee)}})).to_list(None)
    if any(row['status'] in {'Submitted', 'Submitting'} for row in others) and len(others) <= 5:
        flow.fail('Keep at least five colleagues in this cycle', 409)
    await db.performance_peer_tasks.delete_one({'_id': task['_id'], 'status': 'Assigned', 'started_at': {'$exists': False}})
    return {'status': 'Removed'}


async def collection_open(db, user, task):
    window = await process.cycle(db, user, task['cycle_id'])
    review = await db.performance_reviews.find_one(process.scoped(user, {'id': task['review_id']}))
    if not review or review['status'] in {'Archived', 'Cancelled'} or review.get('peer_summary') or review.get('released_at') or window.get('status') != 'Open' or not date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(task['due_on']):
        flow.fail('Peer assessment collection is closed', 409)


async def draft(db, user, reference, body):
    process.fields(body, {'scores', 'retain', 'relationship', 'strengthens_team', 'more_effective'})
    task, employee = await owned_task(db, user, reference)
    if task['status'] != 'Assigned': flow.fail('This peer review is final and cannot be edited', 409)
    await collection_open(db, user, task)
    scores = body.get('scores', [''] * 5)
    if not isinstance(scores, list) or len(scores) != 5: flow.fail('Provide five values scores')
    values = {'scores': [float(scoring.number(score, 0, 10)) if score not in ('', None) else '' for score in scores]}
    retain = body.get('retain', '')
    if retain not in ('', None) and scoring.number(retain, 0, 10) not in {0, 5, 10}: flow.fail('Choose Yes, Maybe or No for retention')
    values['retain'] = float(retain) if retain not in ('', None) else ''
    if body.get('relationship', 'Peer') not in {'Peer', 'Direct_Report', 'Cross_Functional'}: flow.fail('Choose your working relationship')
    values['relationship'] = body.get('relationship', 'Peer')
    for field in ('strengthens_team', 'more_effective'):
        value = body.get(field, '')
        if not isinstance(value, str) or len(value) > 4000: flow.fail('Each comment must contain no more than 4,000 characters')
        values[field] = value
    await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Assigned'}, {'$set': {'draft': values, 'started_at': task.get('started_at') or flow.now()}})
    return {'status': 'Draft saved'}


async def start(db, user, reference, body):
    process.fields(body, set())
    task, employee = await owned_task(db, user, reference)
    if task['status'] != 'Assigned': flow.fail('This peer review is final and cannot be edited', 409)
    await collection_open(db, user, task)
    await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Assigned'}, {'$set': {'started_at': task.get('started_at') or flow.now()}})
    return {'status': 'Started'}
