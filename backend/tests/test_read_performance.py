"""Request-local read performance without cross-request permission caches."""
import asyncio
from unittest.mock import patch
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
