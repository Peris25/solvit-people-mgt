"""HR preparation, peer collection controls and cycle reporting."""
from datetime import date, timedelta
from utils import performance_v3 as process, performance_workflows as flow, performance_v3_scoring as scoring


async def dashboard(db, user):
    flow.require_hr(user)
    result = await process.setup(db, user)
    from routes.surveys import FTE_ALIGNMENT_QUESTIONS
    result['questions'] = FTE_ALIGNMENT_QUESTIONS
    result['cycles'] = [process.clean(r) for r in await db.performance_cycles.find(process.scoped(user, {'workflow_version': 3})).sort('starts_on', -1).to_list(50)]
    result['reviewers'] = [{'id': process.employee_key(e), 'name': e.get('full_name'), 'department': e.get('department')} for e in
                           await db.employees.find(process.tenant_query(process.tenant_of(user))).to_list(None)
                           if process.enabled(e) and process.fte(e) and not process.ed(e)]
    result['reviews'] = []
    for row in await db.performance_reviews.find(process.scoped(user, {'workflow_version': 3})).to_list(None):
        employee = await flow.employee_access(db, user, row['employee_id'])
        visible = process.projection(row, user, employee)
        tasks = await db.performance_peer_tasks.find(process.scoped(user, {'review_id': row['id']})).to_list(None)
        visible['peer_tasks'] = []
        for task in tasks:
            reviewer = await process.find_employee(db, task['reviewer_employee_id'], process.tenant_of(user))
            visible['peer_tasks'].append({'id': task['id'], 'name': (reviewer or {}).get('full_name', 'Unavailable employee'), 'status': task['status'], 'due_on': task['due_on']})
        result['reviews'].append(visible)
    return result


async def peers(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'reviewer_ids', 'extend_days', 'reason'})
    row, employee = await process.record(db, user, reference)
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('Another HR approver must manage your peer assignments', 403)
    if row.get('peer_summary') or row.get('released_at'): flow.fail('Peer results have already been compiled', 409)
    window = await process.cycle(db, user, row['cycle_id'])
    if window.get('status') != 'Open': flow.fail('The cycle is not open', 409)
    reason = flow.text(body.get('reason'), 'peer collection change reason', 1500)
    if len(reason) < 10: flow.fail('Explain the collection change in at least ten characters')
    days = body.get('extend_days', 0)
    if type(days) is not int or not 0 <= days <= 3: flow.fail('Extension must be zero to three days')
    current = date.fromisoformat(row['peer_due_on']); deadline = current
    if days:
        responses = await db.performance_peer_responses.find(process.scoped(user, {'review_id': row['id']})).to_list(3)
        if len(responses) >= 3: flow.fail('Extension is only allowed when fewer than three responses exist', 409)
        deadline = date.fromisoformat(window['peer_due_on']) + timedelta(days=days)
        if deadline <= current or process.today() > deadline: flow.fail('Choose a later deadline within three days of the original deadline', 409)
    identifiers = body.get('reviewer_ids', [])
    if not isinstance(identifiers, list) or len(identifiers) > 100 or any(not isinstance(i, str) for i in identifiers): flow.fail('Choose eligible reviewers')
    reviewers = []
    for reference in set(identifiers):
        reviewer = await process.find_employee(db, reference, process.tenant_of(user))
        if not reviewer or not process.enabled(reviewer) or not process.fte(reviewer) or process.ed(reviewer) or process.employee_key(reviewer) == row['employee_id']:
            flow.fail('A selected reviewer is not eligible', 409)
        reviewers.append(reviewer)
    if process.today() > deadline: flow.fail('Peer collection has closed; use a permitted extension first', 409)
    if not days and not reviewers: flow.fail('Select reviewers or a deadline extension')
    await flow.audit(db, user, 'performance.v3.peers.changed', row, reason=reason, reviewer_ids=sorted(set(identifiers)), due_on=deadline.isoformat())
    if days:
        tasks = await db.performance_peer_tasks.find(process.scoped(user, {'review_id': row['id'], 'status': 'Assigned'})).to_list(None)
        for task in tasks: await db.performance_peer_tasks.update_one({'_id': task['_id']}, {'$set': {'due_on': deadline.isoformat()}})
        row = await process.save(db, user, row, {'peer_due_on': deadline.isoformat()}, 'peers.extended')
    for reviewer in reviewers: await process.peer_task(db, user, row, reviewer, deadline.isoformat())
    return {'status': 'Saved', 'peer_due_on': deadline.isoformat()}


