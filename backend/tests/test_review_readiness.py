from copy import deepcopy
from datetime import date
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from utils import performance_v3 as process
from .test_performance_v3_end_to_end import configured
from .test_profile_self_service import run


def test_setup_and_send_share_exact_readiness_and_do_not_send_on_failure():
    db, users, cycle, _ = configured()
    staff = db.employees.docs[0]
    saved = run(process.assignment(db, staff))
    saved['values']['scope'] = 'Probation'
    saved['values']['goals'][0]['weight'] = 0
    run(db.system_settings.update_one({'_id': saved['_id']}, {'$set': {'values': saved['values']}}))
    staff['line_manager_id'] = 'missing-manager'
    setup = run(process.setup(db, users['hr']))
    visible = next(e for e in setup['employees'] if e['id'] == 'staff')
    assert not visible['review_ready'] and visible['assignment']
    assert any('Probation' in issue for issue in visible['review_issues'])
    assert any('positive weight' in issue for issue in visible['review_issues'])
    assert any('Manager not found' in issue for issue in visible['review_issues'])
    before = deepcopy(db.notifications.docs)
    with patch.object(process, 'today', return_value=date(2026, 11, 30)):
        with pytest.raises(HTTPException) as failure:
            run(process.open_cycle(db, users['hr'], cycle['id'], ['staff']))
    for issue in visible['review_issues']:
        assert issue in failure.value.detail
    assert db.notifications.docs == before


def test_valid_assignment_is_ready_and_setup_does_not_modify_it():
    db, users, _, _ = configured()
    before = deepcopy(db.system_settings.docs)
    setup = run(process.setup(db, users['hr']))
    staff = next(e for e in setup['employees'] if e['id'] == 'staff')
    assert staff['review_ready'] and staff['review_issues'] == []
    assert db.system_settings.docs == before
