"""Clear performance action copy. Never include assessment answers or scores."""
from datetime import date, datetime, timezone, timedelta
from utils import performance_v3 as process


def due(value):
    try: return date.fromisoformat(str(value)[:10]).strftime('%d %B %Y')
    except (TypeError, ValueError): return None


def deadline(label, value):
    return f'{label}: {due(value)}.' if due(value) else f'{label}: check the review in the portal.'


def meeting_details(values):
    try:
        instant = datetime.fromisoformat(values['scheduled_at'].replace('Z', '+00:00'))
        if instant.tzinfo is None: return ''
        text = instant.astimezone(timezone(timedelta(hours=3))).strftime('%d %B %Y at %H:%M EAT')
        return 'Meeting: ' + text + ('. Location: ' + str(values['location']) if values.get('location') else '') + '.'
    except (KeyError, TypeError, ValueError): return ''


async def body(db, notification, recipient_id=None, *, saved_review=None, saved_employee=None):
    data = notification.get('data') or {}
    tenant = process.tenant_of(notification)
    reviews = getattr(db, 'performance_reviews', None)
    review = saved_review or (await reviews.find_one(process.scoped(notification, {'id': data.get('performance_review_id')})) if reviews is not None and data.get('performance_review_id') else None)
    if not review and data.get('performance_peer_task_id'):
        task = await db.performance_peer_tasks.find_one(process.scoped(notification, {'id': data['performance_peer_task_id']}))
        if task and reviews is not None:
            review = await reviews.find_one(process.scoped(notification, {'id': task['review_id']}))
    else: task = None
    cycles = getattr(db, 'performance_cycles', None)
    cycle_id = data.get('cycle_id') or data.get('performance_alignment_cycle_id') or (review or {}).get('cycle_id')
    cycle = await cycles.find_one(process.scoped(notification, {'id': cycle_id})) if cycles is not None and cycle_id else None
    row = review or cycle or {}
    employee_id = (review or {}).get('employee_id') or data.get('employee_id')
    employee = saved_employee or (await process.find_employee(db, employee_id, tenant) if employee_id else None)
    recipient = await process.find_employee(db, recipient_id, tenant) if recipient_id else None
    name = (employee or {}).get('full_name') or 'the employee named in the portal'
    own = bool(employee and recipient_id in process.reference_ids(employee))
    manager_id=(review or {}).get('line_manager_id') or (employee or {}).get('line_manager_id')
    line_manager=await process.find_employee(db,manager_id,tenant) if manager_id else None
    manager = bool(recipient and line_manager and set(process.reference_ids(recipient)) & set(process.reference_ids(line_manager)))
    period = {'Year_End': 'Year-end', 'Mid_Year': 'Mid-year', 'Probation': 'Probation'}.get(row.get('cycle_type'), 'Performance')
    if row.get('cycle_year'): period += ' ' + str(row['cycle_year'])
    if row.get('cycle_type')=='Probation' and row.get('review_month'): period += ' · Month ' + str(row['review_month'])
    greeting = 'Hi ' + str(recipient['full_name']) + ',' if recipient and recipient.get('full_name') else 'Hello,'
    title = str(notification.get('title') or '').lower()
    event = str(data.get('performance_event') or '')
    label = event.split(':', 1)[0]
    if data.get('performance_alignment_cycle_id'):
        return '\n\n'.join([greeting, f'Your Alignment Survey for {period} is ready. This is your own survey, separate from your self-review and any reviews you complete for colleagues.',
            'Open the survey and answer all 12 questions using the 1–5 scale.', deadline('Submit your survey by', row.get('self_due_on')), 'Use the link below to open Solvit People and complete the survey.'])
    if data.get('performance_peer_task_id'):
        return '\n\n'.join([greeting, f'Please complete a confidential 360° peer review for {name} ({period}). This is feedback about your colleague, not your own self-review.',
            'Rate the five values from 0–10, answer the team-retention question, and add optional feedback. Submit when you are ready; your name is not shown with the feedback released to your colleague.',
            deadline('Submit your peer review by', (task or {}).get('due_on') or row.get('peer_due_on')), 'Use the link below to open the peer review in Solvit People.'])
    context = f'This is your own {period} performance review.' if own else f'This concerns {name}’s {period} performance review. '
    if not own: context += 'You are receiving this as their line manager.' if manager else 'You are receiving this for HR follow-up.'
    if row.get('cycle_type')=='Probation' and label in {'created','performance.assessment.manager','performance.assessment.release','performance.probation.meeting_completed','performance.probation.acknowledged'}:
        if label=='created':
            manager_name=(line_manager or {}).get('full_name') or 'your assigned line manager'
            action='Complete the employee’s KPI and five values assessment, record supporting evidence and submit it. The employee does not self-score.' if manager else f'Your probation review has been sent to {manager_name}, your line manager, to complete the KPI and values assessment. You will then discuss the results together, add your comments and acknowledge the outcome after HR releases it. You do not need to submit a self-assessment.'
            timing=deadline('Manager assessment due',row.get('manager_due_on'))
        elif label=='performance.assessment.manager':
            action='Your line manager has submitted the probation assessment. Open it to read the findings and add your comments. Discuss the results and development actions in your review meeting.' if own else 'The manager has submitted the probation assessment. Arrange the employee–manager review meeting. Record its completion before approving the outcome.'
            timing=deadline('HR completion due',row.get('review_due_on'))
        elif label=='performance.assessment.release':
            action='HR has released your probation outcome. Open the review, read it and acknowledge receipt. Acknowledgement does not mean agreement; you may record comments or disagreement.' if own else f'The probation review outcome for {name} has been released to the employee. Open the review to follow up on receipt acknowledgement and the agreed development actions.'
            timing=''
        elif label=='performance.probation.meeting_completed':
            action='Your probation review meeting has been recorded as completed. Open the record to check the discussion and agreed actions. HR will review and release the outcome.' if own else 'The probation review meeting has been recorded as completed. Review the discussion and agreed actions, then record HR’s outcome approval and release it to the employee.'
            timing=deadline('HR completion due',row.get('review_due_on'))
        else:
            action='The employee has acknowledged receipt of the probation review. Open the record to check the acknowledgement and any employee comments.';timing=''
        return '\n\n'.join(part for part in [greeting,context,action,timing,'Use the link below to open the probation review in Solvit People.'] if part)
    if label == 'manager-week2' or 'team performance cycle is open' in title:
        action = f'HR has opened the review for {name}. They should complete their self-review first. Once it is submitted, review their actual results and self-scores, enter your manager scores and comments, then submit to HR.'
        timing = deadline('Employee self-review due', row.get('self_due_on')) + ' ' + deadline('Your manager assessment due', row.get('manager_due_on'))
    elif label == 'dispute-resolved' or 'responded to your performance review dispute' in title:
        action, timing = 'HR has responded to your review dispute. Open your review to read the response and any next steps.', ''
    elif label == 'dispute' or 'submitted a written performance review dispute' in title:
        action, timing = 'The employee has submitted a review dispute. Read it in the portal and record HR’s response.', ''
    elif 'meeting' in title and ('proposed' in title or label == 'meeting-proposed' or label == 'meeting-propose'):
        action = 'A review meeting date has been proposed. This is not a confirmed booking. HR should check availability and confirm the meeting in the portal.'
        timing = meeting_details(row.get('meeting_proposal') or {})
    elif 'meeting' in title and any(word in title for word in ('confirmed', 'approaching', 'scheduled review meeting')):
        action = 'Open the review to check the meeting arrangements and attend the discussion.'
        if 'whether' in title: action = 'Check whether the meeting took place, then record its completion in the portal.'
        timing = meeting_details(row.get('review_meeting') or {})
    elif 'meeting' in title and any(word in title for word in ('propose', 'arrang', 'needs')):
        action = 'Propose a meeting date in the portal so HR can confirm arrangements with the employee and manager.' if manager else 'Arrange the review meeting with the employee and their line manager, then confirm the date and location in the portal.'
        timing = deadline('Meetings and HR release due', row.get('review_due_on'))
    elif label in {'released', 'dispute-resolved'} or 'acknowledge' in title:
        action, timing = 'HR has released your review. Open it, read the outcome and acknowledge that you have received it. If you disagree, use the written dispute option in the review.', deadline('Acknowledge receipt by', row.get('ack_due_on'))
    elif 'release' in title and ('48 hours' in title or 'overdue' in title):
        action, timing = 'The review meeting is completed. Check the review and release it to the employee within 48 hours of the recorded meeting completion.', ''
    elif 'shortfall' in title:
        action, timing = 'This employee has fewer than three submitted peer reviews. Check the counts in the HR peer review progress view and follow up. Individual reviewer names, answers and comments are not included in this email.', deadline('Peer collection deadline', row.get('peer_due_on'))
    elif label == 'outcomes' or 'follow-up' in title:
        action, timing = 'Open the review’s follow-up actions, check what is due and record progress in the portal.', ''
    elif label in {'manager-submitted', 'performance.assessment.manager'} or 'ready for hr review' in title:
        action, timing = 'The manager assessment is submitted. Open the review, complete the HR checks and arrange the review meeting.', deadline('Meetings and HR release due', row.get('review_due_on'))
    elif label in {'actual-correction', 'company-feedback-corrected'} or 'corrected' in title:
        action, timing = 'HR has updated information in this review. Open the updated assessment and check the changes before continuing.', deadline('Manager assessment due', row.get('manager_due_on'))
    elif label in {'self-submitted', 'performance.assessment.self'} or 'submitted assessment' in title or ('manager assessment' in title and manager):
        action, timing = 'The employee has submitted their self-review. Review their actual results and self-scores, enter your manager scores and comments, then submit to HR.', deadline('Manager assessment due', row.get('manager_due_on'))
    elif label in {'opened', 'created'} or 'self-assessment' in title or 'self-review' in title:
        action = 'Complete your probation self-assessment, describing your progress, challenges and the support you need.' if row.get('cycle_type') == 'Probation' else 'Complete your actual results and self-scores for the KPIs, score the five values with examples, and answer the reflection questions. You can save a draft and return before submitting.'
        if row.get('workflow_version') != 3 and row.get('cycle_type') != 'Probation':
            action = 'Open the review, check the assigned goals and complete your self-assessment. Submit it when you are ready for your line manager to review it.'
        timing = deadline('Submit your self-review by', row.get('self_due_on'))
    elif label == 'deadline' or 'overdue' in title:
        if row.get('released_at'):
            action, timing = 'Open the released review and acknowledge receipt. Contact HR if you need help.', deadline('Acknowledgement due', row.get('ack_due_on'))
        elif row.get('status') == 'Self_Draft':
            action = 'The employee self-review is still outstanding. Complete and submit your self-review.' if own else 'The employee self-review is still outstanding. Follow up with the employee.'
            timing = deadline('Self-review due', row.get('self_due_on'))
        else:
            action, timing = 'The manager assessment is outstanding. Complete it in the portal, or follow up with the assigned line manager.', deadline('Manager assessment due', row.get('manager_due_on'))
    else:
        action, timing = 'Open this review in Solvit People to check its current status and the action assigned to you. Contact HR if you need help.', ''
    return '\n\n'.join(part for part in [greeting, context, action, timing, 'Use the link below to open this review in Solvit People.'] if part)
