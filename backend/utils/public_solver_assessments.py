"""Anonymous applicant questionnaires; never creates Solver or login records."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from utils.auth import get_jwt_secret
from utils.solver_assessments import hr, assessor, HR_ROLES
from utils.employee_integrity import tenant_of

BANK = json.loads((Path(__file__).resolve().parents[1] / 'data/public_solver_questionnaire.json').read_text(encoding='utf-8'))
PUBLIC_KIND = 'new_solver_questionnaire'


def now(): return datetime.now(timezone.utc).isoformat()

def signature(value):
    return hmac.new(get_jwt_secret().encode(), ('solver-public-v1:' + value).encode(), hashlib.sha256).hexdigest()


def questionnaire(): return BANK


def issue_challenge():
    a,b=secrets.randbelow(8)+2,secrets.randbelow(8)+2
    value=f'{int(time.time())}|{secrets.token_hex(16)}|{a}|{b}'
    return {'token':value+'|'+signature(value),'question':f'What is {a} + {b}?','expires_in':7200}


def verify_challenge(token,answer):
    try:
        issued,nonce,a,b,sig=token.split('|')
        value='|'.join([issued,nonce,a,b])
        if len(nonce)!=32 or not hmac.compare_digest(signature(value),sig): raise ValueError()
        age=time.time()-int(issued)
        if age<3 or age>7200 or str(int(a)+int(b)) != str(answer).strip(): raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(422,'Verification expired or incorrect. Refresh the verification question and try again; your answers can be kept.')


def validate(body):
    allowed={'version','answers','challenge_token','challenge_answer','website','consent'}
    if not isinstance(body,dict) or set(body)-allowed: raise HTTPException(422,'Unknown assessment fields')
    if body.get('version')!=BANK['version']: raise HTTPException(409,'The questionnaire changed. Reload before submitting.')
    if body.get('website') or body.get('consent') is not True: raise HTTPException(422,'Confirm that Solvit may review this assessment.')
    answers=body.get('answers')
    questions={q['id']:q for section in BANK['sections'] for q in section['questions']}
    if not isinstance(answers,dict) or set(answers)-set(questions): raise HTTPException(422,'Unknown assessment answers')
    result={}
    for key,q in questions.items():
        value=answers.get(key,'')
        if not isinstance(value,str) or len(value)>6000 or any(ord(c)<32 and c not in '\n\t' for c in value):
            raise HTTPException(422,'Answers must be text within 6,000 characters')
        value=value.strip()
        condition=q.get('unless_answer')
        inactive=condition and answers.get(condition['id'])==condition['value']
        if inactive or q.get('availability'):
            if value: raise HTTPException(422,'An unavailable question cannot be answered')
            continue
        if q['required'] and not value: raise HTTPException(422,'Complete every required question')
        if value and q.get('options') and value not in q['options']: raise HTTPException(422,'Choose an available answer')
        if value: result[key]=value
    name=result.get('2073566651','')
    if not 2<=len(name)<=200: raise HTTPException(422,'Enter the applicant name within 200 characters')
    return result


async def reserve_rate(db,ip):
    # Built-in _id uniqueness enforces a shared multiworker five/hour limit.
    key=signature('rate:'+str(ip))
    window=int(time.time()//3600)
    for slot in range(5):
        try:
            await db.public_solver_assessments.insert_one({'_id':f'rate:{key}:{window}:{slot}', 'kind':'rate_limit', 'created_at':now()})
            return
        except DuplicateKeyError: continue
    raise HTTPException(429,'Too many submissions. Please try again later.')


async def finish_publication(db,row):
    event={'tenant_id':'solvit','actor_id':'anonymous_applicant','event':'solver.public_assessment.submitted','entity_id':row['id'],'timestamp':row['submitted_at']}
    await db.audit_logs.update_one({'_id':'public-assessment:'+row['id']},{'$setOnInsert':event},upsert=True)
    for role in ('hr_admin','hr_manager','general_manager'):
        fields={'tenant_id':'solvit','recipient_role':role,'category':'Onboarding','title':'New Solver assessment received',
                'message':'A new applicant assessment is ready for HR review.', 'created_at':row['submitted_at'],'is_read':False,
                'data':{'public_solver_assessment_id':row['id']}}
        await db.notifications.update_one({'_id':f'public-assessment:{row["id"]}:{role}'},{'$setOnInsert':fields},upsert=True)
    await db.public_solver_assessments.update_one({'_id':row['_id']},{'$set':{'publication_state':'Ready'}})


async def submit(db,body,ip):
    answers=validate(body)
    verify_challenge(body.get('challenge_token'),body.get('challenge_answer'))
    digest=hashlib.sha256(json.dumps({'version':BANK['version'],'answers':answers},sort_keys=True).encode()).hexdigest()
    key='submission:'+hashlib.sha256(body['challenge_token'].encode()).hexdigest()
    row=await db.public_solver_assessments.find_one({'_id':key})
    if row is None:
        await reserve_rate(db,ip)
        row={'_id':key,'id':str(uuid.uuid4()),'kind':PUBLIC_KIND,'tenant_id':'solvit','version':BANK['version'],
             'source_url':BANK['source_url'],'questions':BANK['sections'],'full_name':answers['2073566651'],'answers':answers,
             'status':'Submitted','submitted_at':now(),'consent_at':now(),'publication_state':'Pending_Audit','payload_digest':digest,
             'pending_questions':[q['id'] for section in BANK['sections'] for q in section['questions'] if q.get('availability')]}
        try: await db.public_solver_assessments.insert_one(row)
        except DuplicateKeyError: row=await db.public_solver_assessments.find_one({'_id':key})
    if row['payload_digest']!=digest: raise HTTPException(409,'This verification was already used. Refresh it before a different submission.')
    if row.get('publication_state')!='Ready': await finish_publication(db,row)
    return {'reference':row['id'],'status':'Submitted','message':'Your assessment has been received for HR review. This does not create a Solver account or certify a result.'}


def summary(row):
    return {key:row.get(key) for key in ('id','full_name','version','status','submitted_at','reviewed_at','pending_questions')}


async def reviewer(db,user):
    """HR or the saved Operations/Technical hiring leads; no wider HR grant."""
    if tenant_of(user) != 'solvit': raise HTTPException(403,'No access to these applications')
    if user.get('role') in HR_ROLES:
        hr(user)
        return
    employee = await assessor(db,user)
    from utils.staff_directory import normalized, employment_type
    if user.get('role') != 'line_manager' or employment_type(employee.get('employment_type')) != 'Full_Time' or normalized(employee.get('role_title')) not in {
        'operationscoordinator', 'operationscoordinatorheadofsolvers', 'technicalservicesgrowthmanager'}:
        raise HTTPException(403,'Only HR and the Operations/Technical hiring leads may view applicant assessments')


async def review_capabilities(db,user):
    try: await reviewer(db,user)
    except HTTPException as error:
        if error.status_code == 403: return {'can_view':False,'can_review':False}
        raise
    return {'can_view':True,'can_review':user.get('role') in HR_ROLES}


async def applications(db,user):
    await reviewer(db,user)
    if tenant_of(user)!='solvit': raise HTTPException(403,'No access to these applications')
    rows=await db.public_solver_assessments.find({'tenant_id':'solvit','kind':PUBLIC_KIND,'publication_state':'Ready'}).sort('submitted_at',-1).to_list(500)
    return [summary(row) for row in rows]


async def application(db,user,reference):
    await reviewer(db,user)
    if tenant_of(user)!='solvit': raise HTTPException(403,'No access to this application')
    row=await db.public_solver_assessments.find_one({'tenant_id':'solvit','kind':PUBLIC_KIND,'id':reference,'publication_state':'Ready'})
    if not row: raise HTTPException(404,'Assessment not found')
    await db.audit_logs.insert_one({'tenant_id':'solvit','actor_id':user['id'],'event':'solver.public_assessment.viewed','entity_id':row['id'],'timestamp':now()})
    return {**summary(row),'answers':row['answers'],'sections':row['questions'],'source_url':row['source_url'],'review_notes':row.get('review_notes','') if user.get('role') in HR_ROLES else ''}


async def review(db,user,reference,body):
    hr(user)  # Hiring leads have read access; formal HR review remains with HR.
    row=await application(db,user,reference)
    if not isinstance(body,dict) or set(body)!={'notes'} or not isinstance(body['notes'],str) or not 3<=len(body['notes'].strip())<=4000:
        raise HTTPException(422,'Provide review notes within 4,000 characters')
    if row['status']=='Reviewed': raise HTTPException(409,'This assessment has already been reviewed')
    at=now()
    # Persist review intent before changing status, so an audit outage cannot
    # leave a wholly unaudited decision. The row also retains reviewer/time.
    await db.audit_logs.insert_one({'tenant_id':'solvit','actor_id':user['id'],'event':'solver.public_assessment.review_requested','entity_id':reference,'timestamp':at})
    changed=await db.public_solver_assessments.update_one({'id':reference,'tenant_id':'solvit','kind':PUBLIC_KIND,'status':'Submitted','publication_state':'Ready'},
        {'$set':{'status':'Reviewed','reviewed_at':at,'reviewed_by':user['id'],'review_notes':body['notes'].strip()}})
    if not changed.modified_count: raise HTTPException(409,'Assessment changed; refresh before reviewing')
    await db.audit_logs.insert_one({'tenant_id':'solvit','actor_id':user['id'],'event':'solver.public_assessment.reviewed','entity_id':reference,'timestamp':at})
    return {'id':reference,'status':'Reviewed'}
