from copy import deepcopy
from types import SimpleNamespace
import pytest
from bson import ObjectId
from fastapi import HTTPException
from utils import approved_growth_kpi_correction as repair,performance_v3 as process,role_kpi_library as library
from .test_grace_kpi_repair import DB,SessionCollection,Session
from .integrity_fakes import employee
from .test_profile_self_service import run


def fixture():
    lucy=employee('lucy','lucy@example.com',full_name='Lucy Ndinguri',role_title='Growth Captain')
    db=DB([lucy,employee('other','other@example.com')])
    for name in ('employees','system_settings','performance_reviews','removed_employee_records','audit_logs','notifications'):
        setattr(db,name,SessionCollection(getattr(db,name).docs if hasattr(db,name) else []))
    template=deepcopy(next(row for row in library.catalogue() if row['role_id']=='it-support'))
    values={key:deepcopy(template[key]) for key in library.ENTRY_FIELDS}
    values.update(role_id='growth-captain',name='Growth Captain',scope='Annual',notes='Current HR edits',group_weights={})
    base=template['goals'][0]
    values['goals']=[{**deepcopy(base),'id':f'growth-{index}','objective':name,'metric':'Approved HR measurement','target':'Approved scoring rubric','target_value':None,'direction':'Rated','weight':weight,'group':''} for index,(name,weight) in enumerate([('Valuation Prospects',40),('Average Partner NPS',20),('Key Partners Retention',20),('New Partners & Awarded Fleets',20)])]
    old=deepcopy(values);old['goals']=deepcopy(template['goals']);old['goals'][0]['objective']='Previous recruitment criterion'
    source={'_id':library.identity(lucy,'growth-captain'),'tenant_id':'solvit','category':'performance_role_kpi_library','values':values,'published_values':old,'version':'hr-draft-v2','published_version':'old-v1','status':'Draft'}
    assigned={'_id':process.key(process.ASSIGNMENT,'solvit','lucy'),'tenant_id':'solvit','employee_id':'lucy','values':old,'version':'a1'}
    db.system_settings.docs=[source,assigned]
    db.performance_reviews.docs=[{'_id':ObjectId(),'id':'review','tenant_id':'solvit','employee_id':'lucy','workflow_version':3,'cycle_type':'Year_End','cycle_year':2026,'status':'Self_Draft','section_a_kpis':deepcopy(old['goals']),'group_weights':{},'version':'r1'}]
    async def start_session():return Session(db)
    db.client=SimpleNamespace(start_session=start_session)
    return db


def test_correction_updates_assignment_and_review_to_four_hr_kpis_without_publishing_role_or_emailing():
    db=fixture();source=deepcopy(db.system_settings.docs[0]);people=deepcopy(db.employees.docs)
    result=run(repair.apply(db))
    assert result=={'status':'applied','kpi_count':4,'reviews_updated':1}
    goals=db.performance_reviews.docs[0]['section_a_kpis']
    assert [goal['weight'] for goal in goals]==[40,20,20,20]
    assert len(goals)==4 and db.system_settings.docs[1]['values']['goals']==goals
    assert db.system_settings.docs[0]==source and db.employees.docs==people
    assert len(db.removed_employee_records.docs)==2 and not db.notifications.docs
    assert db.audit_logs.docs[0]['metadata']['source_field']=='values'


def test_started_draft_answers_are_archived_and_other_sections_preserved():
    db=fixture();row=db.performance_reviews.docs[0];old=row['section_a_kpis'][0]['id']
    assessment={'actuals':{old:{'actual':25,'self_score':1.5}},'values':[{'score':8,'example':'Original example'}],'challenge':'Original reflection','support':'Original support'}
    row['self_assessment']=deepcopy(assessment)
    run(repair.apply(db));row=db.performance_reviews.docs[0]
    assert row['self_assessment']=={**assessment,'actuals':{}}
    assert row['kpi_draft_revisions'][0]['actuals']==assessment['actuals']
    assert row['kpi_draft_revisions'][0]['goals'][0]['id']==old


def test_identical_kpi_definitions_retain_answers_even_if_ids_change():
    db=fixture();new=db.system_settings.docs[0]['values']['goals'][0]
    row=db.performance_reviews.docs[0];row['section_a_kpis'][0]={**deepcopy(new),'id':'old-id'}
    row['self_assessment']={'actuals':{'old-id':{'actual':10,'self_score':1}},'values':[],'challenge':'Kept'}
    run(repair.apply(db))
    assert db.performance_reviews.docs[0]['self_assessment']['actuals']=={new['id']:{'actual':10,'self_score':1}}


def test_submitted_reviews_and_incomplete_role_definitions_are_not_overwritten():
    db=fixture();db.performance_reviews.docs[0]['status']='Self_Submitted';before=deepcopy(db.system_settings.docs)
    with pytest.raises(HTTPException):run(repair.apply(db))
    assert db.system_settings.docs==before and not db.audit_logs.docs
    db=fixture();db.system_settings.docs[0]['values']['goals'][0]['weight']=30
    assert run(repair.run(db))=={'status':'needs_review','reason':'approved_role_not_ready'}
    db=fixture();db.system_settings.docs[0]['published_values']=deepcopy(db.system_settings.docs[0]['values'])
    db.system_settings.docs[0]['values']['goals'][0]['target']=''
    assert run(repair.run(db))=={'status':'needs_review','reason':'approved_role_not_ready'}


def test_marker_preserves_later_hr_amendments_and_transaction_failure_rolls_back():
    db=fixture();run(repair.apply(db));db.system_settings.docs[1]['values']['notes']='Later HR change'
    assert run(repair.apply(db))['already_applied']
    assert db.system_settings.docs[1]['values']['notes']=='Later HR change'
    db=fixture();before=deepcopy(db.system_settings.docs)
    async def fail(*args,**kwargs):raise RuntimeError('Synthetic audit failure')
    db.audit_logs.insert_one=fail
    with pytest.raises(RuntimeError):run(repair.apply(db))
    assert db.system_settings.docs==before and not db.removed_employee_records.docs
