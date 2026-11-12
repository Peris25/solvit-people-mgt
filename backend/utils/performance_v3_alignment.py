"""Reuse survey windows/responses; V3 answers have no employee identity fields."""
from datetime import date
from pymongo.errors import DuplicateKeyError
from utils import performance_v3 as process, performance_workflows as flow
from utils.employee_access import personal_grant


async def windows(db, user):
    grant = personal_grant(user, 'M05')
    employee = await process.self_employee(db, user)
    reviews = await db.performance_reviews.find(process.scoped(user, {'employee_id': {'$in': process.reference_ids(employee)}, 'workflow_version': 3})).to_list(None)
    result = []
    for review in reviews:
        window = await process.cycle(db, user, review['cycle_id'])
        identity = process.key('alignment-answer', process.tenant_of(user), window['id'], process.employee_key(employee))
        submitted = bool(await db.survey_responses.find_one({'_id': identity}))
        result.append({'id': window['id'], 'title': f"{window['cycle_type']} {window['cycle_year']}", 'starts_on': window['starts_on'], 'due_on': window['self_due_on'], 'submitted': submitted})
    return result


async def submit(db, user, reference, answers):
    personal_grant(user, 'M05', write=True)
    employee = await process.self_employee(db, user)
    if not process.enabled(employee): flow.fail('Not eligible to submit', 403)
    window = await process.cycle(db, user, reference)
    participation = await db.performance_reviews.find_one(process.scoped(user, {'employee_id': {'$in': process.reference_ids(employee)}, 'cycle_id': window['id'], 'workflow_version': 3}))
    if not participation: flow.fail('You are not included in this cycle', 403)
    if window.get('status') != 'Open' or not date.fromisoformat(window['starts_on']) <= process.today() <= date.fromisoformat(window['self_due_on']): flow.fail('Alignment collection is closed', 409)
    from routes.surveys import FTE_ALIGNMENT_QUESTIONS, calc_pillar_score
    if not isinstance(answers, dict) or set(answers) != {q['id'] for q in FTE_ALIGNMENT_QUESTIONS} or any(type(v) is not int or not 1 <= v <= 5 for v in answers.values()): flow.fail('Answer all twelve questions from 1 to 5')
    pillars = [calc_pillar_score(answers, FTE_ALIGNMENT_QUESTIONS, p) for p in (1, 2, 3)]
    identity = process.key('alignment-answer', process.tenant_of(user), window['id'], process.employee_key(employee))
    try:
        await db.survey_responses.insert_one({'_id': identity, 'tenant_id': process.tenant_of(user), 'performance_workflow_version': 3,
            'survey_window_id': window['alignment_window_id'], 'cycle_id': window['id'], 'respondent_type': 'FTE',
            'line_manager_id': participation['line_manager_id'], 'responses_json': answers,
            'pillar_1_score': pillars[0], 'pillar_2_score': pillars[1], 'pillar_3_score': pillars[2], 'overall_alignment_score': round(sum(pillars) / 3, 2)})
    except DuplicateKeyError: flow.fail('Your Alignment Survey was already submitted', 409)
    await flow.audit(db, user, 'performance.v3.alignment.completed', {'id': window['id']})
    return {'status': 'Submitted'}


async def report(db, user, reference):
    grant = personal_grant(user, 'M05')
    window = await process.cycle(db, user, reference)
    if window.get('workflow_version') != 3: flow.fail('Choose a V3 cycle', 409)
    if process.today() <= date.fromisoformat(window['self_due_on']): flow.fail('Results are unavailable while the survey is open', 409)
    hr = user.get('role') in flow.HR
    if not hr and grant.get('scope') not in {'own_team', 'own_reports'} and user.get('role') not in {'line_manager', 'general_manager', 'it_admin'}:
        flow.fail('Manager or HR reporting permission required', 403)
    query = {'cycle_id': window['id'], 'performance_workflow_version': 3}
    if not hr:
        employee = await process.self_employee(db, user)
        query['line_manager_id'] = {'$in': process.reference_ids(employee)}
    rows = await db.survey_responses.find(process.scoped(user, query)).to_list(None)
    if len(rows) < 3: return {'response_count': len(rows), 'score': None, 'message': 'At least three responses are required'}
    result = {'response_count': len(rows), 'score': round(sum(r['overall_alignment_score'] for r in rows) / len(rows), 2)}
    if hr:
        all_reviews = await db.performance_reviews.find(process.scoped(user, {'cycle_id': window['id'], 'workflow_version': 3, 'status': {'$nin': ['Archived', 'Cancelled']}})).to_list(None)
        reviews = [r for r in all_reviews if flow.released(r)]
        workforce = await db.employees.find(process.tenant_query(process.tenant_of(user))).to_list(None)
        expected = {process.employee_key(e) for e in workforce if process.enabled(e) and process.fte(e) and not process.md(e)}
        covered = {r['employee_id'] for r in reviews}
        if reviews and len(reviews) == len(all_reviews) and expected <= covered:
            primary = sum(r.get('nine_box_placement') in {'Stars', 'Core_Contributor'} for r in reviews) / len(reviews) * 100
            values = sum((3 - r['section_b_score']) / 2 * 100 for r in reviews) / len(reviews)
            result['talent_density'] = round(primary * .5 + values * .3 + result['score'] * .2, 2)
            result['target'] = 85
            result['components'] = {'primary_stars_core_pct': round(primary, 2), 'secondary_values_avg_pct': round(values, 2), 'alignment_survey_pct': result['score']}
        else: result['message'] = 'Company talent density awaits released reviews for all eligible staff'
    return result
