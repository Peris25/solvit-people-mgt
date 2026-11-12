"""Explicit V3 assessment transitions; callers must hold the integrity write lock."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

from utils import performance_v3 as process, performance_workflows as flow
from utils import performance_v3_scoring as scoring
from utils.employee_integrity import employee_key, is_direct_report
from utils.employee_access import personal_grant


def version(row, expected):
    if not expected or expected != row.get('version'):
        flow.fail('This review changed. Reload before saving.', 409)


def text(value, label, required=True):
    if not required and value in (None, ''):
        return ''
    return flow.text(value, label, 4000)


async def self_assessment(db, user, reference, body):
    process.fields(body, {'expected_version', 'assessment', 'submit'})
    row, employee = await process.record(db, user, reference)
    version(row, body.get('expected_version'))
    if user.get('employee_id') not in process.reference_ids(employee) or not personal_grant(user, 'M05', write=True):
        flow.fail('Only the employee may complete this self-assessment', 403)
    if row['status'] != 'Self_Draft': flow.fail('The self-assessment has already been submitted', 409)
    process.check_window(row, 'self_due_on')
    submit = body.get('submit', False)
    if not isinstance(submit, bool): flow.fail('Invalid submission action')
    value = body.get('assessment')
    process.fields(value, {'actuals', 'values', 'accomplishments', 'challenge', 'do_differently', 'support'})
    actuals = value.get('actuals', {})
    if not isinstance(actuals, dict): flow.fail('Provide KPI actuals by identifier')
    goals = {g['id']: g for g in row['section_a_kpis']}
    if set(actuals) - set(goals): flow.fail('Unknown KPI identifier')
    validated = {}
    for identifier, entry in actuals.items():
        process.fields(entry, {'actual', 'self_score', 'evidence', 'documents'})
        item = deepcopy(entry)
        if 'actual' in item: scoring.kpi_score(goals[identifier], item['actual'])
        if 'self_score' in item: item['self_score'] = float(scoring.number(item['self_score'], 1, 3))
        item['evidence'] = text(item.get('evidence'), 'KPI evidence', required=submit)
        item['documents'] = await process.evidence(db, user, item.get('documents', []))
        if submit and not {'actual', 'self_score'} <= set(item): flow.fail('Complete every KPI actual and self-rating')
        validated[identifier] = item
    if submit and set(validated) != set(goals): flow.fail('Complete every KPI before submitting')
    values = value.get('values', [])
    if not isinstance(values, list) or len(values) > 5: flow.fail('Provide the five values assessments')
    checked_values = []
    for entry in values:
        process.fields(entry, {'score', 'example'})
        checked_values.append({'score': float(scoring.number(entry.get('score'), 0, 10)), 'example': text(entry.get('example'), 'value example', required=submit)})
    if submit and len(checked_values) != 5: flow.fail('Complete all five values')
    accomplishments = value.get('accomplishments', [])
    if not isinstance(accomplishments, list) or len(accomplishments) > 3: flow.fail('Provide up to three accomplishments')
    accomplishments = [text(item, 'accomplishment') for item in accomplishments]
    if submit and len(accomplishments) != 3: flow.fail('Provide three accomplishments')
    assessment = {'actuals': validated, 'values': checked_values, 'accomplishments': accomplishments}
    for field in ('challenge', 'do_differently', 'support'):
        assessment[field] = text(value.get(field), field.replace('_', ' '), required=submit)
    update = {'self_assessment': assessment}
    if submit: update.update(status='Self_Submitted', self_submitted_at=flow.now())
    saved = await process.save(db, user, row, update, 'self.submitted' if submit else 'self.saved')
    if submit:
        await process.notice(db, saved, 'self-submitted', 'employee', row['line_manager_id'], 'Review your employee’s submitted assessment')
    return process.projection(saved, user, employee)


async def manager_assessment(db, user, reference, body):
    process.fields(body, {'expected_version', 'actuals', 'summary'})
    row, employee = await process.record(db, user, reference)
    version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee) or not is_direct_report(employee, user) or not personal_grant(user, 'M05', write=True):
        flow.fail('Only the assigned line manager may assess this employee', 403)
    if row['status'] != 'Self_Submitted': flow.fail('The employee must submit first', 409)
    process.check_window(row, 'manager_due_on')
    # Manager assessment begins after the employee/peer assessment week.
    if process.today() <= date.fromisoformat(row['self_due_on']): flow.fail('Manager assessment opens in Week 2', 409)
    actuals = body.get('actuals')
    if not isinstance(actuals, dict) or set(actuals) != {g['id'] for g in row['section_a_kpis']}:
        flow.fail('Confirm every KPI actual')
    confirmed = {}
    for identifier, entry in actuals.items():
        process.fields(entry, {'actual', 'comment'})
        original = row['self_assessment']['actuals'][identifier]['actual']
        comment = text(entry.get('comment'), 'manager comment', required=entry.get('actual') != original)
        confirmed[identifier] = {'actual': entry.get('actual'), 'comment': comment}
    result = scoring.section_a(row['section_a_kpis'], {k: v['actual'] for k, v in confirmed.items()}, row.get('group_weights'))
    saved = await process.save(db, user, row, {
        'manager_assessment': {'actuals': confirmed, 'summary': text(body.get('summary'), 'manager summary')},
        'section_a_score': result['score'], 'section_a_kpi_scores': result['kpi_scores'],
        'status': 'Manager_Submitted', 'manager_submitted_at': flow.now(),
    }, 'manager.submitted')
    await process.hr_notice(db, saved, 'manager-submitted', 'Performance assessment ready for HR review')
    return process.projection(saved, user, employee)


async def compile_review(db, user, reference, body):
    flow.require_hr(user)
    process.fields(body, {'expected_version', 'summary'})
    row, employee = await process.record(db, user, reference)
    version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('You cannot approve your own review', 403)
    if row['status'] != 'Manager_Submitted': flow.fail('Manager assessment must be completed first', 409)
    if process.today() <= date.fromisoformat(row['peer_due_on']): flow.fail('Peer responses remain confidential until the collection window closes', 409)
    responses = await db.performance_peer_responses.find(process.scoped(user, {'review_id': row['id']})).to_list(None)
    peer = scoring.section_b(responses, [v['score'] for v in row['self_assessment']['values']])
    peer['response_count'] = len(responses)
    # Never include respondent identities, response IDs or submission times.
    peer['comments'] = [text(r.get('comment'), 'peer comment', required=False) for r in responses if r.get('comment')]
    window = await process.cycle(db, user, row['cycle_id'])
    feedback = window.get('company_feedback')
    if not feedback: flow.fail('HR must record the company NPS and CSAT first', 409)
    c = scoring.section_c(feedback['nps'], feedback['csat'])
    overall = scoring.final(row['section_a_score'], peer['score'], c)
    from routes.performance import get_rating
    saved = await process.save(db, user, row, {
        'peer_summary': peer, 'section_b_score': peer['score'], 'section_c_score': c,
        'overall_score': overall, 'rating': get_rating(overall),
        'nine_box_placement': scoring.placement(row['section_a_score'], peer['score']),
        'hr_summary': text(body.get('summary'), 'HR summary'), 'status': 'HR_Reviewed', 'hr_reviewed_at': flow.now(),
    }, 'hr.reviewed')
    await process.notice(db, saved, 'meeting-needed', 'employee', row['line_manager_id'], 'Propose a performance review meeting date')
    return process.projection(saved, user, employee)
