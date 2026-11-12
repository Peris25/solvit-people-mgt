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
        value_score = entry.get('score')
        if not submit and value_score in (None, ''): value_score = None
        else: value_score = float(scoring.number(value_score, 0, 10))
        checked_values.append({'score': value_score, 'example': text(entry.get('example'), 'value example', required=submit)})
    if submit and len(checked_values) != 5: flow.fail('Complete all five values')
    accomplishments = value.get('accomplishments', [])
    if not isinstance(accomplishments, list) or len(accomplishments) > 3: flow.fail('Provide up to three accomplishments')
    accomplishments = [text(item, 'accomplishment', required=submit) for item in accomplishments]
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
    if user.get('employee_id') in process.reference_ids(employee) or not is_direct_report(employee, user) or row['line_manager_id'] not in process.user_employee_aliases(user) or not personal_grant(user, 'M05', write=True):
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


async def meeting(db, user, reference, body, action):
    row, employee = await process.record(db, user, reference)
    version(row, body.get('expected_version'))
    own = user.get('employee_id') in process.reference_ids(employee)
    if own: flow.fail('You cannot administer your own review meeting', 403)
    personal_grant(user, 'M05', write=True)
    if row['status'] != 'HR_Reviewed' or row.get('released_at'): flow.fail('Complete HR assessment before arranging the review meeting', 409)
    if action == 'propose':
        if not is_direct_report(employee, user) or row['line_manager_id'] not in process.user_employee_aliases(user): flow.fail('Only the assigned manager may propose the meeting', 403)
    else: flow.require_hr(user)
    if action in {'propose', 'schedule'}:
        process.fields(body, {'expected_version', 'scheduled_at', 'location'})
        try:
            scheduled = datetime.fromisoformat(body['scheduled_at'].replace('Z', '+00:00'))
            if scheduled.tzinfo is None: raise ValueError()
            meeting_day = scheduled.astimezone(timezone(timedelta(hours=3))).date()
            if scheduled <= process.instant() or not date.fromisoformat(row['manager_due_on']) < meeting_day <= date.fromisoformat(row['review_due_on']): raise ValueError()
        except (KeyError, TypeError, ValueError): flow.fail('Choose a future meeting in Weeks 3–4, including timezone')
        values = {'scheduled_at': scheduled.isoformat(), 'location': text(body.get('location'), 'meeting location')}
        field = 'meeting_proposal' if action == 'propose' else 'review_meeting'
        saved = await process.save(db, user, row, {field: values}, 'meeting.' + action)
        if action == 'propose': await process.hr_notice(db, saved, 'meeting-proposed:' + values['scheduled_at'], 'Manager proposed a review meeting; arrange it manually')
        for recipient in (row['employee_id'], row['line_manager_id']):
            await process.notice(db, saved, 'meeting-' + action + ':' + values['scheduled_at'], 'employee', recipient,
                                 'Performance review meeting ' + ('proposed' if action == 'propose' else 'confirmed by HR'))
    elif action == 'complete':
        process.fields(body, {'expected_version', 'notes'})
        scheduled = row.get('review_meeting', {}).get('scheduled_at')
        if not scheduled or datetime.fromisoformat(scheduled) > process.instant(): flow.fail('The scheduled meeting must take place first', 409)
        if row.get('meeting_completed_at'): flow.fail('Meeting completion is already recorded', 409)
        saved = await process.save(db, user, row, {'meeting_completed_at': flow.now(), 'meeting_notes': text(body.get('notes'), 'meeting notes')}, 'meeting.completed')
        await process.hr_notice(db, saved, 'release-needed', 'Release the completed review within 48 hours')
    else: flow.fail('Unknown meeting action')
    return process.projection(saved, user, employee)


async def correct_actuals(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'expected_version', 'actuals', 'reason'})
    row, employee = await process.record(db, user, reference); version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('Another HR approver must correct your review', 403)
    if row['status'] not in {'Manager_Submitted', 'HR_Reviewed'} or row.get('meeting_completed_at') or row.get('released_at'): flow.fail('Completed meetings and released reviews cannot be rescored', 409)
    reason = text(body.get('reason'), 'HR correction reason')
    if len(reason) < 10: flow.fail('Explain the correction in at least ten characters')
    result = scoring.section_a(row['section_a_kpis'], body.get('actuals', {}), row.get('group_weights'))
    assessment = deepcopy(row['manager_assessment'])
    assessment['actuals'] = {identifier: {'actual': value, 'comment': reason, 'corrected_by_hr': True} for identifier, value in body['actuals'].items()}
    # Keep the original manager submission as history. Recompile before another
    # meeting can be scheduled; never retain an obsolete released result.
    history = row.get('actual_corrections', []) + [{'before': row['manager_assessment'], 'reason': reason, 'by': user['id'], 'at': flow.now()}]
    saved = await process.save(db, user, row, {'manager_assessment': assessment, 'actual_corrections': history,
        'section_a_score': result['score'], 'section_a_kpi_scores': result['kpi_scores'], 'status': 'Manager_Submitted',
        'review_meeting': None, 'meeting_proposal': None, 'peer_summary': None, 'overall_score': None,
        'section_b_score': None, 'section_c_score': None, 'rating': None, 'nine_box_placement': None}, 'actuals.corrected')
    await process.notice(db, saved, 'actual-correction:' + saved['version'], 'employee', row['line_manager_id'], 'HR corrected assessment actuals; review the updated assessment')
    return process.projection(saved, user, employee)


