from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from bson import ObjectId
from fastapi import HTTPException
from scripts import repair_grace_kpis as repair
from utils import performance_v3 as process, role_kpi_library as library
from .integrity_fakes import Collection, Database, employee
from .test_profile_self_service import run


class SessionCollection(Collection):
    async def find_one(self, query, projection=None, **kwargs): return await super().find_one(query,projection)
    async def insert_one(self, doc, **kwargs): return await super().insert_one(doc)
    async def update_one(self, query, update, **kwargs): return await super().update_one(query,update)


class Transaction:
    def __init__(self, db): self.db=db
    async def __aenter__(self):
        self.before={name:(deepcopy(value.docs),value.writes) for name,value in vars(self.db).items() if isinstance(value,Collection)}
        return self
    async def __aexit__(self, kind, value, traceback):
        if kind:
            for name,(docs,writes) in self.before.items(): getattr(self.db,name).docs=docs; getattr(self.db,name).writes=writes


class Session:
    def __init__(self,db): self.db=db
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def start_transaction(self): return Transaction(self.db)


class DB(Database):
    def __getitem__(self,name): return getattr(self,name)


def fixture():
    grace=employee('grace','gmungai@solvit.co.ke',full_name='Grace Wangui Mungai',role_title='Finance and Operations Manager')
    db=DB([grace,employee('other','other@example.com')])
    for name in ('employees','system_settings','performance_reviews','removed_employee_records','audit_logs','notifications'):
        setattr(db,name,SessionCollection(getattr(db,name).docs if hasattr(db,name) else []))
    values={k:deepcopy(next(e for e in library.catalogue() if e['role_id']=='finance-operations-manager')[k]) for k in library.ENTRY_FIELDS}
    values['group_weights']={'Operations':70,'Finance':30}
    for i,goal in enumerate(values['goals']):
        group='Operations' if i<6 else 'Finance'; goal['group']=group; goal['weight']=round(goal['weight']/values['group_weights'][group]*100,2)
    values['goals'][0]['metric']='HR amended measurement retained'
    assignment={'_id':process.key(process.ASSIGNMENT,'solvit','grace'),'tenant_id':'solvit','employee_id':'grace','version':'a1','values':values,'source_version':'published-role'}
    db.system_settings.docs=[assignment,{'_id':ObjectId(),'tenant_id':'solvit','employee_id':'other','version':'other-v','values':deepcopy(values)}]
    db.performance_reviews.docs=[{'_id':ObjectId(),'id':'review','tenant_id':'solvit','employee_id':'grace','version':'r1','workflow_version':3,'cycle_year':2026,'cycle_type':'Year_End','status':'Self_Draft','section_a_kpis':deepcopy(values['goals']),'group_weights':deepcopy(values['group_weights'])}]
    async def start_session(): return Session(db)
    db.client=SimpleNamespace(start_session=start_session)
    return db


def test_preview_is_read_only_and_keeps_targets_measurements_and_ids():
    db=fixture(); before=deepcopy(db.system_settings.docs)
    plan=run(repair.prepare(db)); values=repair.corrected_values(plan[1]['values'])
    assert [g['weight'] for g in values['goals']]==[15,10,15,15,10,5,10,10,10]
    assert values['group_weights']=={} and all(g['group']=='' for g in values['goals'])
    for old,new in zip(before[0]['values']['goals'],values['goals']):
        assert {k:v for k,v in old.items() if k not in {'weight','group'}}=={k:v for k,v in new.items() if k not in {'weight','group'}}
    assert db.system_settings.docs==before and not db.audit_logs.docs and not db.removed_employee_records.docs


def test_apply_updates_only_grace_and_untouched_review_with_backups_and_audit():
    db=fixture(); other=deepcopy(db.system_settings.docs[1]); digest=repair.fingerprint(run(repair.prepare(db)))
    result=run(repair.apply(db,digest))
    assert result['status']=='corrected_and_verified' and result['changed_records']==2
    assert db.system_settings.docs[1]==other
    assert db.performance_reviews.docs[0]['kpi_assignment_version']==db.system_settings.docs[0]['version']
    assert len(db.removed_employee_records.docs)==2 and len(db.audit_logs.docs)==1 and not db.notifications.docs
    digest=repair.fingerprint(run(repair.prepare(db)))
    assert run(repair.apply(db,digest))['status']=='already_applied'
    assert len(db.audit_logs.docs)==1


@pytest.mark.parametrize('update',[{'status':'Self_Submitted'},{'self_assessment':{'actuals':{'some':'answer'}}}])
def test_started_or_submitted_assessments_stop_the_repair_without_writes(update):
    db=fixture(); db.performance_reviews.docs[0].update(update); before=deepcopy(db.system_settings.docs)
    with pytest.raises(HTTPException): run(repair.prepare(db))
    assert db.system_settings.docs==before and not db.audit_logs.docs


def test_stale_fingerprint_fails_without_changing_assignment():
    db=fixture(); digest=repair.fingerprint(run(repair.prepare(db)))
    db.system_settings.docs[0]['version']='concurrent-update'
    with pytest.raises(HTTPException): run(repair.apply(db,digest))
    assert db.system_settings.docs[0]['version']=='concurrent-update'
    assert not db.removed_employee_records.docs and not db.integrity_locks.docs


def test_transaction_rolls_back_if_review_write_fails():
    db=fixture(); before=deepcopy(db.system_settings.docs); digest=repair.fingerprint(run(repair.prepare(db)))
    with patch.object(db.performance_reviews,'update_one',side_effect=RuntimeError('Synthetic transaction failure')):
        with pytest.raises(RuntimeError): run(repair.apply(db,digest))
    assert db.system_settings.docs==before and not db.removed_employee_records.docs and not db.audit_logs.docs


def test_ambiguous_objective_or_wrong_person_prevents_any_repair():
    db=fixture(); db.employees.docs[0]['full_name']='Another person'
    with pytest.raises(HTTPException): run(repair.prepare(db))
    db=fixture(); db.system_settings.docs[0]['values']['goals'][0]['objective']='Unrecognised KPI'
    with pytest.raises(HTTPException): run(repair.prepare(db))



def test_deployment_correction_runs_once_and_does_not_overwrite_later_hr_amendments():
    from utils import approved_kpi_correction
    db=fixture()
    assert run(approved_kpi_correction.run(db))=='applied'
    assert [g['weight'] for g in db.system_settings.docs[0]['values']['goals']]==[15,10,15,15,10,5,10,10,10]
    db.system_settings.docs[0]['values']['goals'][0]['weight']=14
    assert run(approved_kpi_correction.run(db))=='applied'
    assert db.system_settings.docs[0]['values']['goals'][0]['weight']==14
    assert len(db.audit_logs.docs)==1 and not db.notifications.docs


def test_deployment_reports_protected_reviews_without_changing_records():
    from utils import approved_kpi_correction
    db=fixture(); db.performance_reviews.docs[0]['status']='Self_Submitted'
    before=deepcopy(db.system_settings.docs)
    assert run(approved_kpi_correction.run(db))=='needs_review'
    assert db.system_settings.docs==before and not db.audit_logs.docs
