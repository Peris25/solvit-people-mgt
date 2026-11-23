"""HR-authorized status-based correction; preserves approved role goals and reviews.

Each employee is processed once with recovery copies, an audit marker and an
atomic transaction. No review, notification or employment status is changed.
"""
from copy import deepcopy
import logging
import uuid
from utils import performance_v3 as process
from utils.employee_integrity import integrity_write

logger = logging.getLogger(__name__)


def marker(employee):
    return process.key('approved-kpi-status-scope-20261123', process.tenant_of(employee), process.employee_key(employee))


async def correct_employee(db, employee):
    async with integrity_write(db):
        if await db.audit_logs.find_one({'_id': marker(employee)}): return 'already_applied'
        saved = await process.assignment(db, employee)
        if not saved or not saved.get('version'): return 'needs_assignment'
        values = saved.get('values') or {}
        if values.get('scope') not in {'Annual', 'Probation'}: return 'needs_review'
        expected = process.employee_kpi_scope(employee)
        if values['scope'] == expected: return 'already_correct'
        try:
            if process.library.issues(values): return 'needs_review'
        except (KeyError, TypeError, ValueError): return 'needs_review'
        review_query = process.scoped(employee, {'employee_id': {'$in': process.reference_ids(employee)},
                                                'status': {'$nin': ['Completed', 'Archived', 'Cancelled']}})
        reviews = await db.performance_reviews.find(review_query).to_list(None)
        if any(r.get('status') not in {'Draft', 'Self_Draft'} or r.get('self_assessment') is not None or r.get('manager_assessment') is not None for r in reviews):
            return 'started_review'
        after = deepcopy(values); after['scope'] = expected
        now = process.flow.now()
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                current_employee = await db.employees.find_one({'_id': employee['_id']}, session=session)
                current = await db.system_settings.find_one({'_id': saved['_id']}, session=session)
                if current_employee != employee or current != saved:
                    raise RuntimeError('Employee or KPI assignment changed during correction')
                # Recheck review state in the same transaction; never rewrite an assessment.
                current_reviews = await db.performance_reviews.find(review_query, session=session).to_list(None)
                if current_reviews != reviews: raise RuntimeError('Reviews changed during correction')
                await db.removed_employee_records.insert_one({'tenant_id': process.tenant_of(employee), 'source_collection': 'system_settings',
                    'original': saved, 'repair_id': str(marker(employee)), 'created_at': now}, session=session)
                result = await db.system_settings.update_one({'_id': saved['_id'], 'version': saved['version']}, {'$set': {
                    'values': after, 'version': str(uuid.uuid4()), 'updated_at': now,
                    'updated_by': 'operator:hr-approved-status-scope'}}, session=session)
                if result.modified_count != 1: raise RuntimeError('KPI scope update not confirmed')
                await db.audit_logs.insert_one({'_id': marker(employee), 'tenant_id': process.tenant_of(employee),
                    'event': 'performance.kpi_scope.corrected_from_employee_status', 'entity_id': process.employee_key(employee),
                    'actor_id': 'operator:hr-approved-status-scope', 'timestamp': now,
                    'metadata': {'before_scope': values['scope'], 'after_scope': expected,
                                 'lifecycle_state': employee.get('lifecycle_state') or employee.get('status'),
                                 'onboarding_status': employee.get('onboarding_recorded_status'),
                                 'reason': 'HR instructed probation/onboarding staff retain Probation KPIs; other eligible staff use Annual KPIs.'}}, session=session)
        verified = await process.assignment(db, employee)
        if verified.get('values') != after: raise RuntimeError('Saved KPI scope could not be verified')
        return 'corrected'


async def run(db):
    counts = {}
    try:
        employees = await db.employees.find(process.tenant_query('solvit')).to_list(None)
        for employee in employees:
            if not process.enabled(employee) or not process.fte(employee) or process.md(employee): continue
            status = await correct_employee(db, employee)
            counts[status] = counts.get(status, 0) + 1
        return {'status': 'needs_review' if any(counts.get(k) for k in ('needs_assignment', 'needs_review', 'started_review')) else 'applied', 'counts': counts}
    except Exception as error:
        logger.error('Status-based KPI correction could not be completed (%s). Inspect audit before retrying.', type(error).__name__)
        return {'status': 'unconfirmed', 'counts': counts}