async def release(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'expected_version', 'late_reason'})
    row, employee = await process.record(db, user, reference); version(row, body.get('expected_version'))
    if user.get('employee_id') in process.reference_ids(employee): flow.fail('You cannot release your own review', 403)
    if row['status'] != 'HR_Reviewed' or not row.get('meeting_completed_at') or row.get('released_at'): flow.fail('Complete the meeting before releasing the review', 409)
    if process.instant() > datetime.fromisoformat(row['meeting_completed_at']) + timedelta(hours=48):
        if len(text(body.get('late_reason'), 'late release reason')) < 10: flow.fail('Explain the late release in at least ten characters')
    due = process.today(); units = 0
    from utils.leave_policy import contract_policy, working_units
    policy = await contract_policy(db, employee)
    holidays = await db.public_holidays.find(process.tenant_query(process.tenant_of(user))).to_list(None)
    holiday_dates = {h.get('date') for h in holidays}
    while units < 5:
        due += timedelta(days=1)
        units += working_units(due.isoformat(), due.isoformat(), holiday_dates, policy.get('saturday_weight', .5), policy.get('workday_weights'))
        if due > process.today() + timedelta(days=60): flow.fail('Working schedule needs HR correction', 409)
    previous_type = 'Mid_Year' if row['cycle_type'] == 'Year_End' else 'Year_End'
    previous_year = row['cycle_year'] if row['cycle_type'] == 'Year_End' else row['cycle_year'] - 1
    previous = await db.performance_reviews.find(process.scoped(user, {'employee_id': {'$in': process.reference_ids(employee)},
        'cycle_type': previous_type, 'cycle_year': previous_year, 'released_at': {'$exists': True}, 'released_by': {'$exists': True}, 'workflow_version': 3})).sort('released_at', -1).to_list(1)
    pip = row['overall_score'] >= 2.5 or (row['overall_score'] >= 2 and bool(previous) and previous[0].get('overall_score', 0) >= 2)
    placement = row['nine_box_placement']; outcomes = []
    titles = {'Stars': 'Agree project ownership, mentoring and recognition', 'Core_Contributor': 'Refresh the individual development plan',
              'Realignment_Needed': 'Hold HR and manager realignment discussion', 'Culture_Risk': 'Hold values discussion and review bonus eligibility', 'Exit_Track': 'HR review and documented improvement plan'}
    outcomes.append({'key': 'development', 'title': titles[placement], 'due_on': (process.today() + timedelta(days=7)).isoformat(), 'status': 'Pending'})
    if pip or placement == 'Exit_Track':
        outcomes.extend({'key': f'pip-{days}', 'title': f'PIP {days}-day checkpoint', 'due_on': (process.today() + timedelta(days=days)).isoformat(), 'status': 'Pending'} for days in (30, 60))
    saved = await process.save(db, user, row, {'status': 'Completed', 'released_at': flow.now(), 'released_by': user['id'], 'ack_due_on': due.isoformat(),
        'late_release_reason': body.get('late_reason', ''), 'outcomes': outcomes,
        'compensation_handoff': {'final_score': row['overall_score'], 'company_scorecard_required': 80, 'values_hold': placement == 'Culture_Risk', 'status': 'Pending_Finance_Review'}}, 'released')
    await process.notice(db, saved, 'released', 'employee', row['employee_id'], 'Your performance review is released; please acknowledge it')
    await process.hr_notice(db, saved, 'outcomes', 'Track the released review follow-up actions')
    return process.projection(saved, user, employee)


async def acknowledge(db, user, reference, body):
    process.fields(body, {'expected_version', 'confirmed', 'dispute'})
    row, employee = await process.record(db, user, reference); version(row, body.get('expected_version'))
    personal_grant(user, 'M05', write=True)
    if user.get('employee_id') not in process.reference_ids(employee): flow.fail('Only the employee may acknowledge or dispute this review', 403)
    if not flow.released(row): flow.fail('HR has not released this review', 409)
    update = {}
    if body.get('dispute'):
        update = {'dispute': {'statement': text(body['dispute'], 'written dispute'), 'submitted_at': flow.now(), 'status': 'Pending_HR'}}
        if row.get('dispute'): flow.fail('HR already has your dispute', 409)
    elif body.get('confirmed') is True and not row.get('acknowledged_at'): update = {'acknowledged_at': flow.now()}
    else: flow.fail('Confirm acknowledgement or provide a written dispute')
    saved = await process.save(db, user, row, update, 'disputed' if 'dispute' in update else 'acknowledged')
    if 'dispute' in update: await process.hr_notice(db, saved, 'dispute', 'Employee submitted a written performance review dispute')
    return process.projection(saved, user, employee)
