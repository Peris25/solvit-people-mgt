from datetime import date
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException
import pytest

from utils import performance_v3 as process, performance_v3_peers as peers
from .integrity_fakes import Collection
from .test_profile_self_service import fixture, run


def configured():
    db, users = fixture()
    db.performance_peer_tasks = Collection([{'_id': ObjectId(), 'id': 'task', 'tenant_id': 'solvit',
        'reviewer_employee_id': 'other', 'employee_id': 'staff', 'review_id': 'review',
        'cycle_id': 'cycle', 'status': 'Assigned', 'due_on': '2026-11-07'}])
    db.performance_peer_responses = Collection()
    return db, users


def payload(): return {'scores': [8] * 5, 'retain': 10, 'relationship': 'Peer', 'comment': 'Synthetic example'}


@pytest.mark.parametrize('actor', ['staff', 'manager', 'hr', 'finance'])
def test_only_assigned_reviewer_can_submit(actor):
    db, users = configured()
    with pytest.raises(HTTPException): run(peers.submit(db, users[actor], 'task', payload()))
    assert not db.performance_peer_responses.docs


def test_response_contains_no_author_and_duplicate_submission_is_blocked():
    db, users = configured()
    with patch.object(process, 'cycle', AsyncMock(return_value={'status': 'Open', 'starts_on': '2026-11-01'})), \
         patch.object(process, 'today', return_value=date(2026, 11, 2)):
        assert run(peers.submit(db, users['other'], 'task', payload())) == {'status': 'Submitted'}
        with pytest.raises(HTTPException): run(peers.submit(db, users['other'], 'task', payload()))
    assert len(db.performance_peer_responses.docs) == 1
    response = db.performance_peer_responses.docs[0]
    assert not {'reviewer_employee_id', 'actor_id', 'user_id', 'submitted_at', 'task_id'} & set(response)
    visible = run(peers.listing(db, users['other']))
    assert visible[0]['status'] == 'Submitted' and 'scores' not in visible[0]


def test_expired_window_and_interrupted_claim_fail_closed():
    db, users = configured()
    with patch.object(process, 'cycle', AsyncMock(return_value={'status': 'Open', 'starts_on': '2026-11-01'})), \
         patch.object(process, 'today', return_value=date(2026, 11, 8)):
        with pytest.raises(HTTPException): run(peers.submit(db, users['other'], 'task', payload()))
    db.performance_peer_tasks.docs[0]['status'] = 'Submitting'
    with pytest.raises(HTTPException): run(peers.submit(db, users['other'], 'task', payload()))
    assert not db.performance_peer_responses.docs


def test_foreign_tenant_cannot_read_assignments():
    db, users = configured()
    with pytest.raises(HTTPException):
        run(peers.submit(db, {**users['other'], 'tenant_id': 'foreign'}, 'task', payload()))
    assert not db.performance_peer_responses.docs
