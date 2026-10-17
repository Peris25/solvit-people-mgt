"""Versioned FORM-02 assignments in the existing form store. No seeded policy.

All writes hold the existing integrity lock. Publication is fail-closed until
audit and inbox events are recorded. Historical forms and Solver scores stay put.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from decimal import Decimal
import random
import re
import uuid
from fastapi import HTTPException
from bson import ObjectId
from utils.access_matrix import get_module_access
from utils.employee_integrity import tenant_of, tenant_query, resolve_user_employee
from utils.employee_access import find_linked_record
from utils.solver_access import HR_ROLES, find_solver, own_solver, solver_key, solver_aliases, audit_solver, authorize_solver
from utils.solver_workflows import view, now, evidence_document

KIND = 'solver_assessment_v1'
TITLES = {'technicalmanager', 'technicalservicesmanager', 'technicalservicesgrowthmanager',
          'principalvaluer', 'solversmanager', 'operationscoordinator', 'operationscoordinatorheadofsolvers'}
TECHNICAL = {'technicalmanager', 'technicalservicesmanager', 'technicalservicesgrowthmanager'}


def fail(message, status=422):
    raise HTTPException(status, message)


def text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        fail(f'Provide valid {name} within {maximum} characters')
    return value.strip()


def number(value, name, low=0, high=100):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        fail(f'Invalid {name}')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        fail('Identifiers must contain only letters, digits, underscores or hyphens')
    return value


def stamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None: fail('Assessment timestamps must include a timezone')
        return result.astimezone(timezone.utc)
    except (AttributeError, ValueError, TypeError):
        fail('Invalid assessment timestamp')


def module(user, name):
    entry = get_module_access(name, user.get('role'))
    if not entry or entry.get('level') not in {'Read', 'Manage', 'Full'}:
        fail('No access to Solver assessment operations', 403)
    return entry


def hr(user):
    if user.get('role') not in HR_ROLES:
        fail('This action requires authorized HR', 403)
    for name in ('M02', 'M03'):
        entry = module(user, name)
        if entry.get('scope') is not None or entry.get('level') not in {'Manage', 'Full'}:
            fail('Unrestricted HR assessment administration is required', 403)


async def assessor(db, user, technical=False):
    if user.get('role') not in HR_ROLES.union({'line_manager'}): fail('An assigned assessor account is required', 403)
    if user.get('role') in HR_ROLES: hr(user)
    entry=module(user, 'M03')
    if entry.get('scope') not in (None,'own_dept_pipeline','assigned_candidates','contextual'):
        fail('This module scope does not permit assigned assessments',403)
    employee = await resolve_user_employee(db, user)
    from utils.staff_directory import normalized, visible_state
    if not employee or not visible_state(employee) or normalized(employee.get('role_title')) not in (TECHNICAL if technical else TITLES):
        fail('The saved employee role is not an eligible assessor', 403)
    return employee


async def configurator(db, user, publish=False):
    if user.get('role') in HR_ROLES:
        hr(user)
    elif publish:
        fail('Only HR may publish approved scoring policy', 403)
    else:
        await assessor(db, user, technical=True)


def validate_configuration(body, publishing=False):
    fields = {'title', 'approval_reference', 'sections', 'time_limits', 'pass_mark', 'resit_wait_days',
              'eligibility', 'borderline', 'certification_categories'}
    if not isinstance(body, dict) or set(body) - fields: fail('Unknown assessment configuration fields')
    out = deepcopy(body)
    out['title'] = text(out.get('title'), 'assessment title', 200)
    if out.get('approval_reference') is not None:
        out['approval_reference'] = text(out['approval_reference'], 'approval reference', 500)
    sections = out.get('sections', [])
    if not isinstance(sections, list) or len(sections) > 30: fail('Invalid assessment sections')
    seen = set(); section_ids = set(); parts = set()
    for section in sections:
        if not isinstance(section, dict) or set(section) - {'id','title','part','weight','questions'}: fail('Invalid section fields')
        sid = identifier(section.get('id'))
        if sid in section_ids: fail('Duplicate section identifier')
        section_ids.add(sid)
        section['title'] = text(section.get('title'), 'section title', 200)
        if not isinstance(section.get('part'),str) or section['part'] not in {'A', 'B'}: fail('Sections must belong to Part A or B')
        parts.add(section['part'])
        if section.get('weight') is not None: number(section['weight'], 'section weight', 0.0001)
        questions = section.get('questions', [])
        if not isinstance(questions, list) or len(questions) > 100: fail('Invalid question list')
        for question in questions:
            allowed = {'id','label','type','scoring','points','required','options','correct_answer','rubric','competency','tolerance_bands'}
            if not isinstance(question, dict) or set(question) - allowed: fail('Unknown question fields')
            qid = identifier(question.get('id'))
            if qid in seen: fail('Question identifiers must be unique across both parts')
            seen.add(qid)
            question['label'] = text(question.get('label'), 'question', 6000)
            if not isinstance(question.get('type'),str) or question['type'] not in {'choice','text','number','document'}: fail('Unsupported question type')
            if not isinstance(question.get('scoring'),str) or question['scoring'] not in {'auto','manual','none'}: fail('Choose auto, manual or unscored')
            if not isinstance(question.get('required'), bool): fail('Question required status must be explicit')
            if question.get('competency') is not None: question['competency'] = text(question['competency'], 'competency label', 200)
            if question['type'] == 'choice':
                options = question.get('options')
                if not isinstance(options, list) or not 2 <= len(options) <= 30: fail('Choice questions require approved options')
                question['options'] = [text(value, 'option', 2000) for value in options]
                if len(set(question['options'])) != len(options): fail('Duplicate question options')
            if question['scoring'] != 'none': number(question.get('points'), 'question points', 0.0001, 10000)
            elif question.get('points') not in (None, 0): fail('Unscored questions cannot carry points')
            if question['scoring'] == 'manual': question['rubric'] = text(question.get('rubric'), 'approved rubric', 6000)
            if question['scoring'] == 'auto':
                if question['type'] == 'choice':
                    if question.get('correct_answer') not in question['options']: fail('The answer key must match an approved option')
                elif question['type'] == 'number':
                    number(question.get('correct_answer'), 'numeric reference', -1e15, 1e15)
                    bands = question.get('tolerance_bands', [])
                    if not isinstance(bands, list) or len(bands) > 20: fail('Invalid tolerance bands')
                    previous = -1
                    for band in bands:
                        if not isinstance(band, dict) or set(band) != {'max_difference','points'}: fail('Invalid tolerance band')
                        limit = number(band['max_difference'], 'tolerance', 0, 1e15)
                        number(band['points'], 'band points', 0, question['points'])
                        if limit <= previous: fail('Tolerance bands must be strictly increasing')
                        previous = limit
                else: fail('Only choice and numeric questions can be automatically scored')
        if publishing and (not questions or not sum(q.get('points', 0) or 0 for q in questions if q['scoring'] != 'none')):
            fail('Each published section requires scored approved questions')
    if len(seen) > 200: fail('An assessment may contain at most 200 questions')
    for key in ('pass_mark', 'resit_wait_days'):
        if out.get(key) is not None: number(out[key], key, 0, 365 if key == 'resit_wait_days' else 100)
    limits = out.get('time_limits') or {}
    if not isinstance(limits, dict) or set(limits) - {'A', 'B'}: fail('Invalid part time limits')
    for value in limits.values(): number(value, 'part time limit in minutes', 0.01, 1440)
    eligibility = out.get('eligibility') or {}
    if not isinstance(eligibility, dict) or set(eligibility) - {'states','regions'}: fail('Unsupported eligibility rule')
    for key, values in eligibility.items():
        if not isinstance(values, list) or not values or len(values) > 100: fail('Eligibility values must be a non-empty list')
        eligibility[key] = [text(value, 'eligibility value', 100) for value in values]
        if key == 'states' and any(value not in {'Active','Registering'} for value in values): fail('Only active/registering Solvers can be assigned')
    if out.get('borderline') is not None:
        band = out['borderline']
        if not isinstance(band, dict) or set(band) != {'minimum','maximum'}: fail('Invalid borderline range')
        number(band['minimum'], 'borderline minimum'); number(band['maximum'], 'borderline maximum')
        if band['minimum'] > band['maximum']: fail('Invalid borderline range')
    categories = out.get('certification_categories', [])
    from routes.solvers import VEHICLE_CATEGORIES
    if not isinstance(categories, list) or any(value not in VEHICLE_CATEGORIES for value in categories): fail('Use documented vehicle certification categories')
    if publishing:
        if parts != {'A','B'} or not out.get('approval_reference'): fail('Publish requires approved Part A and B content and an approval reference')
        if any(section.get('weight') is None for section in sections) or sum(Decimal(str(section['weight'])) for section in sections) != Decimal(100):
            fail('Approved section weights must total 100')
        if set(limits) != {'A','B'} or out.get('pass_mark') is None or out.get('resit_wait_days') is None or not eligibility.get('states'):
            fail('Set approved timers, pass mark, re-sit wait and lifecycle eligibility before publishing')
    return out


async def configurations(db, user):
    await configurator(db, user)
    rows = await db.solver_assessment_settings.find(tenant_query(tenant_of(user))).to_list(None)
    await audit_solver(db,user,'solver.assessment.configuration.viewed',fields=['settings'])
    return [{key: value for key,value in row.items() if key != '_id'} for row in sorted(rows, key=lambda r: (r['title'], -r['version']))]


async def capabilities(db,user):
    if user.get('role') in HR_ROLES:
        hr(user)
        return {'can_configure':True,'can_publish':True,'can_assign':True,'is_solver':False}
    if user.get('role')=='solver':
        await authorize_solver(db,user,solver_key(await own_solver(db,user)))
        return {'can_configure':False,'can_publish':False,'can_assign':False,'is_solver':True}
    await assessor(db,user)
    can_configure=False
    try:
        await assessor(db,user,technical=True);can_configure=True
    except HTTPException as error:
        if error.status_code!=403: raise
    return {'can_configure':can_configure,'can_publish':False,'can_assign':False,'is_solver':False}


async def administration_options(db,user):
    hr(user)
    output=[]
    for owner in await db.users.find(tenant_query(tenant_of(user))).to_list(None):
        if owner.get('is_active') is False or owner.get('role') not in HR_ROLES.union({'line_manager'}): continue
        key=str(owner['_id'])
        try: await assigned_account(db,user,key)
        except HTTPException as error:
            if error.status_code in (403,409):continue
            raise
        technical=False
        try: await assigned_account(db,user,key,technical=True);technical=True
        except HTTPException as error:
            if error.status_code not in (403,409):raise
        output.append({'id':key,'name':owner.get('full_name') or 'Authorized assessor','technical_reviewer':technical})
    return {'assessors':output}


async def save_configuration(db, user, body, previous=None):
    await configurator(db, user)
    settings = validate_configuration(body)
    old = await find_linked_record(db.solver_assessment_settings, previous, user) if previous else None
    if old and old.get('publication_state')!='Ready': fail('Recover the previous configuration before creating a revision',409)
    bank = old['bank_id'] if old else str(uuid.uuid4())
    versions = await db.solver_assessment_settings.find({'tenant_id': tenant_of(user), 'bank_id': bank}).to_list(None)
    row = {'id':str(uuid.uuid4()), 'tenant_id':tenant_of(user), 'bank_id':bank,
           'version':max([r['version'] for r in versions] or [0])+1, 'settings':settings,
           'title':settings['title'], 'status':'Draft', 'publication_state':'Pending_Audit', 'created_at':now(), 'created_by':user['id']}
    await db.solver_assessment_settings.insert_one(row)
    await audit_solver(db,user,'solver.assessment.configuration.created',fields=['settings','version'],entity_type='solver_assessment_configuration',entity_id=row['id'])
    await db.solver_assessment_settings.update_one({'id':row['id']}, {'$set':{'publication_state':'Ready'}})
    return {**{key:value for key,value in row.items() if key!='_id'}, 'publication_state':'Ready'}


async def publish(db,user,reference):
    await configurator(db,user,publish=True)
    row = await find_linked_record(db.solver_assessment_settings, reference, user)
    if row.get('publication_state') != 'Ready' or row['status'] != 'Draft': fail('Only a ready draft can be published',409)
    validate_configuration(row['settings'], publishing=True)
    await db.solver_assessment_settings.update_one({'_id':row['_id']},{'$set':{'publication_state':'Pending_Audit'}})
    await audit_solver(db,user,'solver.assessment.configuration.published',fields=['settings','version'],entity_type='solver_assessment_configuration',entity_id=row['id'])
    await db.solver_assessment_settings.update_one({'_id':row['_id']},{'$set':{'status':'Published','publication_state':'Ready','published_at':now(),'published_by':user['id']}})
    return {'published':True,'id':row['id']}


async def assigned_account(db,user,reference,technical=False):
    owner = await find_linked_record(db.users, reference, user)
    if owner.get('is_active') is False: fail('Assessor account is inactive',409)
    subject = {**owner,'id':str(owner['_id'])}
    await assessor(db,subject,technical)
    return str(owner['_id'])


async def load(db,user,reference):
    row = await find_linked_record(db.form_submissions,reference,user)
    if row.get('workflow_kind') != KIND: fail('Assessment not found',404)
    record = await find_solver(db,row['subject_solver_id'],user)
    if user.get('role') in HR_ROLES:
        hr(user)
    elif user.get('role') == 'solver':
        await authorize_solver(db,user,solver_key(record))
    else:
        await assessor(db,user)
        if user['id'] not in {row['assessor_id'],row.get('reviewer_id')}: fail('Assessment is assigned to another assessor',403)
    return row,record


def questions(row,part=None):
    return [q for section in row['configuration']['sections'] if part is None or section['part']==part for q in section['questions']]


def projection(row,user):
    own = user.get('role') == 'solver'
    ready = row.get('publication_state') == 'Ready'
    out = {key:deepcopy(row.get(key)) for key in ('id','title','status','due_at','parts','revision','submitted_at','released_at','configuration_id','configuration_version','subject_solver_id')}
    out['status'] = out['status'] if ready else 'Needs administrator review'
    out['can_release'] = not own and user.get('role') in HR_ROLES and ready and row['status']=='Scored' and (not row.get('second_review_required') or bool(row.get('second_review')))
    out['can_score'] = not own and ready and row['status']=='AwaitingScoring' and user['id']==row['assessor_id']
    out['can_review'] = not own and ready and row['status']=='Scored' and user['id']==row.get('reviewer_id') and row.get('second_review_required') and not row.get('second_review')
    out['configuration'] = deepcopy(row['configuration'])
    if own:
        out['configuration'] = {'sections':out['configuration']['sections'],'time_limits':out['configuration']['time_limits']}
        for section in out['configuration']['sections']:
            if section['part'] not in row['parts']:
                section['question_count']=len(section['questions'])
                section['questions']=[]
            for q in section['questions']:
                for field in ('correct_answer','rubric','tolerance_bands'): q.pop(field,None)
    out['answers'] = deepcopy(row.get('answers') or {})
    if not own or ready and row['status']=='Released':
        out.update({key:deepcopy(row.get(key)) for key in ('score','section_scores','outcome')})
    if not own:
        out.update({key:deepcopy(row.get(key)) for key in ('assessor_id','reviewer_id','marks','assessor_notes','second_review_required','second_review')})
    return out


async def notify(db,row,event):
    recipients=[('role','hr_admin'),('role','hr_manager'),('solver',row['subject_solver_id']),('account',row['assessor_id'])]
    if row.get('reviewer_id'): recipients.append(('account',row['reviewer_id']))
    for kind,recipient in set(recipients):
        key=f"solver-assessment:{tenant_of(row)}:{row['id']}:{event}:{row['revision']}:{kind}:{recipient}"
        await db.notifications.update_one({'_id':key},{'$setOnInsert':{'id':key,'tenant_id':tenant_of(row),
            **({'recipient_role':recipient} if kind=='role' else {'recipient_type':kind,'recipient_id':recipient}),
            'category':'System','is_read':False,'created_at':now(),'data':{'solver_assessment_id':row['id']}}},upsert=True)


async def persist(db,user,row,changes,event,send=True):
    revision=row['revision']+1
    pending={**changes,'revision':revision,'publication_state':'Pending_Audit','updated_at':now()}
    result=await db.form_submissions.update_one({'_id':row['_id'],'revision':row['revision'],'publication_state':'Ready'},{'$set':pending})
    if result.modified_count!=1: fail('Assessment changed; reload before retrying',409)
    changed={**row,**pending}
    await audit_solver(db,user,'solver.assessment.'+event,fields=list(changes),entity_type='solver_assessment',entity_id=row['id'])
    if send: await notify(db,changed,event)
    await db.form_submissions.update_one({'_id':row['_id'],'revision':revision},{'$set':{'publication_state':'Ready'}})
    changed['publication_state']='Ready'
    return projection(changed,user)


async def assign(db,user,body):
    hr(user)
    allowed={'configuration_id','solver_id','assessor_id','reviewer_id','due_at','interview_reference'}
    if not isinstance(body,dict) or set(body)-allowed: fail('Unknown assignment fields')
    config=await find_linked_record(db.solver_assessment_settings,body.get('configuration_id'),user)
    if config['status']!='Published' or config.get('publication_state')!='Ready': fail('Choose a published assessment',409)
    settings=validate_configuration(config['settings'],publishing=True)
    record=await find_solver(db,body.get('solver_id'),user)
    saved=view(record); rules=settings['eligibility']
    if saved['lifecycle_state'] not in rules['states'] or (rules.get('regions') and str(saved.get('region') or '').casefold() not in {r.casefold() for r in rules['regions']}):
        fail('Solver does not meet the approved eligibility rules',409)
    deadline=stamp(body.get('due_at'))
    if deadline<=datetime.now(timezone.utc): fail('The assessment deadline must be in the future')
    reference=text(body.get('interview_reference'),'passed-interview verification reference',500)
    owner=await assigned_account(db,user,body.get('assessor_id'))
    reviewer=await assigned_account(db,user,body['reviewer_id'],technical=True) if body.get('reviewer_id') else None
    if reviewer==owner: fail('The second reviewer must be a different account')
    if settings.get('borderline') is not None and not reviewer: fail('Assign a Technical Manager for the configured borderline review')
    previous=await db.form_submissions.find({'$and':[tenant_query(tenant_of(user)),{'workflow_kind':KIND,'subject_solver_id':{'$in':solver_aliases(record)},'bank_id':config['bank_id']}]}).to_list(None)
    for old in previous:
        if old.get('publication_state')!='Ready' or old['status']!='Released': fail('An assessment in this bank is already pending',409)
        if old.get('outcome')=='Pass' and old['configuration_id']==config['id']: fail('This assessment version is already passed',409)
        if old.get('outcome')=='Fail' and datetime.now(timezone.utc)<stamp(old['released_at'])+timedelta(days=old['configuration']['resit_wait_days']):
            fail('The approved re-sit waiting period has not elapsed',409)
    for section in settings['sections']: random.SystemRandom().shuffle(section['questions'])
    row={'id':str(uuid.uuid4()),'tenant_id':tenant_of(user),'form_id':'form-02','workflow_kind':KIND,
         'title':settings['title'],'form_title':settings['title'],'subject_solver_id':solver_key(record),
         'configuration':settings,'configuration_id':config['id'],'configuration_version':config['version'],'bank_id':config['bank_id'],
         'status':'Assigned','publication_state':'Pending_Audit','revision':0,'answers':{},'parts':{},
         'assessor_id':owner,'reviewer_id':reviewer,'due_at':deadline.isoformat(),'interview_reference':reference,
         'assigned_by':user['id'],'created_at':now()}
    result=await db.form_submissions.insert_one(row);row['_id']=result.inserted_id
    await audit_solver(db,user,'solver.assessment.assigned',[record],['configuration_id','assessor_id'],entity_type='solver_assessment',entity_id=row['id'])
    await notify(db,row,'assigned')
    await db.form_submissions.update_one({'_id':row['_id']},{'$set':{'publication_state':'Ready'}})
    return projection({**row,'publication_state':'Ready'},user)


async def listing(db,user):
    if user.get('role') in HR_ROLES: hr(user)
    elif user.get('role')=='solver': await authorize_solver(db,user,solver_key(await own_solver(db,user)))
    else: await assessor(db,user)
    rows=await db.form_submissions.find({'$and':[tenant_query(tenant_of(user)),{'workflow_kind':KIND}]}).to_list(None)
    output=[]
    for row in sorted(rows,key=lambda r:r.get('created_at',''),reverse=True):
        try: authorized,_=await load(db,user,row['id'])
        except HTTPException as error:
            if error.status_code in (403,404): continue
            raise
        output.append(projection(authorized,user))
    await audit_solver(db,user,'solver.assessment.list.viewed',fields=['attempts'])
    return output


def mutable(row,body):
    if row.get('publication_state')!='Ready': fail('Assessment requires administrator recovery',409)
    if not isinstance(body,dict) or type(body.get('revision')) is not int or body.get('revision')!=row['revision']:
        fail('Assessment changed; reload before retrying',409)


def expired(row,part):
    started=stamp(row['parts'][part]['started_at'])
    return datetime.now(timezone.utc)>=min(stamp(row['due_at']),started+timedelta(minutes=row['configuration']['time_limits'][part]))


async def progress(db,user,reference,part,action,body):
    row,record=await load(db,user,reference); mutable(row,body)
    if user.get('role')!='solver': fail('Only the assigned Solver can answer or submit',403)
    if set(body)-{'revision','answers'}: fail('Only answers and the current revision may be supplied')
    if part not in {'A','B'} or action not in {'start','save','submit'}: fail('Invalid assessment component')
    if row['status'] not in {'Assigned','InProgress'}: fail('Answers are immutable after submission',409)
    parts=deepcopy(row['parts']); current=parts.get(part)
    if part=='B' and not parts.get('A',{}).get('submitted_at'): fail('Submit Part A before starting Part B',409)
    if action=='start':
        if current: return projection(row,user)
        if datetime.now(timezone.utc)>=stamp(row['due_at']): fail('The assessment deadline has passed',409)
        parts[part]={'started_at':now()}
        return await persist(db,user,row,{'parts':parts,'status':'InProgress'},'part_started',send=False)
    if not current or current.get('submitted_at'): fail('Start an unsubmitted component first',409)
    answers=deepcopy(row['answers']); incoming=body.get('answers',{})
    if not isinstance(incoming,dict): fail('Answers must be an object')
    if expired(row,part) and (action=='save' or incoming): fail('This component timer expired; submit saved answers only',409)
    available={q['id']:q for q in questions(row,part)}
    if set(incoming)-set(available): fail('Answers contain an unknown or other-part question')
    for key,value in incoming.items():
        q=available[key]
        if value is None:
            answers.pop(key,None)
            continue
        if q['type']=='number': number(value,'numeric answer',-1e15,1e15)
        elif q['type']=='choice':
            if value not in q['options']: fail('Choose an available answer')
        elif q['type']=='document':
            doc=await evidence_document(db,user,record,text(value,'document reference',200))
            if doc.get('visibility')!='hr_assessment' or doc.get('confidential') is not False:
                fail('HR must explicitly share this evidence with the assessment before submission',403)
        else: text(value,'answer',10000)
        answers[key]=value
    if action=='submit':
        if not expired(row,part) and any(q['required'] and q['id'] not in answers for q in available.values()): fail('Complete required answers before submission')
        parts[part]['submitted_at']=now();parts[part]['timed_out']=expired(row,part)
    complete=all(parts.get(name,{}).get('submitted_at') for name in ('A','B'))
    changes={'parts':parts,'answers':answers,'status':'AwaitingScoring' if complete else 'InProgress'}
    if complete: changes['submitted_at']=now()
    return await persist(db,user,row,changes,'submitted' if complete else 'progress_saved',send=action=='submit')


def score(row,marks):
    dec=lambda value:Decimal(str(value))
    manual={q['id']:q for q in questions(row) if q['scoring']=='manual'}
    if not isinstance(marks,dict) or set(marks)!=set(manual): fail('Provide marks for every manual question and no automatic questions')
    for key,q in manual.items():
        number(marks[key],'manual mark',0,q['points'])
        if q['id'] not in row['answers'] and marks[key]!=0: fail('An unanswered question cannot receive manual marks')
    scores=[];total=Decimal(0)
    for section in row['configuration']['sections']:
        points=Decimal(0);maximum=Decimal(0)
        for q in section['questions']:
            if q['scoring']=='none':continue
            maximum+=dec(q['points']);answer=row['answers'].get(q['id'])
            if q['scoring']=='manual':points+=dec(marks[q['id']])
            elif answer is not None:
                if q['type']=='choice':points+=dec(q['points']) if answer==q['correct_answer'] else Decimal(0)
                else:
                    difference=abs(dec(answer)-dec(q['correct_answer']))
                    bands=q.get('tolerance_bands') or [{'max_difference':0,'points':q['points']}]
                    points+=next((dec(band['points']) for band in bands if difference<=dec(band['max_difference'])),Decimal(0))
        percentage=100*points/maximum
        scores.append({'id':section['id'],'title':section['title'],'part':section['part'],'points':float(points),'maximum':float(maximum),'percentage':float(percentage)})
        total+=percentage*dec(section['weight'])/100
    # No display rounding may turn a below-threshold result into a pass.
    return total,scores


async def decision(db,user,reference,action,body):
    row,_=await load(db,user,reference);mutable(row,body)
    if action=='score':
        if set(body)-{'revision','marks','notes'}: fail('Unknown scoring fields')
        if row['status']!='AwaitingScoring' or user['id']!=row['assessor_id'] or user.get('role')=='solver': fail('Only the assigned assessor may score submitted work',403)
        total,sections=score(row,body.get('marks'))
        band=row['configuration'].get('borderline'); needs_review=bool(band and Decimal(str(band['minimum']))<=total<=Decimal(str(band['maximum'])))
        return await persist(db,user,row,{'status':'Scored','marks':body['marks'],'score':float(total),'section_scores':sections,
            'outcome':'Pass' if total>=Decimal(str(row['configuration']['pass_mark'])) else 'Fail',
            'assessor_notes':text(body.get('notes'),'assessment notes'), 'scored_by':user['id'],'scored_at':now(), 'second_review_required':needs_review},'scored')
    if action=='review':
        if set(body)-{'revision','notes'}: fail('Unknown review fields')
        if row['status']!='Scored' or not row.get('second_review_required') or row.get('second_review') or user['id']!=row.get('reviewer_id') or user['id']==row.get('scored_by'):
            fail('Only the assigned second reviewer may confirm this borderline result',403)
        await assessor(db,user,technical=True)
        return await persist(db,user,row,{'second_review':{'by':user['id'],'at':now(),'notes':text(body.get('notes'),'review notes')}},'reviewed')
    if action=='release':
        hr(user)
        if set(body)!={'revision'}: fail('Only the current revision may be supplied')
        if row['status']!='Scored' or row.get('second_review_required') and not row.get('second_review'): fail('Complete assessment and required independent review before release',409)
        return await persist(db,user,row,{'status':'Released','released_at':now(),'released_by':user['id']},'released')
    fail('Unknown assessment action')


async def competencies(db,user,reference):
    record=await authorize_solver(db,user,reference)
    rows=await db.solver_competencies.find({'$and':[tenant_query(tenant_of(user)),{'solver_id':{'$in':solver_aliases(record)}}]}).to_list(None)
    rows.sort(key=lambda row:row.get('created_at',''),reverse=True)
    latest={}
    for row in rows:
        key=(row['kind'],row['name'])
        if key not in latest: latest[key]=row
    output=[]
    for row in latest.values():
        if row.get('publication_state')!='Ready':
            output.append({'id':row['id'],'kind':row['kind'],'name':row['name'],'status':'Needs administrator review'})
            continue
        item={key:row.get(key) for key in ('id','kind','name','status','assessment_id','created_at','expires_on')}
        if item['status']=='Verified' and item.get('expires_on') and item['expires_on']<datetime.now(timezone.utc).date().isoformat():item['status']='Expired'
        output.append(item)
    return {'items':output,'legacy_vehicle_categories':view(record)['vehicle_categories'],
            'legacy_notice':'Saved legacy categories are not newly verified certifications.',
            'can_manage':user.get('role') in HR_ROLES}


async def record_competency(db,user,reference,body):
    hr(user)
    record=await authorize_solver(db,user,reference,write=True)
    allowed={'kind','name','status','assessment_id','document_id','reference','expires_on'}
    if not isinstance(body,dict) or set(body)-allowed: fail('Unknown competency fields')
    kind=body.get('kind');state=body.get('status')
    if not isinstance(kind,str) or kind not in {'Competency','Qualification','Certification'}: fail('Invalid competency record kind')
    if not isinstance(state,str) or state not in {'Pending','Verified','Expired','Revoked'}: fail('Invalid competency verification status')
    name=text(body.get('name'),'documented competency or qualification',200)
    policy=text(body.get('reference'),'verification/policy reference',500)
    document=await evidence_document(db,user,record,body.get('document_id'))
    assessment=None
    if body.get('assessment_id'):
        assessment,subject=await load(db,user,body['assessment_id'])
        if subject['_id']!=record['_id']: fail('Assessment belongs to another Solver',403)
        if assessment['status']!='Released' or assessment.get('publication_state')!='Ready': fail('Use a released assessment result',409)
    if kind=='Certification':
        from routes.solvers import VEHICLE_CATEGORIES
        if name not in VEHICLE_CATEGORIES: fail('Choose a documented vehicle certification category')
        if state=='Verified' and (not assessment or assessment.get('outcome')!='Pass' or name not in assessment['configuration'].get('certification_categories',[])):
            fail('Certification needs a released pass, approved category rules and actual supporting evidence',409)
    elif kind=='Qualification' and name!='Driving licence':
        fail('Only the documented driving-licence qualification is currently supported')
    elif kind=='Competency' and state=='Verified':
        labels={q.get('competency') for q in questions(assessment)} if assessment else set()
        if name not in labels: fail('Competency verification must refer to an explicitly documented competency in a released assessment',409)
    expiry=body.get('expires_on')
    if expiry is not None:
        from datetime import date
        try:
            if not isinstance(expiry,str) or len(expiry)!=10: raise ValueError()
            parsed=date.fromisoformat(expiry)
        except ValueError: fail('Expiry must be a valid YYYY-MM-DD date')
        if state=='Verified' and parsed<datetime.now(timezone.utc).date(): fail('Expired evidence cannot be recorded as verified')
    row={'id':str(uuid.uuid4()),'tenant_id':tenant_of(user),'solver_id':solver_key(record),'kind':kind,'name':name,'status':state,
         'assessment_id':assessment['id'] if assessment else None,'document_id':str(document.get('id') or document['_id']),
         'reference':policy,'expires_on':expiry,'created_by':user['id'],'created_at':now(),'publication_state':'Pending_Audit'}
    await db.solver_competencies.insert_one(row)
    await audit_solver(db,user,'solver.assessment.competency.recorded',[record],['kind','status'],entity_type='solver_competency',entity_id=row['id'])
    await db.solver_competencies.update_one({'id':row['id']},{'$set':{'publication_state':'Ready'}})
    return {'recorded':True,'id':row['id']}


async def download_evidence(db,user,reference,document_id):
    row,record=await load(db,user,reference)
    references={row.get('answers',{}).get(q['id']) for q in questions(row) if q['type']=='document'}
    if document_id not in references: fail('This document is not part of the assigned assessment',403)
    doc=await find_linked_record(db.solver_documents,document_id,user)
    if doc.get('solver_id') not in solver_aliases(record) or doc.get('deleted_at'): fail('Document not found',404)
    if doc.get('visibility')!='hr_assessment' or doc.get('confidential') is not False: fail('Assessment evidence sharing is not authorized',403)
    from utils.solver_documents import download_authorized_file
    return await download_authorized_file(db,user,record,doc)
