"""Request-local read performance without cross-request permission caches."""
import asyncio
from unittest.mock import patch, AsyncMock
import pytest
from fastapi import HTTPException
from utils.employee_integrity import employee_read_snapshot, find_employee
from utils.notification_centre import list_inbox
from .integrity_fakes import Database, employee
from .test_notification_centre import fixture, notice


def test_employee_reads_reuse_one_query_and_return_independent_records():
    db=Database([employee('one')],[])
    async def check():
        with patch.object(db.employees,'find',wraps=db.employees.find) as query:
            with employee_read_snapshot():
                first=await find_employee(db,'one'); first['full_name']='Local projection'
                for _ in range(39):
                    assert (await find_employee(db,'one'))['full_name'] != 'Local projection'
            assert query.call_count==1
            db.employees.docs[0]['full_name']='Updated between requests'
            with employee_read_snapshot():
                assert (await find_employee(db,'one'))['full_name']=='Updated between requests'
            assert query.call_count==2
    asyncio.run(check())


def test_writes_without_snapshot_recheck_identities_and_duplicate_references():
    db=Database([employee('one')],[])
    async def check():
        await find_employee(db,'one')
        db.employees.docs.append(employee('one',email='duplicate@example.com'))
        with pytest.raises(HTTPException) as exc: await find_employee(db,'one')
        assert exc.value.status_code==409
    asyncio.run(check())


def test_snapshot_does_not_cross_tenant_or_concurrent_request_boundaries():
    db=Database([employee('one',tenant_id='a'),employee('one',tenant_id='b')],[])
    async def request(tenant):
        with employee_read_snapshot():
            await asyncio.sleep(0)
            assert (await find_employee(db,'one',tenant))['tenant_id']==tenant
            assert await find_employee(db,'one','missing') is None
    async def check(): await asyncio.gather(request('a'),request('b'))
    asyncio.run(check())


def test_notification_checks_are_bounded_concurrent_and_preserve_counts_and_order():
    db,actors=fixture(); db.notifications.docs=[notice(created_at=f'2026-10-{day:02d}T10:00:00Z') for day in range(1,14)]
    active=peak=0
    async def authorize(db,user,row):
        nonlocal active,peak
        active+=1; peak=max(peak,active)
        await asyncio.sleep(0.001)
        active-=1
        if row['_id']==db.notifications.docs[0]['_id']: raise HTTPException(403,'Unrelated')
    async def related(*args): return None,None
    with patch('utils.notification_centre.authorize_recipient',side_effect=authorize),patch('utils.notification_centre.related_link',side_effect=related):
        result=asyncio.run(list_inbox(db,actors['staff'],limit=5))
    assert 1<peak<=6
    assert result['unread_count']==12 and result['total']==12 and len(result['items'])==5
    assert result['items'][0]['created_at'].startswith('2026-10-13')
    assert db.notifications.writes==0


def test_permission_configuration_reads_overlap_but_remain_fresh_per_request():
    from utils.access_matrix import read_runtime_state
    from .integrity_fakes import Cursor
    db = Database()
    active = peak = reads = 0
    class DelayedCursor(Cursor):
        async def to_list(self, length):
            nonlocal active, peak, reads
            active += 1; peak = max(peak, active); reads += 1
            await asyncio.sleep(.01)
            active -= 1
            return await super().to_list(length)
    with patch.object(db.permission_overrides, 'find', return_value=DelayedCursor([])), patch.object(db.custom_roles, 'find', return_value=DelayedCursor([])):
        assert asyncio.run(read_runtime_state(db)) == {'overrides': {}, 'roles': {}}
        asyncio.run(read_runtime_state(db))
    assert peak == 2 and reads == 4


def test_profile_section_reads_overlap_and_preserve_authorized_output():
    from routes import employees
    from .test_profile_self_service import fixture as profile_fixture
    from .integrity_fakes import Cursor
    db, actors = profile_fixture()
    active = peak = 0
    class DelayedCursor(Cursor):
        async def to_list(self, length):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            await asyncio.sleep(.01)
            active -= 1
            return await super().to_list(length)
    names = ('performance_reviews', 'leave_requests', 'recognitions', 'training_requests', 'disciplinary_cases', 'notifications')
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(patch.object(employees, 'get_db', return_value=db))
        stack.enter_context(patch.object(employees, 'get_current_user', AsyncMock(return_value=actors['hr'])))
        for name in names:
            stack.enter_context(patch.object(getattr(db, name), 'find', return_value=DelayedCursor([])))
        result = asyncio.run(employees.get_employee_profile('staff', object()))
    assert peak == 6
    assert result['employee']['id'] == 'staff'
    assert result['leave_history'] == [] and result['performance_history'] == []
    assert result['employee']['line_manager_name'] == 'manager'


def test_slow_smtp_does_not_block_other_api_tasks(monkeypatch):
    import threading
    from utils import email_service
    monkeypatch.setenv('OUTBOUND_EMAIL_ENABLED', 'true')
    started, release = threading.Event(), threading.Event()
    def slow_smtp(*args):
        started.set()
        assert release.wait(2), 'API event loop could not progress while SMTP was running'
    async def check():
        task = asyncio.create_task(email_service._attempt_send('', 0, '', '', '', '', '', '', object()))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            assert not task.done()
        finally:
            release.set()
            await task
    with patch.object(email_service, '_smtp_transaction', side_effect=slow_smtp):
        asyncio.run(check())
