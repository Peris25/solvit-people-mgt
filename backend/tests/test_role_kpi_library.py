from copy import deepcopy
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from utils import role_kpi_library as service
from .test_profile_self_service import fixture, run


def draft(db, user, role='it-support'):
    row = next(r for r in run(service.listing(db,user))['roles'] if r['role_id']==role)
    return {key:deepcopy(row[key]) for key in service.ENTRY_FIELDS}


def save(db,user,entry,version=None,action='draft',reason=''):
    return run(service.save(db,user,entry['role_id'],{'entry':entry,'expected_version':version,'action':action,'reason':reason}))


def approved(db,user):
    entry=draft(db,user);entry['approval_reference']='MD and line manager approval 12 November 2026'
    return entry


def test_reference_catalogue_is_read_only_and_does_not_modify_employees():
    db,users=fixture(); before=deepcopy(db.employees.docs)
    rows=run(service.listing(db,users['hr']))['roles']
    assert len(rows)==13 and sum(len(r['goals']) for r in rows)==110
    assert all(row['status']=='Draft' and row['version'] is None and row['issues'] for row in rows)
    assert db.employees.docs==before and not db.system_settings.docs


@pytest.mark.parametrize('actor',['staff','manager','other','finance'])
def test_library_is_hr_only(actor):
    db,users=fixture()
    with pytest.raises(HTTPException): run(service.listing(db,users[actor]))
    with pytest.raises(HTTPException): save(db,users[actor],approved(db,users['hr']))
    assert not db.system_settings.docs


def test_incomplete_drafts_persist_across_requests_and_tenants_are_isolated():
    db,users=fixture();entry=draft(db,users['hr']);entry['goals'][0].update(target='',weight=None)
    saved=save(db,users['hr'],entry)
    restored=next(row for row in run(service.listing(db,users['hr']))['roles'] if row['role_id']==entry['role_id'])
    assert restored['version']==saved['version'] and restored['goals'][0]['target']==''
    foreign=next(row for row in run(service.listing(db,{**users['hr'],'tenant_id':'foreign'}))['roles'] if row['role_id']==entry['role_id'])
    assert foreign['version'] is None and foreign['goals'][0]['target']


def test_publish_requires_approval_reference_and_exact_weights():
    db,users=fixture();entry=draft(db,users['hr'])
    with pytest.raises(HTTPException): save(db,users['hr'],entry,action='publish')
    entry['approval_reference']='MD and line manager approval'
    entry['goals'][0]['weight']=24
    with pytest.raises(HTTPException): save(db,users['hr'],entry,action='publish')
    assert not db.system_settings.docs
    entry['goals'][0]['weight']=25
    result=save(db,users['hr'],entry,action='publish')
    assert result['status']=='Published' and not result['issues']
    assert db.employees.writes==0 and db.performance_reviews.writes==0


def test_published_edit_requires_reason_and_preserves_previous_publication():
    db,users=fixture();entry=approved(db,users['hr']);published=save(db,users['hr'],entry,action='publish')
    entry['goals'][0]['target']='99%'
    with pytest.raises(HTTPException): save(db,users['hr'],entry,published['version'])
    result=save(db,users['hr'],entry,published['version'],reason='Approved change to diagnosis target')
    assert result['status']=='Draft' and result['has_published_version']
    assert db.system_settings.docs[0]['published_values']['goals'][0]['target']=='100%'
    assert db.audit_logs.docs[-1]['metadata']['reason']=='Approved change to diagnosis target'


def test_stale_version_and_audit_failure_preserve_saved_draft():
    db,users=fixture();entry=draft(db,users['hr']);saved=save(db,users['hr'],entry)
    entry['notes']='Second HR change'
    with pytest.raises(HTTPException) as error: save(db,users['hr'],entry)
    assert error.value.status_code==409
    before=deepcopy(db.system_settings.docs)
    with patch.object(db.audit_logs,'insert_one',side_effect=RuntimeError('Synthetic audit failure')):
        with pytest.raises(RuntimeError): save(db,users['hr'],entry,saved['version'])
    assert db.system_settings.docs==before


def test_split_groups_are_not_treated_as_two_hundred_percent():
    db,users=fixture();entry=draft(db,users['hr'],'finance-operations-manager')
    problems=service.issues(entry)
    assert 'Group weights must total 100%.' in problems
    assert not any('Finance KPI weights' in p or 'Operations KPI weights' in p for p in problems)
    assert all(value is None for value in entry['group_weights'].values())


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,{},-1,101])
def test_invalid_weights_are_rejected_even_in_drafts(value):
    db,users=fixture();entry=draft(db,users['hr']);entry['goals'][0]['weight']=value
    with pytest.raises(HTTPException): save(db,users['hr'],entry)


def test_custom_role_and_empty_kpi_drafts_can_be_saved():
    db,users=fixture();entry=draft(db,users['hr']);entry.update(role_id='custom-role',name='Custom role',goals=[],scope='Unconfirmed')
    assert save(db,users['hr'],entry)['status']=='Draft'
    with pytest.raises(HTTPException): save(db,users['hr'],entry,action='publish')


def test_api_rejects_staff_before_acquiring_integrity_lock():
    from routes import performance
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    db,users=fixture();request=SimpleNamespace(json=AsyncMock(return_value={}))
    with patch.object(performance,'get_current_user',new=AsyncMock(return_value=users['staff'])),patch.object(performance,'get_db') as database:
        with pytest.raises(HTTPException) as error: run(performance.save_role_kpis('it-support',request))
    assert error.value.status_code==403
    database.assert_not_called();request.json.assert_not_awaited()
