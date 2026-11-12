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
    if not process.enabled(employee) or process.ed(employee): flow.fail('Not eligible to submit staff peer assessments', 403)
    task = await db.performance_peer_tasks.find_one(process.scoped(user, {'id': reference, 'reviewer_employee_id': {'$in': reference_ids(employee)}}))
    if not task: flow.fail('Peer assessment not found', 404)
    if task['employee_id'] in reference_ids(employee): flow.fail('Self peer-assessment is not permitted', 403)
    return task, employee


async def listing(db, user):
    personal_grant(user, 'M05')
    employee = await process.self_employee(db, user)
    if not process.enabled(employee) or process.ed(employee): return []
    rows = await db.performance_peer_tasks.find(process.scoped(user, {'reviewer_employee_id': {'$in': reference_ids(employee)}})).to_list(None)
    result = []
    for row in rows:
        subject = await process.find_employee(db, row['employee_id'], process.tenant_of(user))
        if not subject or not process.enabled(subject) or not process.fte(subject) or row['employee_id'] in reference_ids(employee): continue
        can_submit = False
        if row['status'] == 'Assigned':
            try:
                window = await process.cycle(db, user, row['cycle_id'])
                can_submit = window.get('status') == 'Open' and date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(row['due_on'])
            except (KeyError, ValueError, TypeError):
                continue
            except flow.HTTPException as error:
                if error.status_code in (404, 409): continue
                raise
        result.append({'id': row['id'], 'employee_name': subject.get('full_name'), 'department': subject.get('department'),
                       'role_title': subject.get('role_title'), 'due_on': row['due_on'], 'status': row['status'], 'can_submit': can_submit})
    return result


async def submit(db, user, reference, body):
    process.fields(body, {'scores', 'retain', 'relationship', 'comment'})
    task, employee = await owned_task(db, user, reference)
    subject = await process.find_employee(db, task['employee_id'], process.tenant_of(user))
    if not subject or not process.enabled(subject) or not process.fte(subject): flow.fail('The colleague is no longer eligible for this review', 409)
    if task['status'] != 'Assigned': flow.fail('This task was already submitted or needs recovery', 409)
    window = await process.cycle(db, user, task['cycle_id'])
    if window.get('status') != 'Open' or not date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(task['due_on']):
        flow.fail('Peer assessment collection is closed', 409)
    scores = body.get('scores')
    if not isinstance(scores, list) or len(scores) != 5: flow.fail('Complete all five values')
    scores = [float(scoring.number(value, 0, 10)) for value in scores]
    retain = scoring.number(body.get('retain'), 0, 10)
    if retain not in {0, 5, 10}: flow.fail('Choose Yes, Maybe or No for retention')
    if body.get('relationship') not in {'Peer', 'Direct_Report', 'Cross_Functional'}: flow.fail('Choose your working relationship')
    comment = body.get('comment', '')
    if not isinstance(comment, str) or len(comment) > 4000: flow.fail('Comment must contain no more than 4,000 characters')
    # CAS prevents a second worker submitting the same assignment. Do not remove
    # this claim automatically following an uncertain database/network outcome.
    claimed = await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Assigned'}, {'$set': {'status': 'Submitting'}})
    if not claimed.modified_count: flow.fail('This task is already being submitted', 409)
    identity = process.key('v3-response', process.tenant_of(user), task['id'])
    try:
        await db.performance_peer_responses.insert_one({
            '_id': identity, 'tenant_id': process.tenant_of(user), 'review_id': task['review_id'],
            'cycle_id': task['cycle_id'], 'scores': scores, 'retain': float(retain),
            'relationship': body['relationship'], 'comment': comment.strip(),
        })
    except DuplicateKeyError:
        flow.fail('This assessment already has a response; ask HR to check completion', 409)
    await db.performance_peer_tasks.update_one({'_id': task['_id'], 'status': 'Submitting'}, {'$set': {'status': 'Submitted'}})
    await flow.audit(db, user, 'performance.v3.peer.completed', {'id': task['id']}, cycle_id=task['cycle_id'])
    return {'status': 'Submitted'}
