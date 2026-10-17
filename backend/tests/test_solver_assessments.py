"""Synthetic assessment policy/content only. No reference roster or production data."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from bson import ObjectId
from utils import solver_assessments as service, administrative_reporting as reporting
from utils.access_matrix import RUNTIME_OVERRIDES
from utils.employee_integrity import integrity_write
from utils.notification_centre import list_inbox, read_notification
from routes import solvers
from .test_solver_workflows import fixture as base_fixture
from .test_solver_security import run, request
from .integrity_fakes import Collection, employee, account


def fixture():
    db,_,record=base_fixture()
    db.solver_assessment_settings=Collection();db.solver_competencies=Collection()
    owners={}
    for name,role,title in [('hr','hr_admin','HR Manager'),('assessor','line_manager','Principal Valuer'),('reviewer','line_manager','Technical Manager'),('other','line_manager','Principal Valuer')]:
        person=employee(name,name+'@example.com',role_title=title,employment_type='Full_Time')
        owner=account(name+'@example.com',role=role,employee_id=name,full_name='Synthetic '+name,is_active=True)
        db.employees.docs.append(person);db.users.docs.append(owner);owners[name]={**owner,'id':str(owner['_id'])}
    for name,key in [('solver','one'),('foreign_solver','two')]:
        owner=account(name+'@example.com',role='solver',account_type='solver',solver_id=key,is_active=True)
        db.users.docs.append(owner);owners[name]={**owner,'id':str(owner['_id'])}
    return db,owners,record


def configuration(**changes):
    return {'title':'Synthetic approved assessment','approval_reference':'Synthetic approval for local tests only',
        'pass_mark':70,'resit_wait_days':14,'time_limits':{'A':10,'B':15},'eligibility':{'states':['Registering','Active']},
        'certification_categories':['Saloon'],
        'sections':[
            {'id':'a','title':'Synthetic section A','part':'A','weight':40,'questions':[
                {'id':'a1','label':'Synthetic choice','type':'choice','scoring':'auto','points':2,'required':True,'options':['synthetic correct','synthetic incorrect'],'correct_answer':'synthetic correct'},
                {'id':'a2','label':'Synthetic written explanation','type':'text','scoring':'manual','points':2,'required':True,'rubric':'Synthetic rubric for test scoring only','competency':'Synthetic documented competency'}]},
            {'id':'b','title':'Synthetic section B','part':'B','weight':60,'questions':[
                {'id':'b1','label':'Synthetic valuation reference','type':'number','scoring':'auto','points':4,'required':True,'correct_answer':100,
                 'tolerance_bands':[{'max_difference':0,'points':4},{'max_difference':10,'points':2}]},
                {'id':'b2','label':'Synthetic valuation justification','type':'text','scoring':'manual','points':6,'required':True,'rubric':'Synthetic justification rubric'}]},
        ],**changes}


def assign(db,users,settings=None):
    config=run(service.save_configuration(db,users['hr'],settings or configuration()))
    run(service.publish(db,users['hr'],config['id']))
    row=run(service.assign(db,users['hr'],{'configuration_id':config['id'],'solver_id':'one','assessor_id':users['assessor']['id'],
        'reviewer_id':users['reviewer']['id'],'due_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
        'interview_reference':'Synthetic verified passed interview'}))
    return row,config


def submitted(db,users,**settings):
    row,config=assign(db,users,configuration(**settings))
    for part,answers in [('A',{'a1':'synthetic correct','a2':'Synthetic explanation'}),('B',{'b1':100,'b2':'Synthetic justification'})]:
        row=run(service.progress(db,users['solver'],row['id'],part,'start',{'revision':row['revision']}))
        row=run(service.progress(db,users['solver'],row['id'],part,'submit',{'revision':row['revision'],'answers':answers}))
    return row,config


def scored(db,users,**settings):
    row,config=submitted(db,users,**settings)
    row=run(service.decision(db,users['assessor'],row['id'],'score',{'revision':row['revision'],'marks':{'a2':2,'b2':4},'notes':'Synthetic scoring notes'}))
    return row,config


@pytest.mark.parametrize('role',['solver','foreign_solver','assessor','other'])
def test_question_bank_and_policy_publish_are_not_exposed_to_ordinary_or_assigned_assessors(role):
    db,users,_=fixture()
    with pytest.raises(HTTPException):run(service.configurations(db,users[role]))
    with pytest.raises(HTTPException):run(service.save_configuration(db,users[role],configuration()))
    with pytest.raises(HTTPException):run(service.publish(db,users[role],'forged'))


def test_technical_manager_can_draft_version_but_only_hr_can_publish():
    db,users,_=fixture();row=run(service.save_configuration(db,users['reviewer'],configuration()))
    with pytest.raises(HTTPException):run(service.publish(db,users['reviewer'],row['id']))
    assert run(service.publish(db,users['hr'],row['id']))['published']


def test_empty_draft_cannot_be_assigned_or_published_without_policy():
    db,users,_=fixture();row=run(service.save_configuration(db,users['hr'],{'title':'Unconfigured draft'}))
    assert row['status']=='Draft' and 'pass_mark' not in row['settings']
    with pytest.raises(HTTPException):run(service.publish(db,users['hr'],row['id']))
    assert not db.form_submissions.docs


@pytest.mark.parametrize('change',[{'pass_mark':float('nan')},{'resit_wait_days':-1},{'time_limits':{'A':0}}, {'sections':'invalid'},
                                 {'eligibility':{'states':['Suspended']}},{'certification_categories':['Invented category']},
                                 {'borderline':{'minimum':90,'maximum':20}},{'unexpected':'forged'}])
def test_invalid_configuration_is_rejected_without_writing(change):
    db,users,_=fixture()
    with pytest.raises(HTTPException):run(service.save_configuration(db,users['hr'],configuration(**change)))
    assert db.solver_assessment_settings.writes==0


def test_publish_requires_both_parts_and_explicit_weights_and_thresholds():
    db,users,_=fixture();settings=configuration();settings['sections'][1]['weight']=10
    row=run(service.save_configuration(db,users['hr'],settings))
    with pytest.raises(HTTPException):run(service.publish(db,users['hr'],row['id']))
    assert db.solver_assessment_settings.docs[0]['status']=='Draft'


def test_duplicate_question_identifiers_and_unselectable_keys_are_rejected():
    for variation in ('duplicate','key'):
        db,users,_=fixture();settings=configuration()
        if variation=='duplicate':settings['sections'][1]['questions'][0]['id']='a1'
        else:settings['sections'][0]['questions'][0]['correct_answer']='not an option'
        with pytest.raises(HTTPException):run(service.save_configuration(db,users['hr'],settings))


def test_assigned_snapshot_and_legacy_history_survive_new_versions():
    db,users,_=fixture();old={'_id':ObjectId(),'id':'legacy','form_id':'form-02','tenant_id':'solvit','subject_solver_id':'one','score':16,'data':{'historical':'answer'}}
    db.form_submissions.docs.append(deepcopy(old));row,config=assign(db,users)
    new=run(service.save_configuration(db,users['hr'],configuration(pass_mark=99),config['id']))
    assert new['version']==2
    saved,_=run(service.load(db,users['solver'],row['id']))
    assert saved['configuration']['pass_mark']==70 and db.form_submissions.docs[0]==old


def test_assignments_require_passed_interview_and_prevent_duplicates():
    db,users,_=fixture();row,config=assign(db,users)
    body={'configuration_id':config['id'],'solver_id':'one','assessor_id':users['assessor']['id'],
          'due_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'interview_reference':'Synthetic passed interview'}
    with pytest.raises(HTTPException):run(service.assign(db,users['hr'],body))
    assert len(db.form_submissions.docs)==1
    body['solver_id']='two';body.pop('interview_reference')
    with pytest.raises(HTTPException):run(service.assign(db,users['hr'],body))


@pytest.mark.parametrize('role',['foreign_solver','other'])
def test_assessment_ownership_and_assessor_assignment_are_enforced(role):
    db,users,_=fixture();row,_=assign(db,users)
    with pytest.raises(HTTPException):run(service.load(db,users[role],row['id']))
    assert run(service.listing(db,users[role]))==[]
    with pytest.raises(HTTPException):run(service.progress(db,users[role],row['id'],'A','start',{'revision':0}))


def test_no_keys_rubrics_unstarted_questions_or_unreleased_scores_in_solver_view():
    db,users,_=fixture();row,_=assign(db,users);candidate=service.projection(run(service.load(db,users['solver'],row['id']))[0],users['solver'])
    assert all(not section['questions'] for section in candidate['configuration']['sections'])
    candidate=run(service.progress(db,users['solver'],row['id'],'A','start',{'revision':0}))
    assert 'synthetic correct' in str(candidate)  # approved option, never labelled as the key
    assert 'correct_answer' not in str(candidate) and 'rubric' not in str(candidate)
    assert not next(section for section in candidate['configuration']['sections'] if section['part']=='B')['questions']
    assert 'score' not in candidate and 'outcome' not in candidate


def test_parts_are_ordered_required_answers_validated_and_revisions_enforced():
    db,users,_=fixture();row,_=assign(db,users)
    with pytest.raises(HTTPException):run(service.progress(db,users['solver'],row['id'],'B','start',{'revision':0}))
    row=run(service.progress(db,users['solver'],row['id'],'A','start',{'revision':0}))
    for body in ({'revision':0,'answers':{}},{'revision':row['revision'],'answers':{}},{'revision':row['revision'],'answers':{'b1':100}},{'revision':row['revision'],'answers':{'a1':'forged'}}):
        with pytest.raises(HTTPException):run(service.progress(db,users['solver'],row['id'],'A','submit',body))


def test_timer_expiry_only_permits_submission_of_previously_saved_answers():
    db,users,_=fixture();row,_=assign(db,users)
    row=run(service.progress(db,users['solver'],row['id'],'A','start',{'revision':0}))
    row=run(service.progress(db,users['solver'],row['id'],'A','save',{'revision':row['revision'],'answers':{'a1':'synthetic correct'}}))
    db.form_submissions.docs[0]['parts']['A']['started_at']=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()
    with pytest.raises(HTTPException):run(service.progress(db,users['solver'],row['id'],'A','save',{'revision':row['revision'],'answers':{'a2':'late'}}))
    row=run(service.progress(db,users['solver'],row['id'],'A','submit',{'revision':row['revision']}))
    assert row['parts']['A']['timed_out'] and 'a2' not in row['answers']


def test_scoring_uses_configured_weights_and_release_is_separate():
    db,users,_=fixture();row,_=scored(db,users)
    assert row['score']==88 and row['outcome']=='Pass'
    candidate=service.projection(run(service.load(db,users['solver'],row['id']))[0],users['solver'])
    assert 'score' not in candidate
    with pytest.raises(HTTPException):run(service.decision(db,users['solver'],row['id'],'release',{'revision':row['revision']}))
    with pytest.raises(HTTPException):run(service.decision(db,users['assessor'],row['id'],'release',{'revision':row['revision']}))
    row=run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))
    candidate=service.projection(run(service.load(db,users['solver'],row['id']))[0],users['solver'])
    assert candidate['score']==88 and 'assessor_notes' not in candidate and 'correct_answer' not in str(candidate)


def test_numeric_tolerances_and_manual_mark_limits_are_configuration_driven():
    db,users,_=fixture();row,_=submitted(db,users);saved,_=run(service.load(db,users['hr'],row['id']))
    saved['answers']['b1']=105
    total,_=service.score(saved,{'a2':2,'b2':6});assert total==88
    for marks in ({'a2':3,'b2':6},{'a2':float('inf'),'b2':6},{'a2':2,'b2':6,'a1':2}):
        with pytest.raises(HTTPException):service.score(saved,marks)


def test_borderline_release_requires_different_assigned_technical_reviewer():
    db,users,_=fixture();row,_=scored(db,users,borderline={'minimum':85,'maximum':90})
    with pytest.raises(HTTPException):run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))
    with pytest.raises(HTTPException):run(service.decision(db,users['assessor'],row['id'],'review',{'revision':row['revision'],'notes':'Self review denied'}))
    row=run(service.decision(db,users['reviewer'],row['id'],'review',{'revision':row['revision'],'notes':'Synthetic independent review'}))
    assert run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))['status']=='Released'


def test_legacy_profile_cannot_disclose_new_unreleased_result():
    db,users,_=fixture();row,_=scored(db,users)
    with patch.multiple(solvers,get_db=lambda:db,get_current_user=AsyncMock(return_value=users['solver'])):
        assert run(solvers.solver_workflow('one',request()))['assessments']==[]


def test_audit_failure_keeps_assignment_and_release_unpublished():
    db,users,_=fixture();row,_=scored(db,users)
    db.audit_logs.insert_one=AsyncMock(side_effect=RuntimeError('Synthetic audit outage'))
    with pytest.raises(HTTPException):run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))
    saved,_=run(service.load(db,users['solver'],row['id']));candidate=service.projection(saved,users['solver'])
    assert candidate['status']=='Needs administrator review' and 'score' not in candidate
    with pytest.raises(HTTPException):run(service.decision(db,users['hr'],row['id'],'release',{'revision':saved['revision']}))


def test_notifications_are_scoped_readable_and_do_not_expose_answers():
    db,users,_=fixture();row,_=assign(db,users)
    assert run(list_inbox(db,users['solver']))['unread_count']==1
    assert run(list_inbox(db,users['foreign_solver']))['total']==0
    item=run(list_inbox(db,users['assessor']))['items'][0]
    assert item['link'].startswith('/solver-assessments?assessment=') and 'synthetic correct' not in str(item)
    with pytest.raises(HTTPException):run(read_notification(db,users['other'],item['id']))
    count=len(db.notifications.docs);saved,_=run(service.load(db,users['hr'],row['id']));run(service.notify(db,saved,'assigned'))
    assert len(db.notifications.docs)==count


def evidence(db,record):
    db.solver_documents.docs.append({'_id':ObjectId(),'id':'proof','tenant_id':'solvit','solver_id':'one','scan_status':'Clean',
        'publication_state':'Ready','visibility':'hr_only','confidential':True})
    return {'kind':'Certification','name':'Saloon','status':'Verified','document_id':'proof','reference':'Synthetic approved certification rules'}


def test_competencies_are_evidence_based_and_never_inferred_from_legacy_categories():
    db,users,record=fixture();body=evidence(db,record)
    assert run(service.competencies(db,users['solver'],'one'))['items']==[]
    with pytest.raises(HTTPException):run(service.record_competency(db,users['hr'],'one',body))
    row,_=scored(db,users);row=run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))
    body['assessment_id']=row['id'];run(service.record_competency(db,users['hr'],'one',body))
    result=run(service.competencies(db,users['solver'],'one'))
    assert result['items'][0]['status']=='Verified' and 'document_id' not in str(result['items'])
    assert 'vehicle_categories' not in db.solvers.docs[0]
    with pytest.raises(HTTPException):run(service.competencies(db,users['foreign_solver'],'one'))


def test_module_revocations_block_configuration_results_and_certification():
    db,users,_=fixture();row,_=assign(db,users)
    with patch.dict(RUNTIME_OVERRIDES,{('M03','hr_admin'):None}):
        with pytest.raises(HTTPException):run(service.configurations(db,users['hr']))
        with pytest.raises(HTTPException):run(service.load(db,users['hr'],row['id']))
    with patch.dict(RUNTIME_OVERRIDES,{('M03','line_manager'):None}):
        with pytest.raises(HTTPException):run(service.load(db,users['assessor'],row['id']))


def test_report_excludes_banks_answers_notes_and_unreleased_scores():
    db,users,_=fixture();row,_=scored(db,users)
    result=run(reporting.report_data(db,users['hr'],'solver_assessments',export=True))
    assert result['total']==1 and 'score' not in result['items'][0] and 'configuration' not in result['items'][0]
    assert 'Synthetic scoring notes' not in str(result) and 'synthetic correct' not in str(result)
    result=run(reporting.report_data(db,{'id':'executive','role':'executive','tenant_id':'solvit'},'solver_assessments',export=True))
    assert result['summary_only'] and 'solver_name' not in str(result)


def test_answers_can_be_cleared_but_submitted_answers_cannot_be_changed():
    db,users,_=fixture();row,_=assign(db,users)
    row=run(service.progress(db,users['solver'],row['id'],'A','start',{'revision':0}))
    row=run(service.progress(db,users['solver'],row['id'],'A','save',{'revision':row['revision'],'answers':{'a2':'draft'}}))
    row=run(service.progress(db,users['solver'],row['id'],'A','save',{'revision':row['revision'],'answers':{'a2':None}}))
    assert 'a2' not in row['answers']
    row=run(service.progress(db,users['solver'],row['id'],'A','submit',{'revision':row['revision'],'answers':{'a1':'synthetic correct','a2':'final'}}))
    with pytest.raises(HTTPException):run(service.progress(db,users['solver'],row['id'],'A','save',{'revision':row['revision'],'answers':{'a2':'forged'}}))


def test_decimal_scoring_does_not_round_a_below_threshold_result_up_to_a_pass():
    db,users,_=fixture();row,_=submitted(db,users,pass_mark=100)
    row=run(service.decision(db,users['assessor'],row['id'],'score',{'revision':row['revision'],'marks':{'a2':2,'b2':5.9999999},'notes':'Synthetic exact boundary test'}))
    assert row['score']<100 and row['outcome']=='Fail'


def test_hr_role_without_a_documented_assessor_title_cannot_be_nominated():
    db,users,_=fixture()
    with pytest.raises(HTTPException):run(service.assigned_account(db,users['hr'],users['hr']['id']))
    with patch.dict(RUNTIME_OVERRIDES,{('M03','line_manager'):{'level':'Read','scope':'own_record'}}):
        with pytest.raises(HTTPException):run(service.assessor(db,users['assessor']))


def test_failed_assessment_resit_respects_the_approved_wait_period():
    db,users,_=fixture();row,config=submitted(db,users,pass_mark=100)
    row=run(service.decision(db,users['assessor'],row['id'],'score',{'revision':row['revision'],'marks':{'a2':0,'b2':0},'notes':'Synthetic failed attempt'}))
    row=run(service.decision(db,users['hr'],row['id'],'release',{'revision':row['revision']}))
    body={'configuration_id':config['id'],'solver_id':'one','assessor_id':users['assessor']['id'],
          'due_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'interview_reference':'Synthetic passed interview'}
    with pytest.raises(HTTPException):run(service.assign(db,users['hr'],body))
    db.form_submissions.docs[0]['released_at']=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
    assert run(service.assign(db,users['hr'],body))['status']=='Assigned'


def test_assessment_evidence_requires_explicit_sharing_and_assigned_ownership(tmp_path):
    from routes import documents as document_routes
    db,users,record=fixture();settings=configuration()
    settings['sections'][1]['questions'].append({'id':'b3','label':'Synthetic proof','type':'document','scoring':'none','required':False})
    row,_=assign(db,users,settings)
    doc={'_id':ObjectId(),'id':'proof','tenant_id':'solvit','solver_id':'one','scan_status':'Clean','publication_state':'Ready',
         'visibility':'hr_only','confidential':True,'file_name':'proof.pdf'}
    folder=tmp_path/'solvers'/str(record['_id']);folder.mkdir(parents=True);path=folder/'proof.pdf';path.write_bytes(b'%PDF-1.4\n%%EOF');doc['stored_path']=str(path)
    db.solver_documents.docs.append(doc)
    for part,answers in [('A',{'a1':'synthetic correct','a2':'Synthetic explanation'})]:
        row=run(service.progress(db,users['solver'],row['id'],part,'start',{'revision':row['revision']}))
        row=run(service.progress(db,users['solver'],row['id'],part,'submit',{'revision':row['revision'],'answers':answers}))
    row=run(service.progress(db,users['solver'],row['id'],'B','start',{'revision':row['revision']}))
    with pytest.raises(HTTPException):run(service.progress(db,users['solver'],row['id'],'B','save',{'revision':row['revision'],'answers':{'b3':'proof'}}))
    doc.update(visibility='hr_assessment',confidential=False)
    row=run(service.progress(db,users['solver'],row['id'],'B','save',{'revision':row['revision'],'answers':{'b3':'proof'}}))
    with patch.object(document_routes,'UPLOAD_ROOT',tmp_path):
        response=run(service.download_evidence(db,users['assessor'],row['id'],'proof'))
        assert response.headers['cache-control']=='no-store'
        with pytest.raises(HTTPException):run(service.download_evidence(db,users['other'],row['id'],'proof'))
    assert db.document_audit.docs[-1]['action']=='downloaded'


def test_actual_http_routes_enforce_ownership_keys_and_cache_headers(monkeypatch):
    from fastapi.testclient import TestClient
    from server import app
    from utils.auth import create_access_token
    from routes import solver_assessments as routes
    db,users,_=fixture();row,_=assign(db,users)
    monkeypatch.setenv('JWT_SECRET','Synthetic-assessment-local-signing-key-only-2026')
    with patch('database.get_db',return_value=db),patch.object(routes,'get_db',return_value=db):
        client=TestClient(app,base_url='http://127.0.0.1:18089')
        def headers(name):
            user=users[name]
            return {'Authorization':'Bearer '+create_access_token(user['id'],user['email'],user['role'])}
        assert client.get('/api/solver-assessments/configurations',headers=headers('solver')).status_code==403
        response=client.get('/api/solver-assessments/attempts/'+row['id'],headers=headers('solver'))
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert 'correct_answer' not in response.text and 'rubric' not in response.text
        assert client.get('/api/solver-assessments/attempts/'+row['id'],headers=headers('foreign_solver')).status_code==403
        assert client.post('/api/solver-assessments/attempts/'+row['id']+'/score',headers=headers('solver'),json={'revision':0,'marks':{},'notes':'forged'}).status_code==403
        client.close()


def test_real_local_mongo_serializes_duplicate_assignments_and_records_audit():
    import asyncio
    from .test_employee_integrity_mongo import local_database
    async def check():
        fake,users,_=fixture()
        async with local_database() as db:
            for name in ('solvers','users','employees'):
                await getattr(db,name).insert_many(deepcopy(getattr(fake,name).docs))
            async with integrity_write(db):
                config=await service.save_configuration(db,users['hr'],configuration())
                await service.publish(db,users['hr'],config['id'])
            body={'configuration_id':config['id'],'solver_id':'one','assessor_id':users['assessor']['id'],
                'due_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'interview_reference':'Synthetic passed interview'}
            async def one():
                async with integrity_write(db):return await service.assign(db,users['hr'],body)
            results=await asyncio.gather(one(),one(),return_exceptions=True)
            assert await db.form_submissions.count_documents({'workflow_kind':service.KIND})==1
            assert sum(isinstance(row,HTTPException) and row.status_code==409 for row in results)==1
            assert await db.audit_logs.count_documents({'event':'solver.assessment.assigned'})==1
    run(check())


def test_audit_events_reference_immutable_versions_and_attempts_without_copying_keys():
    db,users,_=fixture();row,config=assign(db,users)
    events=db.audit_logs.docs
    created=next(event for event in events if event['event']=='solver.assessment.configuration.created')
    assigned=next(event for event in events if event['event']=='solver.assessment.assigned')
    assert created['entity_id']==config['id'] and assigned['entity_id']==row['id']
    assert 'synthetic correct' not in str(events) and 'Synthetic rubric' not in str(events)


def test_legacy_storage_aliases_resolve_to_one_canonical_solver_and_attempt():
    db,users,record=fixture();config=run(service.save_configuration(db,users['hr'],configuration()));run(service.publish(db,users['hr'],config['id']))
    row=run(service.assign(db,users['hr'],{'configuration_id':config['id'],'solver_id':str(record['_id']),
        'assessor_id':users['assessor']['id'],'due_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'interview_reference':'Synthetic interview reference'}))
    assert row['subject_solver_id']=='one'
    saved,_=run(service.load(db,users['solver'],str(db.form_submissions.docs[0]['_id'])))
    assert saved['id']==row['id']


def test_approximate_weight_totals_cannot_change_the_approved_scoring_denominator():
    settings=configuration();settings['sections'][1]['weight']=59.9999999
    with pytest.raises(HTTPException):service.validate_configuration(settings,publishing=True)
