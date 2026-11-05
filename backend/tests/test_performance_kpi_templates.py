from copy import deepcopy
from unittest.mock import AsyncMock, patch
import pytest
from bson import ObjectId
from fastapi import HTTPException
from utils import performance_kpi_templates as service
from .test_performance_workflows import fixture as base_fixture, create, run
from .integrity_fakes import Collection


def fixture():
    db, users = base_fixture(); db.system_settings = Collection()
    return db, users


def body():
    return {'name': 'Synthetic standard KPIs', 'expected_version': None,
            'goals': [{'objective': f'Objective {i}', 'metric': 'Verified measure', 'target': 'HR approved target'} for i in range(3)]}


def setup():
    db, users = fixture()
    row = create(db, users)
    template = run(service.save(db, users['hr'], body()))
    return db, users, row, template


def apply_body(row, template):
    return {'review_ids': [row['id']], 'version': template['version'], 'due_on': '2026-10-20'}


@pytest.mark.parametrize('actor', ['staff', 'manager', 'finance', 'other'])
def test_template_operations_are_hr_only(actor):
    db, users = fixture()
    for action in (service.load(db, users[actor]), service.save(db, users[actor], body()), service.apply(db, users[actor], {})):
        with pytest.raises(HTTPException) as error: run(action)
        assert error.value.status_code == 403
    assert not db.system_settings.docs and not db.audit_logs.docs


def test_saved_template_is_tenant_scoped_versioned_and_audited():
    db, users = fixture(); assert run(service.load(db, users['hr'])) is None
    template = run(service.save(db, users['hr'], body()))
    assert run(service.load(db, users['hr'])) == template
    assert run(service.load(db, {**users['hr'], 'tenant_id': 'other-tenant'})) is None
    with pytest.raises(HTTPException) as error: run(service.save(db, users['hr'], body()))
    assert error.value.status_code == 409
    updated = run(service.save(db, users['hr'], {**body(), 'expected_version': template['version'], 'name': 'Updated standard'}))
    assert updated['version'] != template['version']
    assert db.audit_logs.docs[-1]['event'] == 'performance.kpi_template.saved'


@pytest.mark.parametrize('change', [ {'goals': []}, {'goals': body()['goals'] * 2},
    {'goals': [body()['goals'][0]] * 3}, {'name': ''}, {'goals': [{'objective': 'Incomplete'}] * 3}, {'scores': [1, 2, 3]}])
def test_invalid_templates_never_write(change):
    db, users = fixture()
    with pytest.raises(HTTPException): run(service.save(db, users['hr'], {**body(), **change}))
    assert not db.system_settings.docs and not db.audit_logs.docs


def test_apply_copies_goals_once_and_keeps_copies_independent_of_later_template_edits():
    db, users, row, template = setup()
    with patch('utils.performance_workflows.notify', new=AsyncMock()) as notify:
        result = run(service.apply(db, users['hr'], apply_body(row, template)))
        assert result == {'applied': [row['id']], 'skipped': []}
        notify.assert_awaited_once()
    stored = deepcopy(db.performance_reviews.docs[0]['section_a_kpis'])
    assert len(stored) == 3 and len({g['id'] for g in stored}) == 3
    assert all(g['due_on'] == '2026-10-20' and g['progress'] == 0 for g in stored)
    assert db.audit_logs.docs[-1]['event'] == 'performance.goals.template_assigned'
    again = run(service.apply(db, users['hr'], apply_body(row, template)))
    assert not again['applied'] and len(again['skipped']) == 1
    run(service.save(db, users['hr'], {**body(), 'expected_version': template['version'], 'name': 'Next version'}))
    assert db.performance_reviews.docs[0]['section_a_kpis'] == stored


@pytest.mark.parametrize('changes', [{'status': 'Self_Submitted'}, {'status': 'Completed'}, {'goals_acknowledged_at': '2026-10-02'},
    {'section_a_kpis': [{'id': 'existing', 'objective': 'Preserve this'}]}, {'cycle_type': 'Probation'}, {'workflow_version': 0}, {'employee_id': 'hr'}])
def test_locked_historical_probation_existing_and_own_reviews_are_preserved(changes):
    db, users, row, template = setup()
    db.performance_reviews.docs[0].update(changes)
    before = deepcopy(db.performance_reviews.docs)
    result = run(service.apply(db, users['hr'], apply_body(row, template)))
    assert not result['applied'] and len(result['skipped']) == 1
    assert db.performance_reviews.docs == before


def test_bulk_apply_reports_skipped_reviews_and_rejects_foreign_tenant_records():
    db, users, row, template = setup()
    second = {**deepcopy(db.performance_reviews.docs[0]), '_id': ObjectId(), 'id': 'foreign-review', 'tenant_id': 'other-tenant'}
    run(db.performance_reviews.insert_one(second))
    result = run(service.apply(db, users['hr'], {**apply_body(row, template), 'review_ids': [row['id'], 'foreign-review']}))
    assert result['applied'] == [row['id']] and result['skipped'][0]['review_id'] == 'foreign-review'
    assert db.performance_reviews.docs[1]['section_a_kpis'] == []


@pytest.mark.parametrize('changes', [{'review_ids': []}, {'review_ids': ['x', 'x']}, {'review_ids': ['x'] * 101},
    {'due_on': 'bad'}, {'version': 'stale'}, {'employee_id': 'forged'}])
def test_invalid_or_stale_apply_never_changes_reviews(changes):
    db, users, row, template = setup(); before = deepcopy(db.performance_reviews.docs)
    with pytest.raises(HTTPException): run(service.apply(db, users['hr'], {**apply_body(row, template), **changes}))
    assert db.performance_reviews.docs == before
