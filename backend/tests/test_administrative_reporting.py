"""Read-only synthetic report/audit authorization, privacy and export regressions."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import csv,io,json
import pytest
from bson import ObjectId
from fastapi import HTTPException
from openpyxl import load_workbook
from utils import administrative_reporting as service
from utils.access_matrix import RUNTIME_OVERRIDES
from routes import reporting,exports,settings,masters_settings,email_delivery
from .test_benefits_payroll import fixture as base_fixture
from .integrity_fakes import Collection,employee,account

def run(coro):return asyncio.run(coro)
def fixture():
    db,users=base_fixture()
    for name in (*service.AUDIT_SOURCES,'onboarding_tasks','leave_balances','pay_bands','budget_allocations','email_log','email_send_log','solvers','form_submissions'):setattr(db,name,Collection())
    for role in ('it_admin','executive','solver'):
        row=employee(role,role+'@example.com',start_date='2020-01-01');db.employees.docs.append(deepcopy(row))
        owner=account(role+'@example.com',employee_id=role,role=role,full_name='Synthetic '+role);db.users.docs.append(deepcopy(owner));users[role]={**owner,'id':str(owner['_id'])}
    return db,users

def insert(collection,**values):run(collection.insert_one({'id':str(ObjectId()),'tenant_id':'solvit',**values}));return collection.docs[-1]
def event(db,source='audit_logs',**values):return insert(getattr(db,source),event='employee.updated',timestamp='2026-10-01T09:00:00Z',actor_id='legacy-actor',metadata={'password':'SECRET_PASSWORD','bank_account':'SECRET_BANK','before':{'salary':999}},**values)

@pytest.mark.parametrize('actor',['staff','other','manager','finance','executive','solver'])
def test_ordinary_and_non_audit_roles_cannot_read_audit(actor):
    db,users=fixture();event(db)
    with pytest.raises(HTTPException):run(service.audit_feed(db,users[actor]))

@pytest.mark.parametrize('actor',['staff','other','solver','it_admin'])
@pytest.mark.parametrize('kind',list(service.KINDS))
def test_non_reporting_roles_cannot_read_or_export_employee_reports(actor,kind):
    db,users=fixture()
    with pytest.raises(HTTPException):run(service.report_data(db,users[actor],kind,export=True))


def test_audit_federates_existing_sources_with_safe_payloads_and_no_writes():
    db,users=fixture()
    for source in service.AUDIT_SOURCES:event(db,source)
    before={source:deepcopy(getattr(db,source).docs) for source in service.AUDIT_SOURCES}
    result=run(service.audit_feed(db,users['it_admin']))
    assert result['total']==6 and len({row['id'] for row in result['items']})==6
    assert set(row['source'] for row in result['items'])==set(service.AUDIT_SOURCES)
    assert 'SECRET_' not in str(result) and 'metadata' not in str(result)
    assert all(getattr(db,source).docs==before[source] for source in before)


def test_audit_tenant_dates_event_module_and_authorized_actor_filtering():
    db,users=fixture();event(db)
    insert(db.audit_logs,event='leave.approved',timestamp='2026-10-02T10:00:00+03:00',actor_id=users['hr']['id'])
    insert(db.audit_logs,tenant_id='foreign',event='employee.updated',timestamp='2026-10-02T10:00:00Z')
    all_rows=run(service.audit_feed(db,users['it_admin']))
    actor=next(row['actor_id'] for row in all_rows['items'] if row['module']=='M18')
    result=run(service.audit_feed(db,users['it_admin'],date_from='2026-10-02',date_to='2026-10-02',event_type='leave.approved',module='M18',actor=actor))
    assert result['total']==1 and result['items'][0]['event']=='leave.approved'
    assert run(service.audit_feed(db,users['it_admin'],actor='forged'))['total']==0


def test_legacy_missing_actor_date_and_raw_event_are_safe_and_filters_exclude_undated():
    db,users=fixture();insert(db.audit_log,action='private account = SECRET',entity='SECRET_BANK',timestamp=None)
    result=run(service.audit_feed(db,users['it_admin']))
    assert result['items'][0]['event']=='legacy_event' and result['items'][0]['actor_name']=='Unknown / historical actor'
    assert 'SECRET' not in str(result) and result['missing_dates']==1
    assert run(service.audit_feed(db,users['it_admin'],date_from='2026-01-01'))['items']==[]


def test_audit_pagination_is_stable_and_does_not_confuse_duplicate_public_ids():
    db,users=fixture()
    for i in range(5):insert(db.audit_logs,id='same-legacy-id',event='employee.updated',timestamp=f'2026-10-0{i+1}T00:00:00Z')
    first=run(service.audit_feed(db,users['it_admin'],limit=2));second=run(service.audit_feed(db,users['it_admin'],limit=2,offset=2))
    assert first['total']==5 and len({row['id'] for row in first['items']+second['items']})==4
    assert first['items'][0]['timestamp']>second['items'][0]['timestamp']


def test_hr_audit_cannot_read_security_or_revoked_module_events():
    db,users=fixture();event(db);insert(db.audit_logs,event='auth.login',timestamp='2026-10-01T00:00:00Z')
    with patch.dict(RUNTIME_OVERRIDES,{('M01','hr_admin'):None}):
        with pytest.raises(HTTPException):run(service.audit_feed(db,users['hr']))
    result=run(service.audit_feed(db,users['hr']))
    assert all(row['module']!='Security' for row in result['items'])


def test_manager_report_uses_only_direct_reports_and_never_private_employee_fields():
    db,users=fixture();db.employees.docs[0].update(current_salary_kes=123456,bank_account='SECRET_BANK',national_id_number='SECRET_ID',medical_notes='SECRET_MEDICAL',disciplinary_notes='SECRET_DISCIPLINARY')
    result=run(service.report_data(db,users['manager'],'employees'))
    assert [row['employee_id'] for row in result['items']]==['staff'] and result['scope']=='direct_reports'
    assert 'SECRET' not in str(result) and 'current_salary_kes' not in str(result)

@pytest.mark.parametrize('reference',['canonical','string','native'])
def test_canonical_and_legacy_employee_foreign_keys_resolve(reference):
    db,users=fixture();emp=db.employees.docs[0]
    key=emp['id'] if reference=='canonical' else str(emp['_id']) if reference=='string' else emp['_id']
    insert(db.training_requests,employee_id=key,training_name='Synthetic learning',status='Approved',business_justification='SECRET_NOTE')
    result=run(service.report_data(db,users['manager'],'training'))
    assert result['total']==1 and result['items'][0]['employee_id']=='staff' and 'SECRET_NOTE' not in str(result)


def test_native_manager_reference_is_not_lost():
    db,users=fixture();manager=next(row for row in db.employees.docs if row['id']=='manager');db.employees.docs[0]['line_manager_id']=manager['_id']
    assert run(service.report_data(db,users['manager'],'employees'))['total']==1


def test_executive_receives_only_aggregate_rows_including_export():
    db,users=fixture();result=run(service.report_data(db,users['executive'],'employees',export=True))
    assert result['summary_only'] and all(set(row)=={'department','status','count'} for row in result['items'])
    assert 'employee_id' not in service.csv_bytes(result['items']).decode('utf-8')
    with pytest.raises(HTTPException):run(service.report_data(db,users['executive'],'benefits'))


def test_executive_leave_summary_obeys_saved_team_permission():
    db,users=fixture();db.employees.docs[0]['line_manager_id']='executive'
    insert(db.leave_requests,employee_id='staff',status='Approved',start_date='2026-10-01',end_date='2026-10-03')
    insert(db.leave_requests,employee_id='other',status='Approved',start_date='2026-10-01',end_date='2026-10-03')
    result=run(service.report_data(db,users['executive'],'leave'))
    assert result['scope']=='direct_reports' and sum(row['count'] for row in result['items'])==1


def test_department_dates_and_leave_overlap_filters_have_explicit_semantics():
    db,users=fixture()
    insert(db.leave_requests,employee_id='staff',status='Approved',start_date='2026-09-28',end_date='2026-10-03',reason='SECRET_REASON',medical_certificate='SECRET_FILE')
    result=run(service.report_data(db,users['hr'],'leave',department='operations',date_from='2026-10-01',date_to='2026-10-02'))
    assert result['total']==1 and 'SECRET' not in str(result)
    assert run(service.report_data(db,users['hr'],'leave',department='Unknown'))['items']==[]
    with pytest.raises(HTTPException):run(service.report_data(db,users['hr'],'leave',date_from='2026-10-02',date_to='2026-01-01'))


def test_ambiguous_or_orphaned_employee_links_are_counted_not_overwritten():
    db,users=fixture();duplicate=employee('staff','duplicate@example.com',start_date='2020-01-01');run(db.employees.insert_one(duplicate))
    insert(db.training_requests,employee_id='staff',status='Approved');insert(db.training_requests,employee_id='missing',status='Approved')
    result=run(service.report_data(db,users['hr'],'training'))
    assert result['items']==[] and result['unresolved_records']>=2


def test_board_records_are_excluded_but_exited_history_is_preserved_for_hr():
    db,users=fixture();db.employees.docs[0]['board_only']=True;db.employees.docs[1]['lifecycle_state']='Exited'
    result=run(service.report_data(db,users['hr'],'employees'))
    assert 'staff' not in [row['employee_id'] for row in result['items']]
    assert next(row for row in result['items'] if row['employee_id']=='other')['status']=='Exited'


def test_saved_balances_are_not_recomputed_and_absent_balances_are_not_invented():
    db,users=fixture();assert run(service.report_data(db,users['hr'],'leave_balances'))['items']==[]
    insert(db.leave_balances,employee_id='staff',year=2026,Annual={'remaining':3.75},Sick={'remaining':9},bank_account='SECRET')
    before=deepcopy(db.leave_balances.docs);result=run(service.report_data(db,users['hr'],'leave_balances'))
    assert result['items'][0]['annual_remaining']==3.75 and result['items'][0]['sick_remaining']==9
    assert db.leave_balances.docs==before and 'SECRET' not in str(result)
    with pytest.raises(HTTPException):run(service.report_data(db,users['manager'],'leave_balances'))


def test_performance_report_preserves_task10_unreleased_self_score_privacy():
    db,users=fixture();insert(db.performance_reviews,employee_id='hr',status='HR_Reviewed',overall_score=1.234,manager_assessment={'private':'SECRET'})
    result=run(service.report_data(db,users['hr'],'performance'))
    assert result['items'][0]['overall_score'] is None and 'SECRET' not in str(result)


def test_finance_benefits_report_is_status_only_and_cannot_export_households():
    db,users=fixture();insert(db.benefit_requests,employee_id='staff',scheme_title='Approved scheme',status='Approved',dependants=[{'name':'SECRET_DEPENDANT'}],premium_kes=999,review_reason='SECRET_MEDICAL')
    result=run(service.report_data(db,users['finance'],'benefits',export=True))
    assert result['total']==1 and 'SECRET' not in str(result) and 'premium' not in str(result)
    with pytest.raises(HTTPException):run(service.report_data(db,users['manager'],'benefits'))


def test_report_module_revocation_and_tenant_isolation_apply_to_exports_too():
    db,users=fixture();run(db.employees.insert_one(employee('foreign','foreign@example.com',tenant_id='foreign')))
    result=run(service.report_data(db,users['hr'],'employees',export=True))
    assert all(row['employee_id']!='foreign' for row in result['items'])
    with patch.dict(RUNTIME_OVERRIDES,{('M01','hr_admin'):None}):
        with pytest.raises(HTTPException):run(service.report_data(db,users['hr'],'employees',export=True))

@pytest.mark.parametrize('value',['=HYPERLINK("bad")',' +SUM(1,2)','-cmd','@SUM(1)','\t=cmd','\ufeff=cmd'])
def test_csv_and_excel_cells_cannot_execute_formulas(value):
    payload=[{'employee_name':value,'count':-2}]
    row=list(csv.DictReader(io.StringIO(service.csv_bytes(payload).decode('utf-8-sig'))))[0]
    assert row['employee_name'].startswith("'") and row['count']=='-2'
    book=load_workbook(BytesIO(service.xlsx_bytes(payload)),data_only=False)
    cell=book.active['A2'];assert cell.data_type=='s' and cell.value.startswith("'")


def test_export_and_view_fail_closed_if_access_audit_cannot_be_written():
    db,users=fixture();before=deepcopy(db.employees.docs)
    with patch.object(reporting,'get_db',return_value=db),patch.object(reporting,'get_current_user',return_value=users['hr']),patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('Synthetic audit outage')):
        with pytest.raises(HTTPException) as error:run(reporting.export('employees','csv',None))
    assert error.value.status_code==503 and db.employees.docs==before


def test_legacy_employee_export_no_longer_exposes_salary_identifiers_or_it_access():
    db,users=fixture();db.employees.docs[0].update(current_salary_kes=123456,national_id_number='SECRET_ID',kra_pin='SECRET_PIN')
    with patch.object(exports,'get_db',return_value=db),patch.object(exports,'get_current_user',return_value=users['hr']):result=run(exports.export_employees(None))
    assert b'SECRET' not in result.body and b'current_salary' not in result.body and result.headers['cache-control']=='no-store'
    with patch.object(exports,'get_db',return_value=db),patch.object(exports,'get_current_user',return_value=users['it_admin']):
        with pytest.raises(HTTPException):run(exports.export_employees(None))


def test_legacy_audit_readers_redact_configuration_values_and_actor_emails():
    db,users=fixture();insert(db.settings_audit,category='email',field='password',old_value='SECRET_OLD',new_value='SECRET_NEW',changed_by=users['hr']['id'],changed_by_name='private@example.com')
    with patch.object(masters_settings,'get_db',return_value=db),patch.object(masters_settings,'get_current_user',return_value=users['it_admin']):result=run(masters_settings.get_audit_log(None))
    assert result[0]['old_value']=='[redacted]' and 'SECRET' not in str(result) and 'private@example.com' not in str(result)


def test_email_log_view_and_export_do_not_disclose_subjects_recipients_or_smtp_errors():
    db,users=fixture();insert(db.email_log,to='private@example.com',subject='SECRET_SALARY',template_key='comp.salary_review',status='failed',error='SECRET_SMTP_PASSWORD',sent_at='2026-10-01T00:00:00Z')
    with patch.object(email_delivery,'get_db',return_value=db),patch.object(email_delivery,'get_current_user',return_value=users['it_admin']):
        result=run(email_delivery.get_email_log(None));export=run(email_delivery.export_email_log_csv(None))
    assert 'SECRET' not in str(result) and 'private@example.com' not in str(result) and b'SECRET' not in export.body


def test_read_export_routes_do_not_offer_audit_mutation_or_raw_details():
    from server import app
    methods={method for route in app.routes if getattr(route,'path','').startswith('/api/reporting') for method in getattr(route,'methods',[])}
    assert methods=={'GET'}


def test_malformed_legacy_identifiers_cannot_leak_nested_private_payloads():
    db,users=fixture();db.employees.docs[0]['id']={'bank':'SECRET_BANK'}
    result=run(service.report_data(db,users['hr'],'employees'))
    assert 'SECRET' not in str(result) and result['unresolved_records']>=1
    db,users=fixture();insert(db.training_requests,id={'private':'SECRET'},employee_id='staff',status='Approved')
    assert 'SECRET' not in str(run(service.report_data(db,users['hr'],'training')))


def test_real_mongo_native_dates_foreign_keys_and_read_time_audit_federation():
    from .test_employee_integrity_mongo import local_database
    async def exercise():
        async with local_database() as db:
            seed,users=fixture();await db.employees.insert_many(deepcopy(seed.employees.docs));await db.users.insert_many(deepcopy(seed.users.docs))
            await db.audit_logs.insert_one({'tenant_id':'solvit','event':'employee.updated','timestamp':datetime(2026,10,1,tzinfo=timezone.utc),'metadata':{'bank':'SECRET'}})
            await db.audit_log.insert_one({'tenant_id':'solvit','action':'employee.created','timestamp':'2026-10-01T01:00:00Z'})
            result=await service.audit_feed(db,users['it_admin'],date_from='2026-10-01',date_to='2026-10-01')
            assert result['total']==2 and 'SECRET' not in str(result) and await db.audit_logs.count_documents({})==1
            await db.training_requests.insert_one({'employee_id':seed.employees.docs[0]['_id'],'tenant_id':'solvit','status':'Approved'})
            result=await service.report_data(db,users['manager'],'training')
            assert result['total']==1 and result['items'][0]['employee_id']=='staff'
    run(exercise())


def test_existing_applicant_exports_deny_it_executive_and_other_tenant_rows():
    from routes import solver_intake
    db,users=fixture();db.ineligible_applicants=Collection()
    insert(db.ineligible_applicants,full_name='=HYPERLINK("unsafe")',submitted_at='2026-10-01')
    insert(db.ineligible_applicants,tenant_id='foreign',full_name='SECRET_FOREIGN')
    with patch.object(solver_intake,'get_db',return_value=db),patch.object(solver_intake,'get_current_user',return_value=users['hr']):response=run(solver_intake.export_ineligible(None))
    assert b'SECRET_FOREIGN' not in response.body and b"'=HYPERLINK" in response.body and response.headers['cache-control']=='no-store'
    for role in ('it_admin','executive','staff'):
        with patch.object(solver_intake,'get_db',return_value=db),patch.object(solver_intake,'get_current_user',return_value=users[role]):
            with pytest.raises(HTTPException):run(solver_intake.export_ineligible(None))


def test_management_summary_reuses_only_authorized_modules_without_individual_rows():
    db,users=fixture();insert(db.benefit_requests,employee_id='staff',status='Approved',dependants=[{'name':'SECRET'}])
    for role in ('hr','executive','manager','finance'):
        result=run(service.report_data(db,users[role],'management',export=True))
        assert result['summary_only'] and 'employee_name' not in str(result['items']) and 'SECRET' not in str(result)
        assert all(service.report_allowed(users[role],row['report_kind']) for row in result['items'])
    with pytest.raises(HTTPException):run(service.report_data(db,users['staff'],'management'))


def test_probation_and_contract_reports_require_recorded_dates_and_preserve_history():
    db,users=fixture();assert run(service.report_data(db,users['hr'],'probation_dates'))['items']==[]
    db.employees.docs[0].update(probation_end_date='2026-10-20',contract_end_date='2026-11-01')
    before=deepcopy(db.employees.docs)
    assert run(service.report_data(db,users['manager'],'probation_dates',date_from='2026-10-01',date_to='2026-10-31'))['total']==1
    assert run(service.report_data(db,users['hr'],'contract_dates',date_from='2026-11-01',date_to='2026-11-30'))['total']==1
    assert db.employees.docs==before
