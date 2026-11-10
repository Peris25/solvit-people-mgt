"""Scoped action emails; durable per-event claims prevent multiworker duplicates."""
import hashlib
from functools import wraps
import logging
import os
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from utils.employee_integrity import find_employee, employee_key, tenant_of, tenant_query, normalize_email
from utils.runtime_controls import outbound_email_enabled

logger = logging.getLogger(__name__)
HR_EMAIL_ROLES = {'hr_admin', 'hr_manager'}
INELIGIBLE = {'inactive', 'exited', 'suspended', 'terminated'}


def best_effort(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        try:
            return await function(*args, **kwargs)
        except Exception:
            logger.warning('Action email routing needs review: %s', function.__name__)
            return {'status': 'failed'}
    return wrapped


def eligible(record):
    state = str(record.get('lifecycle_state') or record.get('status') or '').lower()
    return record.get('is_active') is not False and state not in INELIGIBLE


async def employee_address(db, reference, tenant):
    employee = await find_employee(db, reference, tenant) if reference else None
    return normalize_email(employee.get('work_email') or '') if employee and eligible(employee) else None


async def role_addresses(db, roles, tenant):
    addresses = set()
    rows = await db.users.find({'$and': [tenant_query(tenant), {'role': {'$in': sorted(roles)}, 'is_active': {'$ne': False}}]}).to_list(None)
    for account in rows:
        if not eligible(account) or account.get('account_type') in {'solver', 'board'}:
            continue
        if account.get('employee_id'):
            try:
                employee = await find_employee(db, account['employee_id'], tenant)
            except Exception:
                continue
            if not employee or not eligible(employee):
                continue
        address = normalize_email(account.get('email') or '')
        if address:
            addresses.add(address)
    return sorted(addresses)


def portal_link(path, reference=None):
    base = (os.environ.get('PUBLIC_APP_URL') or os.environ.get('FRONTEND_URL') or 'https://people.solvit.co.ke').rstrip('/')
    return base + path + (quote(str(reference), safe='') if reference is not None else '')


async def action_email(db, tenant, event, to, subject, message, link, template_key=None):
    if not to or not outbound_email_enabled():
        return {'status': 'skipped'}
    address = normalize_email(to)
    claim_id = ObjectId(hashlib.sha256(f'email-event:{tenant}:{event}:{address}'.encode()).hexdigest()[:24])
    html = '<p>' + escape(message) + '</p><p><a href="' + escape(link, quote=True) + '">Open in Solvit People</a></p>'
    claim = {'_id': claim_id, 'tenant_id': tenant, 'event_key': event, 'to': address,
             'subject': subject, 'body_html': html, 'delivery_claim': True, 'template_key': template_key, 'status': 'dispatching',
             'sent_at': datetime.now(timezone.utc).isoformat()}
    try:
        await db.email_log.insert_one(claim)
    except DuplicateKeyError:
        return {'status': 'skipped', 'reason': 'duplicate_event'}
    except Exception:
        logger.warning('Action email claim unavailable for %s; no email dispatched', template_key)
        return {'status': 'failed'}
    try:
        from utils.email_service import send_email
        result = await send_email(db, to=address, subject=subject, html=html, template_key=template_key)
        await db.email_log.update_one({'_id': claim_id}, {'$set': {'status': result.get('status', 'failed')}})
        return result
    except Exception:
        logger.warning('Action email dispatch needs review for %s', template_key)
        return {'status': 'failed'}


@best_effort
async def leave_action(db, employee, row, event):
    tenant = tenant_of(row)
    identity = employee_key(employee)
    key = f"leave:{row['id']}:{event}:{len(row.get('approval_history') or [])}"
    link = portal_link('/leave?view=team&request=', row['id'])
    addresses = []
    if event == 'submitted':
        addresses = await role_addresses(db, HR_EMAIL_ROLES, tenant)
        subject, message = 'New leave request submitted', 'A new leave request is available in Team Leave. Manager approval is pending; HR may review or use its authorized override.'
    elif row.get('status') == 'Pending_HR':
        addresses = await role_addresses(db, HR_EMAIL_ROLES, tenant)
        subject, message = 'Leave request awaiting HR approval', 'The line manager has approved a leave request. Please review it in Team Leave.'
    elif event == 'withdrawn':
        addresses = await role_addresses(db, HR_EMAIL_ROLES, tenant)
        manager = await employee_address(db, row.get('line_manager_id'), tenant)
        if manager: addresses.append(manager)
        subject, message = 'Leave request withdrawn', 'An employee has withdrawn a pending leave request. No approval is required.'
    else:
        return
    own = await employee_address(db, identity, tenant)
    for address in sorted(set(addresses) - {own}):
        await action_email(db, tenant, key, address, subject, message, link, 'leave.workflow_action')


@best_effort
async def performance_action(db, employee, manager, row, event):
    base = event.split(':', 1)[0]
    tenant = tenant_of(row)
    link = portal_link('/performance?review=', row['id'])
    addresses = []
    if base == 'created':
        addresses = [await employee_address(db, employee_key(employee), tenant)]
        subject, message = 'Your performance review is ready', 'HR has created your performance review. Open it to check the assessment deadlines and instructions.'
    elif base in {'performance.assessment.manager', 'performance.meeting.proposed'}:
        addresses = await role_addresses(db, HR_EMAIL_ROLES, tenant)
        own = await employee_address(db, employee_key(employee), tenant)
        addresses = [address for address in addresses if address != own]
        subject, message = ('Performance review ready for HR', 'The manager assessment is submitted. Please arrange the employee and line manager review meeting.') if base == 'performance.assessment.manager' else ('Review meeting date proposed', 'The line manager has proposed a review meeting date. Please confirm availability and set the meeting in the portal.')
    elif base == 'performance.meeting.scheduled':
        addresses = [await employee_address(db, employee_key(employee), tenant), await employee_address(db, employee_key(manager), tenant) if manager else None]
        subject, message = 'Performance review meeting confirmed', 'HR has set your review meeting. Open the review for the confirmed date, time and location.'
    else:
        return
    for address in sorted(set(address for address in addresses if address)):
        await action_email(db, tenant, f"performance:{row['id']}:{event}", address, subject, message, link, 'performance.workflow_action')


@best_effort
async def solver_application(db, row, requisition, eligible_applicant):
    tenant = tenant_of(row)
    reference = row['id']
    for address in await role_addresses(db, {'hr_admin'}, tenant):
        path = '/solver-eligible' if eligible_applicant else '/solver-ineligible'
        await action_email(db, tenant, f'solver.application:{reference}', address,
            'New Solver application received', 'A new Solver application and CV are available for HR review.', portal_link(path), 'solver.application_hr')
    if row.get('email'):
        await action_email(db, tenant, f'solver.application.ack:{reference}', row['email'],
            'Your Solvit Solver application was received', 'Thank you for applying. Your application and CV have been received. HR will contact you about any next steps; this acknowledgement is not a job offer or confirmation of eligibility.',
            portal_link('/apply/', requisition['id']), 'solver.application_ack')
