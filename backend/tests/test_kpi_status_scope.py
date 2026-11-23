from copy import deepcopy
from types import SimpleNamespace
import pytest
from utils import performance_v3 as process, approved_kpi_scope_correction as correction
from .test_grace_kpi_repair import DB, SessionCollection, Session
from .test_profile_self_service import run
from .integrity_fakes import employee
from .test_performance_v3_end_to_end import configured


class ScopedCollection(SessionCollection):
    def find(self, query=None, projection=None, **kwargs):
        return super().find(query, projection)


def fixture(state='Active', onboarding=None, scope='Probation'):
    person = employee('staff', 'staff@example.com', lifecycle_state=state, role_title='IT Support')
    if onboarding: person['onboarding_recorded_status'] = onboarding
    db = DB([person])
    for name in ('employees', 'system_settings', 'performance_reviews', 'removed_employee_records', 'audit_logs', 'notifications'):
        setattr(db, name, ScopedCollection(getattr(db,name).docs if hasattr(db,name) else []))
    # Complete approved role goals, independent of the test employee lifecycle.
    values = deepcopy(next(r for r in process.library.catalogue() if r['role_id']=='it-support'))
    values['scope'] = scope
    db.system_settings.docs = [{'_id':process.key(process.ASSIGNMENT,'solvit','staff'), 'tenant_id':'solvit',
                               'employee_id':'staff', 'version':'v1', 'values':values}]
    async def start_session(): return Session(db)
    db.client = SimpleNamespace(start_session=start_session)
    return db, person


@pytest.mark.parametrize('state,onboarding,expected', [('Active',None,'Annual'), ('Probation',None,'Probation'),
    ('Onboarding',None,'Probation'), ('Active','In_Progress','Probation'), ('Active','Completed','Annual'), ('On_Leave',None,'Annual')])
def test_scope_uses_employee_status_not_template_scope(state,onboarding,expected):
    db, person = fixture(state,onboarding)
    assert process.employee_kpi_scope(person)==expected


@pytest.mark.parametrize('state,onboarding,before,after', [('Active',None,'Probation','Annual'),
    ('Probation',None,'Annual','Probation'), ('Active','In_Progress','Annual','Probation')])
def test_correction_preserves_all_kpis_and_status_and_is_idempotent(state,onboarding,before,after):
    db, person = fixture(state,onboarding,before)
    original = deepcopy(db.system_settings.docs[0]); original_person=deepcopy(person)
    assert run(correction.correct_employee(db,person))=='corrected'
    saved=run(process.assignment(db,person))
    assert saved['values']=={**original['values'],'scope':after}
    assert db.employees.docs[0]==original_person
    assert db.removed_employee_records.docs[0]['original']==original
    assert len(db.audit_logs.docs)==1 and not db.notifications.docs and not db.performance_reviews.docs
    # A later HR edit is never overwritten by the one-time repair.
    db.system_settings.docs[0]['values']['notes']='Later HR edit'
    assert run(correction.correct_employee(db,person))=='already_applied'
    assert db.system_settings.docs[0]['values']['notes']=='Later HR edit'


def test_started_reviews_are_left_for_hr_and_probation_status_blocks_annual():
    db, person=fixture('Probation',scope='Annual')
    db.performance_reviews.docs=[{'employee_id':'staff','status':'Self_Draft','self_assessment':{'draft':True}}]
    before=deepcopy(db.system_settings.docs)
    assert run(correction.correct_employee(db,person))=='started_review'
    assert db.system_settings.docs==before and not db.audit_logs.docs
    problems,_=run(process.review_readiness(db,person,run(process.assignment(db,person))))
    assert any('Use Create probation review' in issue for issue in problems)


def test_transaction_failure_rolls_back_assignment_and_backup():
    db, person=fixture()
    before=deepcopy(db.system_settings.docs)
    async def broken(*args,**kwargs): raise RuntimeError('Synthetic audit failure')
    db.audit_logs.insert_one=broken
    with pytest.raises(RuntimeError): run(correction.correct_employee(db,person))
    assert db.system_settings.docs==before and not db.removed_employee_records.docs


@pytest.mark.parametrize('state,source_scope,expected', [('Active','Probation','Annual'),('Probation','Annual','Probation')])
def test_new_hr_assignment_uses_employee_status_and_keeps_approved_role_goals(state,source_scope,expected):
    db,users,_,_=configured()
    person=db.employees.docs[0]; person['lifecycle_state']=state
    db.performance_reviews.docs=[]
    source=next(r for r in db.system_settings.docs if r.get('category')=='performance_role_kpi_library')
    source['published_values']['scope']=source_scope
    before=deepcopy(source['published_values'])
    saved=run(process.assignment(db,person))
    result=run(process.assign(db,users['hr'],'staff',{'role_id':'it-support','expected_version':saved['version'],'reason':'HR approved role assignment by employee status'}))
    assert result['values']=={**before,'scope':expected}
    assert source['published_values']==before
