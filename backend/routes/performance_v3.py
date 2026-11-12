from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from database import get_db
from utils.auth import get_current_user
from utils.employee_integrity import integrity_write
from utils import performance_v3 as process, performance_v3_reviews as reviews
from utils import performance_v3_admin as admin, performance_v3_peers as peers, performance_v3_alignment as alignment

router = APIRouter(prefix='/v3', tags=['performance'])


@router.get('/setup')
async def setup(request: Request):
    return await admin.dashboard(get_db(), await get_current_user(request))


@router.get('/learning')
async def learning(request: Request):
    user = await get_current_user(request); db = get_db()
    from routes.surveys import FTE_ALIGNMENT_QUESTIONS
    from utils.performance_v3_scoring import VALUES, QUESTIONS
    team_cycles = []
    from utils.employee_access import personal_grant
    grant = personal_grant(user, 'M05')
    if grant.get('scope') in {'own_team', 'own_reports'} or user.get('role') in {'line_manager', 'general_manager', 'it_admin'}:
        team_rows = await db.performance_reviews.find(process.scoped(user, {'workflow_version': 3, 'line_manager_id': {'$in': process.user_employee_aliases(user)}})).to_list(None)
        for identifier in sorted({r['cycle_id'] for r in team_rows}):
            cycle = await process.cycle(db, user, identifier)
            team_cycles.append({'id': cycle['id'], 'title': f"{cycle['cycle_type']} {cycle['cycle_year']}"})
    return {'peers': await peers.listing(db, user), 'alignment': await alignment.windows(db, user), 'team_cycles': team_cycles, 'questions': FTE_ALIGNMENT_QUESTIONS, 'values': VALUES, 'peer_questions': QUESTIONS}


@router.get('/evidence')
async def evidence(request: Request):
    return await process.evidence_options(get_db(), await get_current_user(request))


@router.get('/cycles/{reference}/alignment')
async def alignment_report(reference: str, request: Request):
    return await alignment.report(get_db(), await get_current_user(request), reference)


@router.post('/{kind}/{reference}/{action}')
async def mutate(kind: str, reference: str, action: str, request: Request, background_tasks: BackgroundTasks):
    user = await get_current_user(request); db = get_db(); body = await request.json()
    if not isinstance(body, dict): raise HTTPException(422, 'An object body is required')
    async with integrity_write(db):
        if kind == 'employees' and action == 'assign': result = await process.assign(db, user, reference, body)
        elif kind == 'cycles' and action == 'create': result = await process.create_cycle(db, user, body)
        elif kind == 'cycles' and action == 'open':
            process.fields(body, {'employee_ids'}); result = await process.open_cycle(db, user, reference, body.get('employee_ids'))
        elif kind == 'cycles' and action == 'archive': result = await process.archive(db, user, reference, body)
        elif kind == 'cycles' and action == 'feedback': result = await admin.company_feedback(db, user, reference, body)
        elif kind == 'cycles' and action == 'alignment':
            process.fields(body, {'answers'}); result = await alignment.submit(db, user, reference, body.get('answers'))
        elif kind == 'peers' and action == 'submit': result = await peers.submit(db, user, reference, body)
        elif kind == 'reviews' and action == 'peers': result = await admin.peers(db, user, reference, body)
        elif kind == 'reviews' and action == 'self': result = await reviews.self_assessment(db, user, reference, body)
        elif kind == 'reviews' and action == 'manager': result = await reviews.manager_assessment(db, user, reference, body)
        elif kind == 'reviews' and action == 'compile': result = await reviews.compile_review(db, user, reference, body)
        elif kind == 'reviews' and action == 'correct': result = await reviews.correct_actuals(db, user, reference, body)
        elif kind == 'reviews' and action in {'propose', 'schedule', 'complete'}: result = await reviews.meeting(db, user, reference, body, action)
        elif kind == 'reviews' and action == 'release': result = await reviews.release(db, user, reference, body)
        elif kind == 'reviews' and action == 'acknowledge': result = await reviews.acknowledge(db, user, reference, body)
        elif kind == 'reviews' and action == 'followup': result = await admin.followup(db, user, reference, body)
        elif kind == 'reviews' and action == 'resolve-dispute': result = await admin.resolve_dispute(db, user, reference, body)
        else: raise HTTPException(404, 'Unknown performance action')
    from utils.performance_v3_reminders import deliver
    background_tasks.add_task(deliver, db, process.tenant_of(user))
    return result
