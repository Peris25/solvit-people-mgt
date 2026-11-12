"""Idempotent portal reminders and event emails through the existing mail service."""
import logging
from datetime import date, datetime, timedelta
from utils import performance_v3 as process
from utils.runtime_controls import background_jobs_enabled, outbound_email_enabled

logger = logging.getLogger(__name__)


async def deliver(db, tenant):
    if not outbound_email_enabled(): return
    from utils.email_routing import employee_address, role_addresses, action_email, portal_link
    pending = await db.notifications.find({'tenant_id': tenant, 'data.performance_v3': True, 'v3_email_pending': True}).to_list(500)
    for item in pending:
        try:
            data = item.get('data') or {}
            if data.get('performance_peer_task_id'): suffix = '?peer=' + data['performance_peer_task_id']
            elif data.get('performance_alignment_cycle_id'): suffix = '?alignment=' + data['performance_alignment_cycle_id']
            else: suffix = '?review=' + data['performance_review_id']
            if item.get('recipient_id'):
                address = await employee_address(db, item['recipient_id'], tenant); addresses = [address] if address else []
            else:
                addresses = await role_addresses(db, {item['recipient_role']}, tenant)
                subject_address = await employee_address(db, data.get('employee_id'), tenant)
                addresses = [address for address in addresses if address != subject_address]
            for address in addresses:
                await action_email(db, tenant, 'performance-v3:' + str(item['_id']), address, item['title'],
                                   'A performance action is ready. Open the portal to view its authorized details and deadline.', portal_link('/performance') + suffix)
            await db.notifications.update_one({'_id': item['_id']}, {'$set': {'v3_email_pending': False}})
        except Exception:
            logger.warning('Performance notification delivery needs retry; event %s', str(item.get('_id')))


async def daily(db):
    if not background_jobs_enabled(): return
    rows = await db.performance_reviews.find({'workflow_version': 3, 'status': {'$nin': ['Archived', 'Cancelled']}}).to_list(None)
    tenants = set()
    for row in rows:
        tenants.add(process.tenant_of(row))
        if row.get('released_at'):
            deadline, recipient, label = row.get('ack_due_on'), row['employee_id'], 'Acknowledge your released performance review'
            pending = not row.get('acknowledged_at')
        elif row['status'] == 'Self_Draft': deadline, recipient, label, pending = row['self_due_on'], row['employee_id'], 'Complete your self-assessment', True
        elif row['status'] == 'Self_Submitted': deadline, recipient, label, pending = row['manager_due_on'], row['line_manager_id'], 'Complete your employee’s manager assessment', True
        else: deadline, recipient, label, pending = None, None, None, False
        if pending and deadline:
            distance = (date.fromisoformat(deadline) - process.today()).days
            if distance in (3, 1) or distance < 0:
                await process.notice(db, row, 'deadline:' + deadline + ':' + process.today().isoformat(), 'employee', recipient, label if distance >= 0 else 'Performance action overdue — contact HR')
                if distance < 0: await process.hr_notice(db, row, 'overdue:' + process.today().isoformat(), 'A performance action is overdue')
        if not row.get('released_at') and process.today() >= date.fromisoformat(row['peer_due_on']):
            responses = await db.performance_peer_responses.find(process.scoped(row, {'review_id': row['id']})).to_list(3)
            if len(responses) < 3: await process.hr_notice(db, row, 'peer-shortfall:' + process.today().isoformat(), 'Peer assessment has fewer than three responses')
        if row.get('meeting_completed_at') and not row.get('released_at') and process.instant() > datetime.fromisoformat(row['meeting_completed_at']) + timedelta(hours=48):
            await process.hr_notice(db, row, 'release-overdue:' + process.today().isoformat(), 'Completed performance review is overdue for HR release')
        meeting = row.get('review_meeting') or {}
        if meeting.get('scheduled_at') and not row.get('meeting_completed_at'):
            distance = (datetime.fromisoformat(meeting['scheduled_at']).date() - process.today()).days
            if distance in (3, 1):
                for recipient in (row['employee_id'], row['line_manager_id']):
                    await process.notice(db, row, 'meeting-reminder:' + process.today().isoformat(), 'employee', recipient, 'Your performance review meeting is approaching')
            if distance < 0: await process.hr_notice(db, row, 'meeting-completion:' + process.today().isoformat(), 'Confirm whether the scheduled review meeting was completed')
        if row['status'] == 'HR_Reviewed' and not meeting:
            distance = (date.fromisoformat(row['review_due_on']) - process.today()).days
            if distance in (3, 1) or distance < 0:
                await process.notice(db, row, 'propose-meeting:' + process.today().isoformat(), 'employee', row['line_manager_id'], 'Propose the performance review meeting date')
                await process.hr_notice(db, row, 'schedule-meeting:' + process.today().isoformat(), 'A performance review meeting still needs arranging')
        if any(o.get('status') == 'Pending' and o.get('due_on', 'z') <= process.today().isoformat() for o in row.get('outcomes', [])):
            await process.hr_notice(db, row, 'followup-due:' + process.today().isoformat(), 'Performance development or PIP follow-up is due')
        window = await db.performance_cycles.find_one(process.scoped(row, {'id': row['cycle_id']}))
        if window and window.get('alignment_window_id'):
            distance = (date.fromisoformat(window['self_due_on']) - process.today()).days
            identity = process.key('alignment-answer', process.tenant_of(row), window['id'], row['employee_id'])
            if distance in (3, 1) and not await db.survey_responses.find_one({'_id': identity}):
                await process.notice(db, {**row, 'alignment': True}, 'alignment-reminder:' + process.today().isoformat(), 'employee', row['employee_id'], 'Complete your Alignment Survey before its deadline')
    tasks = await db.performance_peer_tasks.find({'status': 'Assigned'}).to_list(None)
    for task in tasks:
        distance = (date.fromisoformat(task['due_on']) - process.today()).days
        if distance in (3, 1) or distance < 0:
            review = await db.performance_reviews.find_one(process.scoped(task, {'id': task['review_id']}))
            if review and review.get('status') not in {'Archived', 'Cancelled'}:
                await process.notice(db, {**review, 'peer_task_id': task['id']}, 'peer-reminder:' + task['id'] + ':' + process.today().isoformat(), 'employee', task['reviewer_employee_id'], 'Complete your anonymous peer assessment')
    for tenant in tenants: await deliver(db, tenant)
