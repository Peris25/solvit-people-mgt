"""Email Templates — CRUD + seed + preview. Templates are stored in
`email_templates` (one doc per template key). IT Admin has full edit; HR Admin
has view/preview only.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/email-templates", tags=["email_templates"])

# Centralised default catalogue. Adding a new template here is enough — it
# auto-seeds on first read. Merge tags are listed for the UI.
DEFAULT_TEMPLATES = [
    # ---------------- Onboarding ----------------
    {"key": "onboarding.welcome", "module": "Onboarding", "name": "Welcome Email",
     "subject": "Welcome to Solvit, {{employee_first_name}}", "merge_tags": ["employee_name","employee_first_name","employee_role","employee_department","line_manager_name","start_date","login_url","hr_name"],
     "body": "<p>Hi {{employee_first_name}},</p><p>Welcome to <strong>Solvit Limited</strong>! We're delighted to have you on the team as <strong>{{employee_role}}</strong> in {{employee_department}}.</p><p><strong>Your start date:</strong> {{start_date}}<br/><strong>Your line manager:</strong> {{line_manager_name}}</p><p>Your People Platform login will be set up by IT — they'll email you separately with your password. In the meantime you can visit <a href=\"{{login_url}}\">{{login_url}}</a>.</p><p>Warm regards,<br/>{{hr_name}}<br/>Solvit People & Admin</p>"},
    {"key": "onboarding.pre_arrival", "module": "Onboarding", "name": "Pre-Arrival Instructions",
     "subject": "Your first day at Solvit — what to expect", "merge_tags": ["employee_name","start_date","office_address","manager_name"],
     "body": "<p>Hi {{employee_name}},</p><p>We can't wait to welcome you on <strong>{{start_date}}</strong>.</p><p>Please report to {{office_address}} where {{manager_name}} will meet you.</p><p>— Solvit People Platform</p>"},
    {"key": "onboarding.checkin_30", "module": "Onboarding", "name": "30-Day Check-In Reminder (LM)",
     "subject": "{{employee_name}} — 30-day check-in due", "merge_tags": ["employee_name","manager_name","due_date"],
     "body": "<p>Hi {{manager_name}},</p><p>Please complete the 30-day check-in for {{employee_name}} by {{due_date}}.</p><p>— Solvit People Platform</p>"},
    {"key": "onboarding.checkin_60", "module": "Onboarding", "name": "60-Day Check-In Reminder (LM)",
     "subject": "{{employee_name}} — 60-day check-in due", "merge_tags": ["employee_name","manager_name","due_date"],
     "body": "<p>Hi {{manager_name}},</p><p>Please complete the 60-day check-in for {{employee_name}} by {{due_date}}.</p><p>— Solvit People Platform</p>"},
    {"key": "onboarding.checkin_90", "module": "Onboarding", "name": "90-Day Check-In Reminder (LM)",
     "subject": "{{employee_name}} — 90-day check-in due", "merge_tags": ["employee_name","manager_name","due_date"],
     "body": "<p>Hi {{manager_name}},</p><p>Please complete the 90-day check-in for {{employee_name}} by {{due_date}}.</p><p>— Solvit People Platform</p>"},
    {"key": "onboarding.probation_confirm", "module": "Onboarding", "name": "Probation Confirmation",
     "subject": "Probation confirmed — welcome aboard", "merge_tags": ["employee_name","start_date"],
     "body": "<p>Hi {{employee_name}},</p><p>Congratulations — your probation has been successfully confirmed effective today. We're delighted to have you on the team!</p><p>— Solvit People Platform</p>"},
    {"key": "onboarding.probation_extend", "module": "Onboarding", "name": "Probation Extension Notice",
     "subject": "Probation extension notice", "merge_tags": ["employee_name","new_end_date","reason"],
     "body": "<p>Hi {{employee_name}},</p><p>Your probation period has been extended to {{new_end_date}}.</p><p>Reason: {{reason}}</p><p>— Solvit People Platform</p>"},

    # ---------------- Recruitment ----------------
    {"key": "recruitment.application_received", "module": "Recruitment", "name": "Application Received",
     "subject": "We received your application — Solvit", "merge_tags": ["candidate_name","role_title"],
     "body": "<p>Dear {{candidate_name}},</p><p>Thank you for applying for the {{role_title}} role at Solvit. We've received your application and will be in touch shortly.</p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.invite_competency", "module": "Recruitment", "name": "Invitation to Competency Test",
     "subject": "Competency test invitation — {{role_title}}", "merge_tags": ["candidate_name","role_title","test_link","deadline"],
     "body": "<p>Dear {{candidate_name}},</p><p>Please complete the competency test for {{role_title}} by {{deadline}}.</p><p><a href=\"{{test_link}}\">{{test_link}}</a></p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.invite_values", "module": "Recruitment", "name": "Invitation to Values Assessment",
     "subject": "Values assessment invitation — {{role_title}}", "merge_tags": ["candidate_name","role_title","test_link","deadline"],
     "body": "<p>Dear {{candidate_name}},</p><p>Please complete the values assessment by {{deadline}}.</p><p><a href=\"{{test_link}}\">{{test_link}}</a></p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.invite_growth", "module": "Recruitment", "name": "Invitation to Growth Mindset Assessment",
     "subject": "Growth mindset assessment — {{role_title}}", "merge_tags": ["candidate_name","role_title","test_link","deadline"],
     "body": "<p>Dear {{candidate_name}},</p><p>Please complete the growth mindset assessment by {{deadline}}.</p><p><a href=\"{{test_link}}\">{{test_link}}</a></p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.invite_interview", "module": "Recruitment", "name": "Invitation to Physical Interview",
     "subject": "Interview invitation — {{role_title}}", "merge_tags": ["candidate_name","role_title","interview_datetime","office_address"],
     "body": "<p>Dear {{candidate_name}},</p><p>You're invited to interview for {{role_title}} on {{interview_datetime}} at {{office_address}}.</p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.offer", "module": "Recruitment", "name": "Offer Letter Email",
     "subject": "Offer of employment — {{role_title}}", "merge_tags": ["candidate_name","role_title","salary_kes","expiry_date"],
     "body": "<p>Dear {{candidate_name}},</p><p>We're delighted to offer you the role of <strong>{{role_title}}</strong> at a monthly gross salary of <strong>KES {{salary_kes}}</strong>.</p><p>Please respond by {{expiry_date}}.</p><p>— Solvit Recruitment</p>"},
    {"key": "recruitment.regret", "module": "Recruitment", "name": "Regret Email",
     "subject": "Update on your application — {{role_title}}", "merge_tags": ["candidate_name","role_title"],
     "body": "<p>Dear {{candidate_name}},</p><p>Thank you for your interest in {{role_title}}. We've decided to move forward with other candidates at this time.</p><p>— Solvit Recruitment</p>"},

    # ---------------- Solvers ----------------
    {"key": "solver.activation", "module": "Solvers", "name": "Solver Account Activation",
     "subject": "Your Solver account is live", "merge_tags": ["solver_name","activation_date","platform_link"],
     "body": "<p>Hi {{solver_name}},</p><p>Your Solvit Solver account was activated on <strong>{{activation_date}}</strong>. You can now be assigned inspection jobs.</p><p>Open the platform: <a href=\"{{platform_link}}\">{{platform_link}}</a></p>"},
    {"key": "solver.tier_upgrade", "module": "Solvers", "name": "Solver Performance Tier Upgrade",
     "subject": "You've been upgraded to {{new_tier}}", "merge_tags": ["solver_name","new_tier"],
     "body": "<p>Hi {{solver_name}},</p><p>Great work! Your performance tier is now <strong>{{new_tier}}</strong>. Keep it up.</p>"},
    {"key": "solver.tier_downgrade", "module": "Solvers", "name": "Solver Performance Tier Downgrade",
     "subject": "Your performance tier has changed", "merge_tags": ["solver_name","new_tier"],
     "body": "<p>Hi {{solver_name}},</p><p>Your performance tier has been adjusted to <strong>{{new_tier}}</strong>. Let's talk about how we can help you bounce back.</p>"},
    {"key": "solver.suspension", "module": "Solvers", "name": "Solver Account Suspension Notice",
     "subject": "Your Solver account has been suspended", "merge_tags": ["solver_name","reason"],
     "body": "<p>Hi {{solver_name}},</p><p>Your account has been suspended. Reason: <strong>{{reason}}</strong>.</p><p>Please contact the Solver Manager to discuss.</p>"},
    {"key": "solver.reactivation", "module": "Solvers", "name": "Solver Account Reactivation",
     "subject": "Your Solver account is reactivated", "merge_tags": ["solver_name"],
     "body": "<p>Hi {{solver_name}},</p><p>Welcome back — your account has been reactivated and you can now receive inspection jobs again.</p>"},
    {"key": "solver.incentive_paid", "module": "Solvers", "name": "Solver Incentive Payment Notification",
     "subject": "Your incentive of KES {{amount_kes}} is on the way", "merge_tags": ["solver_name","amount_kes","reference"],
     "body": "<p>Hi {{solver_name}},</p><p>An incentive of <strong>KES {{amount_kes}}</strong> has been processed (ref: {{reference}}).</p>"},

    # ---------------- Performance ----------------
    {"key": "performance.cycle_open", "module": "Performance", "name": "Performance Review Cycle Open",
     "subject": "{{cycle_label}} review cycle is now open", "merge_tags": ["cycle_label","deadline"],
     "body": "<p>The {{cycle_label}} performance review cycle is open until {{deadline}}. Please submit your reviews on time.</p>"},
    {"key": "performance.self_reminder", "module": "Performance", "name": "Self-Review Reminder",
     "subject": "Complete your self-review", "merge_tags": ["employee_name","deadline"],
     "body": "<p>Hi {{employee_name}},</p><p>Your self-review is due {{deadline}}.</p>"},
    {"key": "performance.manager_reminder", "module": "Performance", "name": "Manager Review Reminder",
     "subject": "Reviews due — please complete", "merge_tags": ["manager_name","pending_count","deadline"],
     "body": "<p>Hi {{manager_name}},</p><p>You have {{pending_count}} review(s) pending by {{deadline}}.</p>"},
    {"key": "performance.review_complete", "module": "Performance", "name": "Performance Review Completed",
     "subject": "Your {{cycle_type}} {{cycle_year}} review is ready", "merge_tags": ["employee_name","cycle_type","cycle_year","score","rating","platform_link"],
     "body": "<p>Hi {{employee_name}},</p><p>Your <strong>{{cycle_type}} {{cycle_year}}</strong> performance review has been completed and is ready for your acknowledgement.</p><p><strong>Overall score:</strong> {{score}}<br/><strong>Rating:</strong> {{rating}}</p><p><a href=\"{{platform_link}}\">View and acknowledge your review</a></p>"},
    {"key": "performance.pip_initiated", "module": "Performance", "name": "PIP Initiated",
     "subject": "Performance Improvement Plan — next steps", "merge_tags": ["employee_name","line_manager_name","hr_name","platform_link"],
     "body": "<p>Hi {{employee_name}},</p><p>A Performance Improvement Plan (PIP) has been initiated for you. Your line manager <strong>{{line_manager_name}}</strong> will share the structured plan, focus areas and check-in cadence shortly.</p><p>You can view the live PIP at: <a href=\"{{platform_link}}\">{{platform_link}}</a></p><p>Regards,<br/>{{hr_name}}</p>"},
    {"key": "performance.pip_checkin", "module": "Performance", "name": "PIP Check-In Reminder",
     "subject": "PIP check-in scheduled", "merge_tags": ["employee_name","manager_name","checkin_date"],
     "body": "<p>PIP check-in for {{employee_name}} is scheduled with {{manager_name}} on {{checkin_date}}.</p>"},
    {"key": "performance.pip_success", "module": "Performance", "name": "PIP Outcome — Successful Completion",
     "subject": "Your PIP is successfully closed", "merge_tags": ["employee_name"],
     "body": "<p>Hi {{employee_name}},</p><p>Congratulations — your PIP has been successfully completed.</p>"},
    {"key": "performance.pip_escalate", "module": "Performance", "name": "PIP Outcome — Escalation to Disciplinary",
     "subject": "PIP outcome — escalation notice", "merge_tags": ["employee_name","line_manager_name","hr_name","platform_link"],
     "body": "<p>Hi {{employee_name}},</p><p>Your Performance Improvement Plan has been formally closed and the matter has been escalated for further review. <strong>{{line_manager_name}}</strong> and {{hr_name}} will be in touch to outline the next steps.</p><p>You can review the full record at: <a href=\"{{platform_link}}\">{{platform_link}}</a></p>"},

    # ---------------- Surveys ----------------
    {"key": "survey.open", "module": "Surveys", "name": "Alignment Survey Open",
     "subject": "Alignment survey is now open", "merge_tags": ["cycle_label","deadline"],
     "body": "<p>The {{cycle_label}} alignment survey is open until {{deadline}}. Your responses are anonymous.</p>"},
    {"key": "survey.reminder", "module": "Surveys", "name": "Alignment Survey Reminder",
     "subject": "Survey reminder — please respond", "merge_tags": ["employee_name","deadline"],
     "body": "<p>Hi {{employee_name}},</p><p>You haven't completed the alignment survey yet. Please respond by {{deadline}}.</p>"},
    {"key": "survey.results_published", "module": "Surveys", "name": "Survey Results Published",
     "subject": "Survey results are live", "merge_tags": ["cycle_label"],
     "body": "<p>The {{cycle_label}} alignment survey results are now available in your dashboard.</p>"},

    # ---------------- Retention ----------------
    {"key": "retention.stay_interview_invite", "module": "Retention", "name": "Stay Interview Invitation",
     "subject": "Stay interview invitation", "merge_tags": ["employee_name","manager_name","interview_date","interview_location"],
     "body": "<p>Hi {{employee_name}},</p><p>You're invited to a stay interview with <strong>{{manager_name}}</strong> on <strong>{{interview_date}}</strong> at {{interview_location}}. This is a confidential conversation about what makes you stay, what could make you leave, and how we can grow together.</p>"},
    {"key": "retention.exit_interview_invite", "module": "Retention", "name": "Exit Interview Invitation",
     "subject": "Exit interview invitation", "merge_tags": ["employee_name","interview_date"],
     "body": "<p>Hi {{employee_name}},</p><p>Please join us for an exit interview on {{interview_date}}.</p>"},

    # ---------------- L&D ----------------
    {"key": "lnd.training_assigned", "module": "L&D", "name": "Training Assignment Notification",
     "subject": "Training assigned: {{training_name}}", "merge_tags": ["employee_name","training_name","start_date"],
     "body": "<p>Hi {{employee_name}},</p><p>You've been assigned to {{training_name}} starting {{start_date}}.</p>"},
    {"key": "lnd.idp_review_reminder", "module": "L&D", "name": "IDP Review Reminder",
     "subject": "IDP review due", "merge_tags": ["employee_name","manager_name","review_date"],
     "body": "<p>Hi {{employee_name}} & {{manager_name}},</p><p>The IDP review is due {{review_date}}.</p>"},
    {"key": "lnd.project_assigned", "module": "L&D", "name": "Project Ownership Assignment",
     "subject": "New project ownership: {{project_name}}", "merge_tags": ["employee_name","project_name","start_date"],
     "body": "<p>Hi {{employee_name}},</p><p>You're now owner of project <strong>{{project_name}}</strong> starting {{start_date}}.</p>"},
    {"key": "lnd.project_completed", "module": "L&D", "name": "Project Completion & Reward",
     "subject": "Project completed — well done", "merge_tags": ["employee_name","project_name","reward_on_completion"],
     "body": "<p>Hi {{employee_name}},</p><p>Congratulations on completing <strong>{{project_name}}</strong>.</p><p><strong>Agreed reward:</strong> {{reward_on_completion}}</p><p>HR will be in touch to confirm the next steps.</p>"},

    # ---------------- Leave ----------------
    {"key": "leave.received", "module": "Leave", "name": "Leave Application Received",
     "subject": "Your leave application has been received", "merge_tags": ["employee_name","leave_type","start_date","end_date","days"],
     "body": "<p>Hi {{employee_name}},</p><p>We've received your {{leave_type}} request ({{start_date}} → {{end_date}}, {{days}} days). You'll be notified once approved.</p>"},
    {"key": "leave.approved", "module": "Leave", "name": "Leave Approved",
     "subject": "Leave approved — {{leave_type}}", "merge_tags": ["employee_name","leave_type","start_date","end_date"],
     "body": "<p>Hi {{employee_name}},</p><p>Your {{leave_type}} leave from {{start_date}} to {{end_date}} has been approved.</p>"},
    {"key": "leave.rejected", "module": "Leave", "name": "Leave Rejected",
     "subject": "Leave request not approved", "merge_tags": ["employee_name","leave_type","reason"],
     "body": "<p>Hi {{employee_name}},</p><p>Your {{leave_type}} request was not approved. Reason: {{reason}}.</p>"},
    {"key": "leave.cancelled", "module": "Leave", "name": "Leave Cancellation Confirmed",
     "subject": "Leave cancellation confirmed", "merge_tags": ["employee_name","leave_type"],
     "body": "<p>Hi {{employee_name}},</p><p>Your {{leave_type}} leave has been cancelled as requested.</p>"},
    {"key": "leave.balance_low", "module": "Leave", "name": "Leave Balance Low Warning",
     "subject": "Your leave balance is running low", "merge_tags": ["employee_name","remaining_days"],
     "body": "<p>Hi {{employee_name}},</p><p>You have {{remaining_days}} days remaining for the year.</p>"},
    {"key": "leave.pending_lm", "module": "Leave", "name": "Leave Pending Approval (LM)",
     "subject": "Leave approval pending — {{employee_name}}", "merge_tags": ["manager_name","employee_name","leave_type","days"],
     "body": "<p>Hi {{manager_name}},</p><p>{{employee_name}} has requested {{days}} day(s) of {{leave_type}} leave. Please review.</p>"},

    # ---------------- Compensation ----------------
    {"key": "comp.salary_review", "module": "Compensation", "name": "Salary Review Notification",
     "subject": "Your salary review outcome", "merge_tags": ["employee_name","new_salary_kes","effective_date"],
     "body": "<p>Hi {{employee_name}},</p><p>Your new monthly salary is <strong>KES {{new_salary_kes}}</strong> effective {{effective_date}}.</p>"},
    {"key": "comp.bonus_eligible", "module": "Compensation", "name": "Bonus Eligibility Confirmed",
     "subject": "Bonus eligibility confirmed", "merge_tags": ["employee_name","bonus_kes"],
     "body": "<p>Hi {{employee_name}},</p><p>You're eligible for a bonus of KES {{bonus_kes}}. Final approval is in progress.</p>"},
    {"key": "comp.bonus_paid", "module": "Compensation", "name": "Bonus Approved & Paid",
     "subject": "Your bonus has been processed", "merge_tags": ["employee_name","bonus_kes","reference"],
     "body": "<p>Hi {{employee_name}},</p><p>A bonus of <strong>KES {{bonus_kes}}</strong> has been processed (ref: {{reference}}).</p>"},

    # ---------------- Recognition ----------------
    {"key": "recognition.peer", "module": "Recognition", "name": "Peer Recognition Received",
     "subject": "You've been recognised by a peer", "merge_tags": ["employee_name","from_name","nominator_name","values","behaviour","message","impact"],
     "body": "<p>Hi {{employee_name}},</p><p><strong>{{from_name}}</strong> just recognised you against Solvit's core values.</p><p><strong>Values:</strong> {{values}}</p><p><strong>What you did:</strong><br/><em>\"{{behaviour}}\"</em></p><p><strong>Impact:</strong><br/>{{impact}}</p><p>Thank you for living the Solvit values — your nomination is now pending HR review.</p><p>— Solvit People Platform</p>"},
    {"key": "recognition.manager", "module": "Recognition", "name": "Manager Recognition Issued",
     "subject": "Recognition from your manager", "merge_tags": ["employee_name","manager_name","behaviour","message","impact"],
     "body": "<p>Hi {{employee_name}},</p><p>Your manager <strong>{{manager_name}}</strong> has formally recognised your work.</p><p><strong>What stood out:</strong><br/><em>\"{{behaviour}}\"</em></p><p><strong>Impact:</strong><br/>{{impact}}</p><p>Keep it up.</p><p>— Solvit People Platform</p>"},
    {"key": "recognition.long_service", "module": "Recognition", "name": "Long Service Award",
     "subject": "Long service award — {{years}} years", "merge_tags": ["employee_name","years"],
     "body": "<p>Hi {{employee_name}},</p><p>Thank you for {{years}} years of service at Solvit. Congratulations!</p>"},

    # ---------------- Disciplinary ----------------
    {"key": "disciplinary.hearing", "module": "Disciplinary", "name": "Disciplinary Hearing Invitation",
     "subject": "Disciplinary hearing invitation — {{case_ref}}", "merge_tags": ["employee_name","case_ref","allegation","notice_content","response_deadline","hr_name"],
     "body": "<p>Dear {{employee_name}},</p><p>You are invited to a formal disciplinary hearing on the matter referenced <strong>{{case_ref}}</strong>.</p><p><strong>Allegation:</strong> {{allegation}}</p><p><strong>Notice:</strong><br/>{{notice_content}}</p><p>Please submit your written response by <strong>{{response_deadline}}</strong>.</p><p>Regards,<br/>{{hr_name}}<br/>Solvit HR & Admin</p>"},
    {"key": "disciplinary.written", "module": "Disciplinary", "name": "Written Warning Issued",
     "subject": "Written warning — {{case_ref}}", "merge_tags": ["employee_name","case_ref","allegation","notice_content","response_deadline","hr_name"],
     "body": "<p>Dear {{employee_name}},</p><p>A <strong>written warning</strong> has been formally issued on case <strong>{{case_ref}}</strong>.</p><p><strong>Allegation:</strong> {{allegation}}</p><p><strong>Notice:</strong><br/>{{notice_content}}</p><p>If you wish to respond, please do so by <strong>{{response_deadline}}</strong>.</p><p>Regards,<br/>{{hr_name}}</p>"},
    {"key": "disciplinary.final", "module": "Disciplinary", "name": "Final Written Warning",
     "subject": "FINAL written warning — {{case_ref}}", "merge_tags": ["employee_name","case_ref","allegation","notice_content","response_deadline","hr_name"],
     "body": "<p>Dear {{employee_name}},</p><p>A <strong>FINAL written warning</strong> has been formally issued on case <strong>{{case_ref}}</strong>.</p><p><strong>Allegation:</strong> {{allegation}}</p><p><strong>Notice:</strong><br/>{{notice_content}}</p><p>If you wish to respond, please do so by <strong>{{response_deadline}}</strong>.</p><p>Regards,<br/>{{hr_name}}</p>"},
    {"key": "disciplinary.dismissal", "module": "Disciplinary", "name": "Dismissal Notification",
     "subject": "Notice of dismissal — {{case_ref}}", "merge_tags": ["employee_name","case_ref","allegation","notice_content","response_deadline","hr_name"],
     "body": "<p>Dear {{employee_name}},</p><p>Following the disciplinary process on case <strong>{{case_ref}}</strong>, your employment with Solvit Limited is hereby terminated.</p><p><strong>Allegation:</strong> {{allegation}}</p><p><strong>Notice:</strong><br/>{{notice_content}}</p><p>Any final representation must be submitted by <strong>{{response_deadline}}</strong>.</p><p>Regards,<br/>{{hr_name}}</p>"},

    # ---------------- Policies ----------------
    {"key": "policy.published", "module": "Policies", "name": "New Policy Published",
     "subject": "New policy: {{policy_title}} (v{{policy_version}})", "merge_tags": ["employee_name","policy_title","policy_version","category","effective_date","platform_link"],
     "body": "<p>Hi {{employee_name}},</p><p>A new policy has been published.</p><p><strong>Policy:</strong> {{policy_title}}<br/><strong>Version:</strong> {{policy_version}}<br/><strong>Category:</strong> {{category}}<br/><strong>Effective from:</strong> {{effective_date}}</p><p><a href=\"{{platform_link}}\">Open in the platform</a> to read and acknowledge.</p>"},
    {"key": "policy.ack_request", "module": "Policies", "name": "Policy Acknowledgement Request",
     "subject": "Please acknowledge: {{policy_name}}", "merge_tags": ["employee_name","policy_name","deadline","link"],
     "body": "<p>Hi {{employee_name}},</p><p>Please acknowledge <strong>{{policy_name}}</strong> by {{deadline}}.</p><p><a href=\"{{link}}\">Read & acknowledge</a></p>"},
    {"key": "policy.ack_overdue", "module": "Policies", "name": "Policy Acknowledgement Overdue",
     "subject": "Overdue: {{policy_name}}", "merge_tags": ["employee_name","policy_name","days_overdue"],
     "body": "<p>Hi {{employee_name}},</p><p>Your acknowledgement of {{policy_name}} is {{days_overdue}} day(s) overdue.</p>"},

    # ---------------- Budget ----------------
    {"key": "budget.tier_confirm_request", "module": "Budget", "name": "Annual Tier Confirmation Request",
     "subject": "Action required: Tier confirmation", "merge_tags": ["finance_name","period_label"],
     "body": "<p>Hi {{finance_name}},</p><p>Please confirm the GP Actual for {{period_label}} to unlock Tier 1 / Tier 2 envelopes.</p>"},
    {"key": "budget.tier_status_change", "module": "Budget", "name": "Tier Status Change Notification",
     "subject": "Tier status updated — {{new_tier}} active", "merge_tags": ["new_tier","period_label"],
     "body": "<p>The tier status has been updated. <strong>{{new_tier}}</strong> is now active for {{period_label}}.</p>"},

    # ---------------- Compliance ----------------
    {"key": "compliance.deadline_reminder", "module": "Compliance", "name": "Compliance Deadline Reminder",
     "subject": "{{filing_name}} due in {{days_ahead}} days", "merge_tags": ["filing_name","due_date","days_ahead"],
     "body": "<p>Reminder: <strong>{{filing_name}}</strong> is due on {{due_date}} ({{days_ahead}} days from now).</p>"},
    {"key": "compliance.statutory_due", "module": "Compliance", "name": "Statutory Filing Due",
     "subject": "Statutory filing due — {{filing_name}}", "merge_tags": ["filing_name","due_date","amount_kes"],
     "body": "<p>Statutory filing <strong>{{filing_name}}</strong> is due on {{due_date}}. Amount: KES {{amount_kes}}.</p>"},

    # ---------------- System & Account ----------------
    {"key": "system.account_created", "module": "System & Account", "name": "New User Account Created",
     "subject": "Your Solvit account is ready", "merge_tags": ["full_name","email","temp_password","login_url"],
     "body": "<p>Hi {{full_name}},</p><p>Your account has been created.</p><p>Email: {{email}}<br/>Temporary password: <strong>{{temp_password}}</strong></p><p><a href=\"{{login_url}}\">Sign in</a></p>"},
    {"key": "system.password_reset", "module": "System & Account", "name": "Password Reset",
     "subject": "Reset your Solvit password", "merge_tags": ["full_name","reset_link","expires_in"],
     "body": "<p>Hi {{full_name}},</p><p>Reset your password using this link: <a href=\"{{reset_link}}\">{{reset_link}}</a>. It expires in {{expires_in}}.</p>"},
    {"key": "system.account_deactivated", "module": "System & Account", "name": "Account Deactivated",
     "subject": "Your Solvit account has been deactivated", "merge_tags": ["full_name","effective_date"],
     "body": "<p>Hi {{full_name}},</p><p>Your account has been deactivated effective {{effective_date}}. Contact HR if this is unexpected.</p>"},

    # ---------------- Formal documents (always real email regardless of mode) ----
    {"key": "disciplinary.show_cause", "module": "Disciplinary", "name": "Notice to Show Cause",
     "subject": "FORMAL NOTICE — Show Cause: {{employee_name}}", "merge_tags": ["employee_name","allegation_category","incident_date","response_due_date","hr_name","platform_link"],
     "body": "<p>Dear {{employee_name}},</p><p>You are hereby required to show cause in writing as to why disciplinary action should not be taken against you for an alleged incident in the <strong>{{allegation_category}}</strong> category occurring on or about {{incident_date}}.</p><p>Your written response must be submitted by <strong>{{response_due_date}}</strong>. Please review and sign the formal notice at: {{platform_link}}.</p><p>Regards,<br/>{{hr_name}}<br/>Solvit Limited HR & Admin</p>"},
    {"key": "exit.confidentiality_ack", "module": "Exit", "name": "Post-Employment Confidentiality Acknowledgement",
     "subject": "FORMAL — Confidentiality & Non-Solicitation Acknowledgement", "merge_tags": ["employee_name","last_working_date","platform_link"],
     "body": "<p>Dear {{employee_name}},</p><p>As part of your separation from Solvit Limited effective <strong>{{last_working_date}}</strong>, please review and digitally sign the Post-Employment Confidentiality & Non-Solicitation Acknowledgement at: {{platform_link}}.</p><p>This is a mandatory legal document that must be signed before your final pay is released.</p>"},
    {"key": "retention.flight_risk_alert", "module": "Retention", "name": "CONFIDENTIAL — Flight Risk Alert",
     "subject": "CONFIDENTIAL — Critical flight risk: {{employee_name}}", "merge_tags": ["employee_name","risk_tier","flag_date","platform_link"],
     "body": "<p><strong>CONFIDENTIAL — HR / LM eyes only.</strong></p><p>{{employee_name}} has crossed the {{risk_tier}} flight risk threshold on {{flag_date}}. Recommend immediate stay-interview or 1:1.</p><p>View retention dashboard: {{platform_link}}</p>"},
    {"key": "budget.allocation_submitted", "module": "Budget", "name": "HR Budget Allocation Submitted",
     "subject": "Budget allocation for review — {{initiative_name}}", "merge_tags": ["initiative_name","amount_kes","linked_module","submitted_by","budget_cycle","platform_link"],
     "body": "<p>HR has submitted a budget allocation requiring your approval.</p><p><strong>Initiative:</strong> {{initiative_name}}<br/><strong>Amount:</strong> KES {{amount_kes}}<br/><strong>Module:</strong> {{linked_module}}<br/><strong>Submitted by:</strong> {{submitted_by}}<br/><strong>Cycle:</strong> {{budget_cycle}}</p><p>Review: {{platform_link}}</p>"},
    {"key": "leave.cancelled", "module": "Leave", "name": "Leave Cancellation",
     "subject": "Leave cancelled — {{employee_name}}", "merge_tags": ["employee_name","leave_type","start_date","end_date"],
     "body": "<p>{{employee_name}} has cancelled the {{leave_type}} leave scheduled {{start_date}} → {{end_date}}.</p>"},
    {"key": "performance.self_review_submitted", "module": "Performance", "name": "Self-Review Received — Manager Review Open",
     "subject": "Self-review received from {{employee_name}}", "merge_tags": ["employee_name","review_period","manager_review_due_date","platform_link"],
     "body": "<p>{{employee_name}} has submitted their self-review for {{review_period}}. Your manager review is due by {{manager_review_due_date}}.</p><p>Open: {{platform_link}}</p>"},
    {"key": "onboarding.probation_confirmed", "module": "Onboarding", "name": "Probation Confirmed",
     "subject": "Congratulations — Probation Confirmed", "merge_tags": ["employee_first_name","employee_role","confirmation_date","hr_name"],
     "body": "<p>Hi {{employee_first_name}},</p><p>Congratulations — your probation period has been successfully confirmed effective {{confirmation_date}}. You are now a fully confirmed member of the Solvit team in the role of {{employee_role}}.</p><p>Warm regards,<br/>{{hr_name}}</p>"},
    {"key": "onboarding.probation_extended", "module": "Onboarding", "name": "Probation Extended",
     "subject": "Probation Period Extended — Action Required", "merge_tags": ["employee_first_name","employee_role","extension_end_date","line_manager_name","hr_name","platform_link"],
     "body": "<p>Hi {{employee_first_name}},</p><p>Following review, your probation period has been extended until <strong>{{extension_end_date}}</strong>. {{line_manager_name}} will set up a check-in to discuss focus areas.</p><p>View action plan: {{platform_link}}</p><p>Regards,<br/>{{hr_name}}</p>"},
]


async def _ensure_seeded(db):
    existing_docs = {d["key"]: d async for d in db.email_templates.find({"tenant_id": "solvit"})}
    docs = []
    now = datetime.now(timezone.utc).isoformat()
    for t in DEFAULT_TEMPLATES:
        cur = existing_docs.get(t["key"])
        if cur is None:
            docs.append({
                **t,
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "is_default": True,
                "updated_at": now,
                "updated_by": "system_seed",
            })
            continue
        # Refresh defaults that have NOT been manually edited by an IT Admin.
        # We treat updated_by == "system_seed" (or unset) as "still default" and
        # safely overwrite the body/subject/merge_tags so callers get the latest
        # canonical template. Any IT-Admin edit will set updated_by to the
        # user id, preserving customisations.
        if cur.get("updated_by") in (None, "system_seed"):
            await db.email_templates.update_one(
                {"_id": cur["_id"]},
                {"$set": {
                    "subject": t["subject"],
                    "body": t["body"],
                    "merge_tags": t.get("merge_tags") or [],
                    "name": t["name"],
                    "module": t["module"],
                    "is_default": True,
                    "updated_at": now,
                    "updated_by": "system_seed",
                }}
            )
    if docs:
        await db.email_templates.insert_many(docs)


def _read_role(user):
    return user.get("role")


def _can_edit(role):
    return role == "it_admin"


def _can_view(role):
    return role in ("it_admin", "hr_admin", "hr_manager")


@router.get("")
async def list_templates(request: Request):
    user = await get_current_user(request)
    if not _can_view(_read_role(user)):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    await _ensure_seeded(db)
    rows = await db.email_templates.find({"tenant_id": "solvit"}).sort([("module", 1), ("name", 1)]).to_list(500)
    grouped = {}
    for r in rows:
        r.pop("_id", None)
        grouped.setdefault(r.get("module", "Other"), []).append({
            "id": r.get("id"), "key": r.get("key"), "name": r.get("name"),
            "module": r.get("module"), "subject": r.get("subject"),
            "merge_tags": r.get("merge_tags") or [],
            "updated_at": r.get("updated_at"), "updated_by_name": r.get("updated_by_name") or r.get("updated_by"),
        })
    return {"can_edit": _can_edit(_read_role(user)), "groups": grouped, "count": len(rows)}


@router.get("/{key}")
async def get_template(key: str, request: Request):
    user = await get_current_user(request)
    if not _can_view(_read_role(user)):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    await _ensure_seeded(db)
    t = await db.email_templates.find_one({"tenant_id": "solvit", "key": key})
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    t.pop("_id", None)
    t["can_edit"] = _can_edit(_read_role(user))
    return t


@router.put("/{key}")
async def update_template(key: str, request: Request):
    user = await get_current_user(request)
    if not _can_edit(_read_role(user)):
        raise HTTPException(status_code=403, detail="Only IT Admin can edit templates")
    db = get_db()
    body = await request.json()
    update = {
        "subject": body.get("subject"),
        "body": body.get("body"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["id"],
        "updated_by_name": user.get("full_name") or user.get("email"),
        "is_default": False,
    }
    result = await db.email_templates.find_one_and_update(
        {"tenant_id": "solvit", "key": key},
        {"$set": update},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    result.pop("_id", None)
    return result


@router.post("/{key}/reset")
async def reset_template(key: str, request: Request):
    user = await get_current_user(request)
    if not _can_edit(_read_role(user)):
        raise HTTPException(status_code=403, detail="Only IT Admin can reset templates")
    default = next((t for t in DEFAULT_TEMPLATES if t["key"] == key), None)
    if not default:
        raise HTTPException(status_code=404, detail="No default for this template")
    db = get_db()
    update = {
        "subject": default["subject"], "body": default["body"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["id"], "updated_by_name": user.get("full_name") or user.get("email"),
        "is_default": True,
    }
    result = await db.email_templates.find_one_and_update(
        {"tenant_id": "solvit", "key": key}, {"$set": update}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    result.pop("_id", None)
    return result


@router.post("/{key}/preview")
async def preview_template(key: str, request: Request):
    user = await get_current_user(request)
    if not _can_view(_read_role(user)):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    t = await db.email_templates.find_one({"tenant_id": "solvit", "key": key})
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    body = await request.json()
    sample = body.get("merge_values") or {}
    # Reasonable defaults so the preview is never empty:
    defaults = {
        "employee_name": "Jane Doe", "manager_name": "Sarah Njoroge",
        "candidate_name": "Sample Candidate", "solver_name": "Peter Solver",
        "cycle_label": "H1 2026", "deadline": "31/05/2026", "due_date": "15/04/2026",
        "leave_type": "Annual", "start_date": "01/06/2026", "end_date": "10/06/2026", "days": "8",
        "reason": "—", "remaining_days": "5", "training_name": "Sample Training",
        "policy_name": "Code of Conduct", "summary": "Updated for 2026", "link": "https://solvit.co.ke/policies",
        "amount_kes": "25,000", "salary_kes": "120,000", "bonus_kes": "60,000",
        "reference": "REF-12345", "role_title": "Inspections Analyst",
        "office_address": "Solvit HQ · Westlands, Nairobi",
        "interview_datetime": "15/06/2026 10:00 EAT",
        "filing_name": "PAYE", "days_ahead": "7",
        "full_name": "Jane Doe", "email": "jane.doe@solvit.co.ke",
        "temp_password": "<<sample-temp-pw>>", "login_url": "https://solvit.co.ke/login",
        "new_salary_kes": "135,000", "effective_date": "01/03/2026",
        "from_name": "Peer Reviewer", "message": "Outstanding work on Q1 targets!",
        "years": "5",
        "new_tier": "Tier 1", "old_tier": "Tier 2", "period_label": "Q4 2025",
        "login_code": "SOL-1234", "app_link": "https://solvit.co.ke/solver-app",
        "test_link": "https://solvit.co.ke/tests/abc",
        "checkin_date": "15/05/2026", "review_date": "30/06/2026",
        "case_summary": "Conduct review", "valid_until": "31/12/2026",
        "next_steps": "Disciplinary hearing scheduled.", "expiry_date": "20/02/2026",
        "duration_weeks": "8", "pending_count": "3", "hearing_date": "10/04/2026",
        "reset_link": "https://solvit.co.ke/reset/abc123", "expires_in": "30 minutes",
        "finance_name": "Sarah Njoroge", "new_end_date": "01/08/2026",
        "interview_date": "12/05/2026", "meeting_date": "20/04/2026",
        "overall_score": "1.2", "project_name": "Inspection App v2", "reward_kes": "45,000",
    }
    merged = {**defaults, **sample}

    def render(tpl: str) -> str:
        import re
        return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", lambda m: str(merged.get(m.group(1), m.group(0))), tpl or "")

    return {
        "subject": render(t.get("subject")),
        "body_html": render(t.get("body")),
        "merge_values_used": merged,
    }