async def company_feedback(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'nps', 'csat', 'source_reference', 'reason'})
    window = await process.cycle(db, user, reference)
    if window.get('workflow_version') != 3: flow.fail('Choose a V3 cycle', 409)
    reason = body.get('reason', '')
    affected = []
    if window.get('company_feedback'):
        if len(flow.text(reason, 'company feedback correction reason', 1500)) < 10: flow.fail('Explain the correction in at least ten characters')
        affected = await db.performance_reviews.find(process.scoped(user, {'cycle_id': window['id'], 'workflow_version': 3})).to_list(None)
        if any(r.get('meeting_completed_at') or r.get('released_at') for r in affected): flow.fail('Company feedback cannot change after a meeting is completed or a score released', 409)
    nps = float(scoring.number(body.get('nps'), -100, 100)); csat = float(scoring.number(body.get('csat'), 1, 5))
    source = flow.text(body.get('source_reference'), 'verified company feedback reference', 1000)
    if process.today() <= date.fromisoformat(window['self_due_on']): flow.fail('Record verified company feedback in Week 2, after self/peer collection', 409)
    await flow.audit(db, user, 'performance.v3.company_feedback.recorded', window, source_reference=source, reason=reason, before=window.get('company_feedback'))
    await db.performance_cycles.update_one({'_id': window['_id']}, {'$set': {'company_feedback': {'nps': nps, 'csat': csat, 'source_reference': source, 'recorded_by': user['id']}}})
    for row in affected:
        if row['status'] == 'HR_Reviewed':
            await process.save(db, user, row, {'status': 'Manager_Submitted', 'peer_summary': None, 'section_b_score': None,
                'section_c_score': None, 'overall_score': None, 'rating': None, 'nine_box_placement': None,
                'review_meeting': None, 'meeting_proposal': None}, 'company_feedback.corrected')
            await process.notice(db, row, 'company-feedback-corrected:' + process.flow.now(), 'employee', row['line_manager_id'], 'Company feedback corrected; HR will reconfirm the review and meeting')
    return {'status': 'Saved'}


async def followup(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'expected_version', 'key', 'notes'})
    row, employee = await process.record(db, user, reference)
    from utils.performance_v3_reviews import version
    version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('Another HR approver must administer your follow-up', 403)
    if not flow.released(row): flow.fail('Release the review before completing follow-up', 409)
    outcomes = row.get('outcomes', [])
    item = next((o for o in outcomes if o['key'] == body.get('key')), None)
    if not item or item['status'] == 'Completed': flow.fail('Follow-up is unavailable or completed', 409)
    item.update(status='Completed', notes=flow.text(body.get('notes'), 'completion notes', 2000), completed_at=flow.now(), completed_by=user['id'])
    saved = await process.save(db, user, row, {'outcomes': outcomes}, 'followup.completed')
    return process.projection(saved, user, employee)


async def resolve_dispute(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'expected_version', 'resolution'})
    row, employee = await process.record(db, user, reference)
    from utils.performance_v3_reviews import version
    version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('Another HR approver must resolve your dispute', 403)
    if not row.get('dispute') or row['dispute']['status'] != 'Pending_HR': flow.fail('No unresolved dispute exists', 409)
    dispute = {**row['dispute'], 'status': 'Resolved', 'resolution': flow.text(body.get('resolution'), 'written resolution', 4000), 'resolved_at': flow.now(), 'resolved_by': user['id']}
    saved = await process.save(db, user, row, {'dispute': dispute}, 'dispute.resolved')
    await process.notice(db, saved, 'dispute-resolved', 'employee', row['employee_id'], 'HR responded to your performance review dispute')
    return process.projection(saved, user, employee)
