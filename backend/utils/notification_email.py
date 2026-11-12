"""Deliver new inbox items without requiring the recipient to open the portal.

The rollout boundary is durable, so restarts neither replay old inbox history nor
lose pending items. Per-event/mailbox claims and SMTP retries use email_routing.
"""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from utils.email_routing import action_email, eligible, portal_link
from utils.employee_integrity import normalize_email, tenant_of, tenant_query, find_employee, employee_key, email_query
from utils.notification_centre import list_inbox, date_value, storage_key
from utils.runtime_controls import background_jobs_enabled, outbound_email_enabled

logger = logging.getLogger(__name__)
ROLLOUT_ID = 'notification-email-rollout-v1'


async def initialize(db):
    marker = await db.system_settings.find_one({'_id': ROLLOUT_ID})
    if not marker:
        try:
            await db.system_settings.insert_one({'_id': ROLLOUT_ID, 'tenant_id': 'solvit',
                'enabled_at': datetime.now(timezone.utc).isoformat()})
        except DuplicateKeyError:
            pass
        marker = await db.system_settings.find_one({'_id': ROLLOUT_ID})
    return date_value(marker['enabled_at'])


def event_key(row):
    """Reuse claims owned by existing workflow delivery, including v3 reminders."""
    if row.get('email_event_key'):
        return row['email_event_key']
    data = row.get('data') or {}
    if data.get('performance_v3'):
        return 'performance-v3:' + storage_key(row)
    reference = data.get('performance_review_id')
    prefix = f'performance:{tenant_of(row)}:{reference}:'
    key = storage_key(row)
    event = data.get('performance_event')
    if reference and key.startswith(prefix) and event in {
        'created', 'performance.assessment.manager', 'performance.meeting.proposed', 'performance.meeting.scheduled'
    }:
        # The legacy sender handles HR roles, but not general_manager or the
        # employee's proposed-date notice; those need their own email claim.
        if event == 'performance.meeting.proposed' and row.get('recipient_id'):
            return 'notification:' + key
        if row.get('recipient_role') == 'general_manager':
            return 'notification:' + key
        return f'performance:{reference}:' + key[len(prefix):].rsplit(':', 2)[0]
    return 'notification:' + key


def managed_elsewhere(row):
    data = row.get('data') or {}
    # Never email SMTP failure alerts: a failed alert would generate another.
    if row.get('category') == 'Email':
        return True
    # These two legacy templates are sent directly, without event claims.
    if data.get('performance_event') == 'performance.assessment.self':
        return True
    return (storage_key(row).startswith('learning:') and ':created:employee:' in storage_key(row)
            and row.get('recipient_id') == data.get('employee_id'))


async def deliver(db):
    if not background_jobs_enabled() or not outbound_email_enabled():
        return
    boundary = await initialize(db)
    query = {'email_delivery_checked': {'$ne': True}, '$or': [
        {'created_at': {'$gte': boundary.isoformat()}}, {'created_at': {'$gte': boundary}}]}
    rows = await db.notifications.find(query).sort('created_at', 1).to_list(100)
    for row in rows:
        created = date_value(row.get('created_at'))
        if not created or created < boundary:
            continue
        try:
            if not managed_elsewhere(row):
                complete = await deliver_item(db, row)
                if not complete:
                    continue
            await db.notifications.update_one({'_id': row['_id']}, {'$set': {'email_delivery_checked': True}})
        except Exception:
            logger.exception('Notification email pending; notification %s', storage_key(row))


async def candidate_accounts(db, row):
    """Narrow the lookup; inbox projection remains the authorization authority."""
    recipient = row.get('user_id') or row.get('recipient_id')
    if recipient is not None and recipient != '':
        ids = [recipient]
        if ObjectId.is_valid(str(recipient)):
            ids.append(ObjectId(str(recipient)))
        clauses = [{'_id': {'$in': ids}}]
        if not row.get('user_id') and row.get('recipient_type') not in {'account', 'solver'}:
            employee = await find_employee(db, recipient, tenant_of(row))
            if employee:
                clauses.append({'employee_id': {'$in': [employee_key(employee), str(employee['_id']), employee['_id']]}})
                if employee.get('work_email'):
                    clauses.append(email_query('email', employee['work_email'].strip().lower()))
        if not row.get('user_id') and row.get('recipient_type') not in {'account', 'employee', 'solver'}:
            clauses.append({'role': 'solver'})  # Legacy solver aliases still need the full inbox check.
        routing = {'role': 'solver'} if not row.get('user_id') and row.get('recipient_type') == 'solver' else {'$or': clauses}
    elif row.get('recipient_role') == 'all_active_fte':
        routing = {'role': {'$ne': 'solver'}}
    elif row.get('recipient_role') == 'all_active_solvers':
        routing = {'role': 'solver'}
    else:
        routing = {'role': row.get('recipient_role')}
    return await db.users.find({'$and': [tenant_query(tenant_of(row)), {'is_active': {'$ne': False}}, routing]}).to_list(None)


async def deliver_item(db, row):
    complete = True
    accounts = await candidate_accounts(db, row)
    for account in accounts:
        if not eligible(account) or not account.get('email'):
            continue
        user = {**account, 'id': str(account['_id'])}
        try:
            inbox = await list_inbox(db, user, source_rows=[row], limit=1)
            if not inbox['items']:
                continue
            address = normalize_email(account['email'])
        except HTTPException as error:
            if error.status_code in {403, 404, 409, 422}:
                continue
            raise
        item = inbox['items'][0]
        # Projection applies the same authorization and private-content redaction
        # as the bell; raw notification messages never enter email bodies.
        result = await action_email(db, tenant_of(row), event_key(row), address,
            item['title'], item['message'], portal_link('/notifications'),
            'notification.inbox', retry_skipped=True)
        if result.get('reason') == 'claim_unavailable' or (result.get('status') not in {'sent', 'failed'} and result.get('reason') != 'duplicate_event'):
            complete = False
    return complete
