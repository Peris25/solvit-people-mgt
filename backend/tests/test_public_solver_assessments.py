"""Synthetic anonymous intake; never touches production or submits Google Forms."""
import asyncio
from copy import deepcopy
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from utils import public_solver_assessments as service
from .integrity_fakes import Database, Collection
from .test_notification_centre import Receipts


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','synthetic-public-assessment-signing-key-only')
    clock=[1800000000.0]; monkeypatch.setattr(service.time,'time',lambda:clock[0])
    db=Database([],[]); db.public_solver_assessments=Collection(); db.notifications=Receipts(); db.audit_logs=Receipts(); db.solvers=Collection()
    yield db,clock


def payload(clock):
    challenge=service.issue_challenge(); a,b=challenge['token'].split('|')[2:4]; clock[0]+=4
    answers={q['id']:q.get('options',['Synthetic answer'])[0] for s in service.BANK['sections'] for q in s['questions'] if q['required'] and not q.get('availability')}
    answers['2073566651']='Synthetic applicant'
    return {'version':service.BANK['version'],'answers':answers,'consent':True,'challenge_token':challenge['token'],'challenge_answer':str(int(a)+int(b))}


def test_public_submit_is_idempotent_and_does_not_create_solver_or_account(state):
    db,clock=state; body=payload(clock)
    async def check(): return await asyncio.gather(service.submit(db,body,'synthetic-ip'),service.submit(db,body,'synthetic-ip'))
    rows=asyncio.run(check()); assert rows[0]==rows[1]
    assert len([r for r in db.public_solver_assessments.docs if r['kind']==service.PUBLIC_KIND])==1
    assert len(db.notifications.docs)==3 and len(db.audit_logs.docs)==1
    assert not db.solvers.docs and not db.users.docs
    assert 'answers' not in str(rows) and 'Synthetic applicant' not in str(db.notifications.docs)
    assert all(row['data']['public_solver_assessment_id']==rows[0]['reference'] for row in db.notifications.docs)


@pytest.mark.parametrize('field,value',[('tenant_id','another'),('solver_id','forged'),('score',100)])
def test_public_rejects_forged_identity_or_scores(state,field,value):
    db,clock=state; body=payload(clock); body[field]=value
    with pytest.raises(HTTPException): asyncio.run(service.submit(db,body,'synthetic-ip'))
    assert db.public_solver_assessments.writes==0


@pytest.mark.parametrize('change',['expired','tampered','incorrect','consent','unknown','required','unavailable'])
def test_validation_rejects_bad_proof_or_answers_without_writes(state,change):
    db,clock=state; body=payload(clock)
    if change=='expired': clock[0]+=7201
    if change=='tampered': body['challenge_token']+='x'
    if change=='incorrect': body['challenge_answer']='0'
    if change=='consent': body['consent']=False
    if change=='unknown': body['answers']['unknown']='Secret'
    if change=='required': del body['answers']['2073566651']
    if change=='unavailable': body['answers']['545968819']='1'
    with pytest.raises(HTTPException): asyncio.run(service.submit(db,body,'synthetic-ip'))
    assert db.public_solver_assessments.writes==0


def test_submission_limit_persists_across_calls_and_retries_do_not_duplicate(state):
    db,clock=state
    for _ in range(5): asyncio.run(service.submit(db,payload(clock),'same-ip'))
    with pytest.raises(HTTPException) as exc: asyncio.run(service.submit(db,payload(clock),'same-ip'))
    assert exc.value.status_code==429


def test_only_hr_can_list_review_and_read_answers(state):
    db,clock=state; row=asyncio.run(service.submit(db,payload(clock),'synthetic-ip'))
    for role in ['employee','solver','line_manager','it_admin','executive']:
        actor={'id':'actor','role':role,'tenant_id':'solvit'}
        with pytest.raises(HTTPException): asyncio.run(service.applications(db,actor))
        with pytest.raises(HTTPException): asyncio.run(service.application(db,actor,row['reference']))
    for role in ['hr_admin','hr_manager','general_manager']:
        actor={'id':'reviewer','role':role,'tenant_id':'solvit'}
        listed=asyncio.run(service.applications(db,actor)); assert len(listed)==1 and 'answers' not in listed[0]
        detail=asyncio.run(service.application(db,actor,row['reference'])); assert detail['answers']['2073566651']=='Synthetic applicant'
    assert asyncio.run(service.review(db,actor,row['reference'],{'notes':'Interview and photo follow-up required'}))['status']=='Reviewed'
    assert asyncio.run(service.application(db,actor,row['reference']))['review_notes']=='Interview and photo follow-up required'
    with pytest.raises(HTTPException): asyncio.run(service.applications(db,{**actor,'tenant_id':'other'}))
    with pytest.raises(HTTPException): asyncio.run(service.review(db,actor,row['reference'],{'notes':'Second review'}))


def test_http_only_three_public_handlers_are_exempt_and_admin_stays_protected(state):
    from server import app,SESSION_EXEMPT_ENDPOINTS
    from routes import solver_assessments
    db,clock=state
    handlers={f.__name__ for f in SESSION_EXEMPT_ENDPOINTS if f.__module__==solver_assessments.__name__}
    assert handlers=={'public_questionnaire','public_challenge','public_submission'}
    with patch('database.get_db',return_value=db),patch.object(solver_assessments,'get_db',return_value=db):
        client=TestClient(app,base_url='http://localhost')
        assert client.get('/api/solver-assessments/public/questionnaire').status_code==200
        assert client.get('/api/solver-assessments/public/challenge').status_code==200
        assert client.get('/api/solver-assessments/applications').status_code==401
        assert client.get('/api/solver-assessments/attempts').status_code==401
        response=client.post('/api/solver-assessments/public/submissions',content=b'x'*160001)
        assert response.status_code==413
        submitted=client.post('/api/solver-assessments/public/submissions',json=payload(clock))
        assert submitted.status_code==201 and 'answers' not in submitted.json()
        assert client.get('/api/solver-assessments/applications/'+submitted.json()['reference']).status_code==401
        assert client.post('/api/solver-assessments/public/submissions',json=payload(clock),headers={'Origin':'https://untrusted.example'}).status_code==403
        client.close()


def test_retired_existing_solver_assignment_cannot_create_attempts(state):
    from routes import solver_assessments
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    db,_=state
    with patch.object(solver_assessments,'get_current_user',AsyncMock(return_value={'id':'hr','role':'hr_admin'})),patch.object(solver_assessments,'get_db') as database:
        with pytest.raises(HTTPException) as exc: asyncio.run(solver_assessments.assign(SimpleNamespace()))
    assert exc.value.status_code==410
    database.assert_not_called()
