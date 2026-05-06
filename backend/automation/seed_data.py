"""Seed initial data for the Solvit People Platform"""
from datetime import datetime, timezone
from utils.auth import hash_password
import uuid


DEMO_USERS = [
    {"email": "jessica@solvit.co.ke", "full_name": "Jessica Mwangi", "role": "hr_admin", "department": "HR_People", "password": "Solvit@2026"},
    {"email": "manager@solvit.co.ke", "full_name": "David Ochieng", "role": "line_manager", "department": "Operations", "password": "Solvit@2026"},
    {"email": "finance@solvit.co.ke", "full_name": "Sarah Njoroge", "role": "finance", "department": "Finance", "password": "Solvit@2026"},
    {"email": "employee@solvit.co.ke", "full_name": "James Kamau", "role": "employee", "department": "Commercial", "password": "Solvit@2026"},
    {"email": "solver@solvit.co.ke", "full_name": "Peter Njoroge", "role": "solver", "department": None, "password": "Solvit@2026"},
    {"email": "md@solvit.co.ke", "full_name": "Michael Omondi", "role": "executive", "department": "Leadership", "password": "Solvit@2026"},
]

PAY_BANDS = [
    {"band": "L1", "min_kes": 25000, "mid_kes": 35000, "max_kes": 44000, "roles": ["Entry-level roles across departments"]},
    {"band": "L2", "min_kes": 55000, "mid_kes": 72000, "max_kes": 88000, "roles": ["Account Manager", "Business Development Lead", "Valuation Officer", "Customer Support Executive"]},
    {"band": "L3", "min_kes": 55000, "mid_kes": 78000, "max_kes": 100000, "roles": ["Senior Account Manager", "Technical Services Manager", "HR & Administration Manager"]},
    {"band": "L4", "min_kes": 80000, "mid_kes": 115000, "max_kes": 150000, "roles": ["Operations Manager", "Finance Manager", "IT Support Specialist", "Growth Captain", "Solvers Manager"]},
    {"band": "L5", "min_kes": 196000, "mid_kes": 280000, "max_kes": 364000, "roles": ["Managing Director", "Executive Director"]},
    {"band": "B1a", "min_kes": 10000, "mid_kes": 10000, "max_kes": 10000, "roles": ["Non-Executive Board Member"], "note": "KES 10,000 per meeting (4 meetings p.a.)"},
]

KENYA_HOLIDAYS_2026 = [
    {"date": "2026-01-01", "name": "New Year's Day", "type": "Public"},
    {"date": "2026-04-03", "name": "Good Friday", "type": "Public"},
    {"date": "2026-04-06", "name": "Easter Monday", "type": "Public"},
    {"date": "2026-05-01", "name": "Labour Day", "type": "Public"},
    {"date": "2026-06-01", "name": "Madaraka Day", "type": "Public"},
    {"date": "2026-10-10", "name": "Huduma Day", "type": "Public"},
    {"date": "2026-10-20", "name": "Mashujaa Day", "type": "Public"},
    {"date": "2026-12-12", "name": "Jamhuri Day", "type": "Public"},
    {"date": "2026-12-25", "name": "Christmas Day", "type": "Public"},
    {"date": "2026-12-26", "name": "Boxing Day", "type": "Public"},
    {"date": "2026-03-29", "name": "Eid al-Fitr (est.)", "type": "Public", "note": "Subject to moon sighting"},
    {"date": "2026-06-06", "name": "Eid al-Adha (est.)", "type": "Public", "note": "Subject to moon sighting"},
]

AUTOMATION_RULES = [
    # Onboarding
    {"rule_id": "AR-OB-01", "trigger_type": "event", "trigger_event": "employee_created", "action_type": "create_task", "action_payload_json": {"task_type": "onboarding_setup", "description": "Create 19 onboarding checklist items. Send welcome email."}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Onboarding", "description": "New FTE employee created — trigger full onboarding workflow"},
    {"rule_id": "AR-OB-02", "trigger_type": "event", "trigger_event": "employee_start_date_reached", "action_type": "change_state", "action_payload_json": {"new_state": "Onboarding"}, "notification_recipients_json": ["employee", "line_manager"], "category": "Onboarding", "description": "Day 1 — set lifecycle to Onboarding"},
    {"rule_id": "AR-OB-03", "trigger_type": "event", "trigger_event": "md_onboarding_meeting_completed", "action_type": "change_state", "action_payload_json": {"new_state": "Probation"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Onboarding", "description": "MD Onboarding Meeting complete — transition to Probation"},
    {"rule_id": "AR-OB-04", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "onboarding_overdue", "days_overdue": 3}, "notification_recipients_json": ["task_owner"], "category": "Onboarding", "description": "Onboarding task 3 days overdue — send reminder"},
    {"rule_id": "AR-OB-05", "trigger_type": "event", "trigger_event": "solver_registered", "action_type": "create_task", "action_payload_json": {"task_type": "solver_induction", "description": "Create 6-step Solver induction task list"}, "notification_recipients_json": ["line_manager", "hr_admin"], "category": "Onboarding", "description": "Solver registered — create induction tasks"},
    {"rule_id": "AR-OB-06", "trigger_type": "event", "trigger_event": "solver_induction_complete", "action_type": "send_notification", "action_payload_json": {"message": "Prompt Solvers Manager to review and activate"}, "notification_recipients_json": ["line_manager", "hr_admin"], "category": "Onboarding", "description": "Solver completes induction — prompt manager activation"},
    # Probation
    {"rule_id": "AR-PR-01", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "create_task", "action_payload_json": {"check": "probation_month_1", "days_since_probation": 28}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Probation", "description": "28 days in Probation — create Month 1 review task"},
    {"rule_id": "AR-PR-02", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "create_task", "action_payload_json": {"check": "probation_month_2", "days_since_probation": 56}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Probation", "description": "56 days — Month 2 probation review task"},
    {"rule_id": "AR-PR-03", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "create_task", "action_payload_json": {"check": "probation_month_3", "days_since_probation": 84}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Probation", "description": "84 days — Month 3 final probation review"},
    {"rule_id": "AR-PR-04", "trigger_type": "event", "trigger_event": "probation_passed", "action_type": "change_state", "action_payload_json": {"new_state": "Active"}, "notification_recipients_json": ["hr_admin", "line_manager", "employee"], "category": "Probation", "description": "Probation passed — transition to Active"},
    {"rule_id": "AR-PR-05", "trigger_type": "event", "trigger_event": "probation_extended", "action_type": "create_task", "action_payload_json": {"task_type": "probation_extension"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Probation", "description": "Probation extended — set 28-day extension trigger"},
    {"rule_id": "AR-PR-06", "trigger_type": "event", "trigger_event": "probation_failed", "action_type": "change_state", "action_payload_json": {"new_state": "Exiting"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Probation", "description": "Probation failed — transition to Exiting"},
    {"rule_id": "AR-PR-07", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "probation_review_overdue", "days_overdue": 3}, "notification_recipients_json": ["hr_admin"], "category": "Probation", "description": "Probation review overdue 3 days — escalate to HR Admin"},
    # Performance
    {"rule_id": "AR-PF-01", "trigger_type": "event", "trigger_event": "review_cycle_activated", "action_type": "create_task", "action_payload_json": {"task_type": "send_peer_reviews"}, "notification_recipients_json": ["all_active_fte", "hr_admin"], "category": "Performance", "description": "HR activates review cycle — send peer review forms"},
    {"rule_id": "AR-PF-02", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "peer_review_completion", "days_after_cycle_start": 7}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "Week 1 closes — alert HR if <3 peer reviewers"},
    {"rule_id": "AR-PF-03", "trigger_type": "event", "trigger_event": "all_section_scores_compiled", "action_type": "send_notification", "action_payload_json": {"message": "Scores ready for review meeting scheduling"}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "All scores compiled — make available to HR"},
    {"rule_id": "AR-PF-04", "trigger_type": "event", "trigger_event": "performance_score_calculated", "action_type": "create_task", "action_payload_json": {"check": "score_below_threshold", "threshold": 2.49, "task": "realignment_protocol"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Performance", "description": "Score Below — create Realignment Protocol task"},
    {"rule_id": "AR-PF-05", "trigger_type": "event", "trigger_event": "performance_score_calculated", "action_type": "send_notification", "action_payload_json": {"check": "score_forfeited", "threshold": 2.5, "message": "Critical: PIP or Exit decision required"}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "Score Forfeited — notify HR for PIP/Exit decision"},
    {"rule_id": "AR-PF-06", "trigger_type": "event", "trigger_event": "performance_score_calculated", "action_type": "send_notification", "action_payload_json": {"check": "score_exceeded", "threshold": 1.49, "message": "Employee eligible for Project Ownership"}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "Score Exceeded — set project_ownership_eligible = true"},
    {"rule_id": "AR-PF-07", "trigger_type": "event", "trigger_event": "review_cycle_completed", "action_type": "send_notification", "action_payload_json": {"message": "Update employee records. Prompt salary review."}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "Review cycle complete — update records, prompt salary review"},
    {"rule_id": "AR-PF-08", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "review_meeting_overdue", "days_overdue": 5}, "notification_recipients_json": ["hr_admin"], "category": "Performance", "description": "Review meeting overdue 5 days — escalate"},
    # Surveys
    {"rule_id": "AR-SV-01", "trigger_type": "event", "trigger_event": "survey_window_opened", "action_type": "send_notification", "action_payload_json": {"message": "Survey invitation sent to all Active FTE and Solvers"}, "notification_recipients_json": ["all_active_fte", "all_active_solvers"], "category": "Surveys", "description": "Survey window opened — send invitations"},
    {"rule_id": "AR-SV-02", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "survey_completion_below_70pct", "days_in": 7}, "notification_recipients_json": ["non_respondents"], "category": "Surveys", "description": "Day 7: completion <70% — send reminder"},
    {"rule_id": "AR-SV-03", "trigger_type": "event", "trigger_event": "survey_window_closed", "action_type": "send_notification", "action_payload_json": {"message": "Calculate scores and make results available"}, "notification_recipients_json": ["hr_admin"], "category": "Surveys", "description": "Survey window closes — compile results"},
    {"rule_id": "AR-SV-04", "trigger_type": "cron", "trigger_cron": "0 8 1 1 *", "action_type": "create_task", "action_payload_json": {"task_type": "fte_engagement_survey", "window_days": 21}, "notification_recipients_json": ["all_active_fte", "hr_admin"], "category": "Surveys", "description": "Annual FTE Engagement Survey — January Q1"},
    {"rule_id": "AR-SV-05", "trigger_type": "cron", "trigger_cron": "0 8 1 */3 *", "action_type": "create_task", "action_payload_json": {"task_type": "solver_satisfaction_pulse", "window_days": 14}, "notification_recipients_json": ["all_active_solvers", "line_manager"], "category": "Surveys", "description": "Quarterly Solver Satisfaction Pulse"},
    # Retention
    {"rule_id": "AR-RT-01", "trigger_type": "event", "trigger_event": "flight_risk_signal_changed", "action_type": "send_notification", "action_payload_json": {"message": "Recalculate flight risk score"}, "notification_recipients_json": ["hr_admin"], "category": "Retention", "description": "Input signal change — recalculate flight risk"},
    {"rule_id": "AR-RT-02", "trigger_type": "event", "trigger_event": "flight_risk_elevated", "action_type": "create_task", "action_payload_json": {"task_type": "stay_interview", "days_due": 10}, "notification_recipients_json": ["hr_admin"], "category": "Retention", "description": "Risk Elevated — create stay interview task"},
    {"rule_id": "AR-RT-03", "trigger_type": "event", "trigger_event": "flight_risk_high", "action_type": "create_task", "action_payload_json": {"task_type": "urgent_stay_interview", "days_due": 5}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Retention", "description": "Risk High — urgent stay interview task"},
    {"rule_id": "AR-RT-04", "trigger_type": "event", "trigger_event": "flight_risk_critical", "action_type": "send_notification", "action_payload_json": {"message": "CRITICAL: Immediate retention intervention required"}, "notification_recipients_json": ["hr_admin", "line_manager", "executive"], "category": "Retention", "description": "Risk Critical — immediate notification to leadership"},
    {"rule_id": "AR-RT-05", "trigger_type": "cron", "trigger_cron": "0 8 1 9 *", "action_type": "create_task", "action_payload_json": {"task_type": "annual_stay_interviews"}, "notification_recipients_json": ["hr_admin"], "category": "Retention", "description": "Q3 annually — stay interviews for all non-interviewed FTE"},
    {"rule_id": "AR-RT-06", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "stay_interview_overdue", "days_overdue": 5}, "notification_recipients_json": ["hr_admin"], "category": "Retention", "description": "Stay interview overdue 5 days — escalate"},
    # Recognition
    {"rule_id": "AR-RK-01", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "anniversary_2yr"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Recognition", "description": "2-year anniversary — create recognition planning task"},
    {"rule_id": "AR-RK-02", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "anniversary_3yr"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Recognition", "description": "3-year anniversary — recognition task"},
    {"rule_id": "AR-RK-03", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "anniversary_5yr"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Recognition", "description": "5-year anniversary — recognition task"},
    {"rule_id": "AR-RK-04", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "anniversary_7yr"}, "notification_recipients_json": ["hr_admin", "line_manager"], "category": "Recognition", "description": "7-year anniversary — recognition task"},
    {"rule_id": "AR-RK-05", "trigger_type": "cron", "trigger_cron": "0 8 1 1 *", "action_type": "send_notification", "action_payload_json": {"check": "annual_solver_event_60days", "month": 3}, "notification_recipients_json": ["line_manager", "hr_admin"], "category": "Recognition", "description": "60 days before Annual Solver Event — planning checklist"},
    {"rule_id": "AR-RK-06", "trigger_type": "cron", "trigger_cron": "0 8 1 4,7,10,1 *", "action_type": "create_task", "action_payload_json": {"task_type": "solver_quarterly_award", "days_due": 10}, "notification_recipients_json": ["line_manager"], "category": "Recognition", "description": "End of quarter — Solver quarterly award nomination"},
    {"rule_id": "AR-RK-07", "trigger_type": "event", "trigger_event": "project_ownership_eligible", "action_type": "create_task", "action_payload_json": {"task_type": "project_assignment", "days_due": 30}, "notification_recipients_json": ["hr_admin"], "category": "Recognition", "description": "Project Ownership eligible — create assignment task"},
    {"rule_id": "AR-RK-08", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "recognition_calendar_event_30days"}, "notification_recipients_json": ["hr_admin"], "category": "Recognition", "description": "30 days before Recognition Calendar event — notify HR"},
    {"rule_id": "AR-RK-09", "trigger_type": "cron", "trigger_cron": "0 8 1 1,4,7,10 *", "action_type": "create_task", "action_payload_json": {"task_type": "values_champion_nominations", "window_days": 14}, "notification_recipients_json": ["hr_admin", "executive"], "category": "Recognition", "description": "Quarterly Values Champion nomination window"},
    # Exit
    {"rule_id": "AR-EX-01", "trigger_type": "event", "trigger_event": "employee_exiting", "action_type": "trigger_workflow", "action_payload_json": {"workflow": "exit_workflow", "tasks_count": 7}, "notification_recipients_json": ["hr_admin", "line_manager", "it", "finance"], "category": "Exit", "description": "Resignation/Termination — create all 7 exit tasks within 60s"},
    {"rule_id": "AR-EX-02", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "confidentiality_form_incomplete", "days_before_last_day": 5}, "notification_recipients_json": ["employee", "hr_admin"], "category": "Exit", "description": "Confidentiality form incomplete 5 days before last day"},
    {"rule_id": "AR-EX-03", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "last_day_tasks_incomplete"}, "notification_recipients_json": ["hr_admin"], "category": "Exit", "description": "Last day reached with incomplete exit tasks"},
    {"rule_id": "AR-EX-04", "trigger_type": "event", "trigger_event": "all_exit_tasks_completed", "action_type": "change_state", "action_payload_json": {"new_state": "Exited"}, "notification_recipients_json": ["hr_admin", "finance", "it"], "category": "Exit", "description": "All exit tasks done — transition to Exited"},
    {"rule_id": "AR-EX-05", "trigger_type": "event", "trigger_event": "solver_deactivated", "action_type": "send_notification", "action_payload_json": {"message": "Revoke app access. Archive Solver record."}, "notification_recipients_json": ["line_manager", "hr_admin"], "category": "Exit", "description": "Solver deactivated — revoke access, archive"},
    {"rule_id": "AR-EX-06", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "change_state", "action_payload_json": {"check": "solver_inactive_60days", "new_state": "Inactive"}, "notification_recipients_json": ["line_manager", "hr_admin"], "category": "Exit", "description": "Solver 60 days inactive — auto-set Inactive"},
    # Leave
    {"rule_id": "AR-LV-01", "trigger_type": "event", "trigger_event": "leave_request_submitted", "action_type": "send_notification", "action_payload_json": {"message": "Route to Line Manager. 2-day response deadline."}, "notification_recipients_json": ["line_manager"], "category": "Leave", "description": "Leave request submitted — route to Line Manager"},
    {"rule_id": "AR-LV-02", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "leave_request_unactioned", "days": 2}, "notification_recipients_json": ["hr_admin"], "category": "Leave", "description": "Leave unapproved 2 days — escalate to HR Admin"},
    {"rule_id": "AR-LV-03", "trigger_type": "event", "trigger_event": "leave_request_submitted", "action_type": "send_notification", "action_payload_json": {"check": "annual_leave_high_activity_period", "months": [1, 7, 8, 9, 10, 11, 12], "days": 5}, "notification_recipients_json": ["hr_admin"], "category": "Leave", "description": "Leave >5 days in high-activity months — flag to HR Admin"},
    {"rule_id": "AR-LV-04", "trigger_type": "event", "trigger_event": "leave_start_date_reached", "action_type": "change_state", "action_payload_json": {"new_state": "On_Leave"}, "notification_recipients_json": ["hr_admin"], "category": "Leave", "description": "Leave start date — set On Leave badge"},
    {"rule_id": "AR-LV-05", "trigger_type": "event", "trigger_event": "leave_end_date_reached", "action_type": "send_notification", "action_payload_json": {"message": "Prompt employee to confirm return"}, "notification_recipients_json": ["employee", "hr_admin"], "category": "Leave", "description": "Leave end date — prompt return confirmation"},
    # Compliance
    {"rule_id": "AR-CP-01", "trigger_type": "cron", "trigger_cron": "0 8 8 * *", "action_type": "send_notification", "action_payload_json": {"message": "NSSF/SHA remittance deadline in 7 days (15th)"}, "notification_recipients_json": ["finance"], "category": "Compliance", "description": "7 days before NSSF/SHA deadline — remind Finance"},
    {"rule_id": "AR-CP-02", "trigger_type": "cron", "trigger_cron": "0 8 14 * *", "action_type": "send_notification", "action_payload_json": {"message": "URGENT: NSSF/SHA remittance deadline TOMORROW"}, "notification_recipients_json": ["finance"], "category": "Compliance", "description": "1 day before NSSF/SHA deadline — urgent reminder"},
    {"rule_id": "AR-CP-03", "trigger_type": "cron", "trigger_cron": "0 8 2 * *", "action_type": "send_notification", "action_payload_json": {"message": "PAYE filing deadline in 7 days (9th)"}, "notification_recipients_json": ["finance"], "category": "Compliance", "description": "7 days before PAYE filing deadline — remind Finance"},
    {"rule_id": "AR-CP-04", "trigger_type": "cron", "trigger_cron": "0 8 1 12 *", "action_type": "send_notification", "action_payload_json": {"message": "Prompt HR to send re-acknowledgement to all staff"}, "notification_recipients_json": ["hr_admin"], "category": "Compliance", "description": "30 days before annual policy acknowledgement audit"},
    {"rule_id": "AR-CP-05", "trigger_type": "event", "trigger_event": "policy_updated", "action_type": "create_task", "action_payload_json": {"task_type": "policy_acknowledgement", "days_due": 10}, "notification_recipients_json": ["all_relevant_employees", "hr_admin"], "category": "Compliance", "description": "Policy updated — auto-send acknowledgement form"},
    {"rule_id": "AR-CP-06", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "policy_acknowledgement_overdue", "days_overdue": 10}, "notification_recipients_json": ["line_manager"], "category": "Compliance", "description": "Policy acknowledgement overdue 10 days — escalate"},
    {"rule_id": "AR-CP-07", "trigger_type": "cron", "trigger_cron": "0 9 * * *", "action_type": "send_notification", "action_payload_json": {"check": "salary_below_band_minimum", "consecutive_cycles": 2, "via_ai_agent": True}, "notification_recipients_json": ["hr_admin"], "category": "Compliance", "description": "Salary below band minimum 2+ cycles — AI Agent alert"},
    {"rule_id": "AR-CP-08", "trigger_type": "cron", "trigger_cron": "0 8 * * *", "action_type": "send_notification", "action_payload_json": {"check": "solver_accuracy_below_50"}, "notification_recipients_json": ["line_manager"], "category": "Compliance", "description": "Solver accuracy <50 — notify Solvers Manager"},
]

PAY_BAND_ALERTS = [
    {"employee_name": "Jessica Mwangi", "role": "HR & Administration Manager", "band": "L3", "current_salary": 55000, "band_minimum": 55000, "alert_type": "at_minimum", "created_at": "2026-01-01"},
    {"employee_name": "Executive Director", "role": "Executive Director", "band": "L5", "current_salary": 196000, "band_minimum": 196000, "alert_type": "at_minimum", "created_at": "2026-01-01"},
    {"employee_name": "Mary Wanjiru", "role": "Senior Account Manager", "band": "L3", "current_salary": 53000, "band_minimum": 55000, "alert_type": "below_minimum", "created_at": "2026-01-01"},
]

EXIT_INTERVIEW_STEPHEN = {
    "id": str(uuid.uuid4()),
    "tenant_id": "solvit",
    "employee_name": "Stephen Kiragu",
    "department": "Valuation",
    "exit_date": "2026-04-30",
    "tenure_years": 4.5,
    "exit_codes": ["R4", "R3"],
    "exit_code_descriptions": {
        "R4": "Limited career development opportunities",
        "R3": "Compensation and benefits dissatisfaction"
    },
    "interview_date": "2026-04-25",
    "interview_conducted_by": "jessica@solvit.co.ke",
    "lifecycle_state": "Exited",
    "role_title": "Valuation Officer",
    "role_level": "L2",
    "start_date": "2021-10-01",
    "insights": {
        "main_reason": "Lack of progression to senior role despite strong performance",
        "salary_review_requested": True,
        "recommend_solvit": "No",
        "net_promoter_score": 3,
        "key_themes": ["career growth", "compensation", "recognition"]
    },
    "status": "Completed",
    "created_at": "2026-04-25T10:00:00+03:00"
}


async def seed_all(db):
    """Run all seed operations"""
    await seed_users(db)
    await seed_pay_bands(db)
    await seed_automation_rules(db)
    await seed_holidays(db)
    await seed_demo_employees(db)
    await seed_exit_interview(db)
    await seed_pay_band_alerts(db)
    await seed_performance_reviews(db)
    await seed_notifications_and_stay_interviews(db)
    print("✅ All seed data loaded successfully")


async def seed_notifications_and_stay_interviews(db):
    """Seed sample notifications and a stay interview so UIs have data"""
    if await db.notifications.count_documents({"tenant_id": "solvit"}) == 0:
        # Find HR admin user
        hr = await db.users.find_one({"role": "hr_admin", "tenant_id": "solvit"})
        hr_id = str(hr.get("id", str(hr["_id"]))) if hr else None
        notifs = [
            {"title": "[Compliance] PAYE deadline approaching", "message": "Monthly PAYE remittance is due on the 9th of next month. Confirm KRA submission.", "recipient_role": "hr_admin", "category": "Compliance", "is_read": False},
            {"title": "[Probation] Review due — John Mwangi", "message": "John Mwangi's 3-month probation review is due in 7 days.", "recipient_role": "hr_admin", "category": "Probation", "is_read": False},
            {"title": "[Pay Band] 3 employees below band minimum", "message": "Pay band compliance: 3 employees flagged. Review Compensation page.", "recipient_role": "hr_admin", "category": "Compensation", "is_read": False},
            {"title": "[Onboarding] Robert Kiprop overdue", "message": "Robert's onboarding day-7 task list has 2 overdue items.", "recipient_role": "hr_admin", "category": "Onboarding", "is_read": True},
        ]
        docs = [{**n, "id": str(uuid.uuid4()), "tenant_id": "solvit", "recipient_id": hr_id, "data": {}, "created_at": datetime.now(timezone.utc).isoformat()} for n in notifs]
        await db.notifications.insert_many(docs)
        print(f"✅ {len(docs)} demo notifications seeded")

    if await db.stay_interviews.count_documents({"tenant_id": "solvit"}) == 0:
        # Pick an active employee at elevated risk (or just first active)
        emp = await db.employees.find_one({"tenant_id": "solvit", "lifecycle_state": "Active"})
        if emp:
            emp_id = str(emp.get("id", str(emp["_id"])))
            doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "employee_id": emp_id,
                "employee_name": emp.get("full_name"),
                "scheduled_date": (datetime.now(timezone.utc).replace(hour=10, minute=0)).isoformat()[:16],
                "status": "Scheduled",
                "trigger_reason": "Elevated flight risk score (alignment + tenure)",
                "what_makes_stay": None,
                "what_might_leave": None,
                "career_path_clear": None,
                "manager_support_rating": None,
                "agreed_actions": None,
                "follow_up_date": None,
                "conducted_by": "system",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.stay_interviews.insert_one(doc)
            print("✅ 1 demo stay interview seeded")


async def reset_demo_data(db):
    """Reset all demo data (keeps users intact)"""
    collections_to_reset = [
        "employees", "solvers", "candidates", "performance_reviews",
        "leave_requests", "training_requests", "idps", "skills_matrix",
        "policies", "policy_acknowledgements", "disciplinary_cases",
        "case_documents", "projects", "recognitions", "solver_awards",
        "exit_interviews", "pay_band_alerts", "tasks", "notifications",
        "calendar_events", "form_submissions", "salary_reviews",
        "gp_records", "gp_gate", "ai_conversations", "onboarding_tasks",
        "stay_interviews", "flight_risk_history"
    ]
    for col in collections_to_reset:
        await db[col].delete_many({"tenant_id": "solvit"})
    # Re-seed everything except users (users already exist and we keep them)
    await seed_pay_bands(db)
    await seed_holidays(db)
    await seed_demo_employees(db)
    await seed_exit_interview(db)
    await seed_pay_band_alerts(db)
    await seed_performance_reviews(db)
    await seed_notifications_and_stay_interviews(db)
    print("✅ Demo data reset completed")


async def seed_users(db):
    """Seed demo user accounts"""
    for user_data in DEMO_USERS:
        existing = await db.users.find_one({"email": user_data["email"]})
        if existing:
            # Update password in case it changed
            if not __import__('bcrypt').checkpw(user_data["password"].encode(), existing["password_hash"].encode()):
                await db.users.update_one(
                    {"email": user_data["email"]},
                    {"$set": {"password_hash": hash_password(user_data["password"])}}
                )
        else:
            doc = {
                "id": str(uuid.uuid4()),
                "email": user_data["email"],
                "full_name": user_data["full_name"],
                "role": user_data["role"],
                "department": user_data.get("department"),
                "password_hash": hash_password(user_data["password"]),
                "tenant_id": "solvit",
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            result = await db.users.insert_one(doc)
            doc["employee_id"] = str(result.inserted_id)
            await db.users.update_one({"_id": result.inserted_id}, {"$set": {"employee_id": str(result.inserted_id)}})
    print("✅ Demo users seeded")


async def seed_pay_bands(db):
    """Seed pay band data"""
    await db.pay_bands.delete_many({"tenant_id": "solvit"})
    docs = []
    for pb in PAY_BANDS:
        docs.append({**pb, "id": str(uuid.uuid4()), "tenant_id": "solvit", "created_at": datetime.now(timezone.utc).isoformat()})
    if docs:
        await db.pay_bands.insert_many(docs)
    print("✅ Pay bands seeded")


async def seed_automation_rules(db):
    """Seed automation rules"""
    existing = await db.automation_rules.count_documents({"tenant_id": "solvit"})
    if existing > 0:
        return
    docs = []
    for rule in AUTOMATION_RULES:
        docs.append({
            **rule,
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "is_active": True,
            "last_executed_at": None,
            "last_execution_status": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    if docs:
        await db.automation_rules.insert_many(docs)
    print(f"✅ {len(docs)} automation rules seeded")


async def seed_holidays(db):
    """Seed Kenya public holidays 2026"""
    existing = await db.public_holidays.count_documents({"tenant_id": "solvit", "year": 2026})
    if existing > 0:
        return
    docs = []
    for h in KENYA_HOLIDAYS_2026:
        docs.append({**h, "id": str(uuid.uuid4()), "tenant_id": "solvit", "year": 2026})
    if docs:
        await db.public_holidays.insert_many(docs)
    print("✅ Kenya 2026 holidays seeded")


async def seed_demo_employees(db):
    """Seed demo employee records"""
    existing = await db.employees.count_documents({"tenant_id": "solvit"})
    if existing > 0:
        return

    employees = [
        {"full_name": "Jessica Mwangi", "work_email": "jessica@solvit.co.ke", "department": "HR_People", "role_title": "HR & Administration Manager", "role_level": "L3", "start_date": "2022-03-01", "lifecycle_state": "Active", "current_salary_kes": 85000},
        {"full_name": "David Ochieng", "work_email": "manager@solvit.co.ke", "department": "Operations", "role_title": "Operations Manager", "role_level": "L4", "start_date": "2021-06-15", "lifecycle_state": "Active", "current_salary_kes": 115000},
        {"full_name": "Sarah Njoroge", "work_email": "finance@solvit.co.ke", "department": "Finance", "role_title": "Finance Manager", "role_level": "L4", "start_date": "2020-09-01", "lifecycle_state": "Active", "current_salary_kes": 120000},
        {"full_name": "James Kamau", "work_email": "employee@solvit.co.ke", "department": "Commercial", "role_title": "Account Manager", "role_level": "L2", "start_date": "2024-01-15", "lifecycle_state": "Active", "current_salary_kes": 72000},
        {"full_name": "Michael Omondi", "work_email": "md@solvit.co.ke", "department": "Leadership", "role_title": "Managing Director", "role_level": "L5", "start_date": "2019-01-01", "lifecycle_state": "Active", "current_salary_kes": 280000},
        {"full_name": "Mary Wanjiru", "work_email": "mary.wanjiru@solvit.co.ke", "department": "Commercial", "role_title": "Senior Account Manager", "role_level": "L3", "start_date": "2021-08-01", "lifecycle_state": "Active", "current_salary_kes": 53000},
        {"full_name": "John Mwenda", "work_email": "john.mwenda@solvit.co.ke", "department": "Technology", "role_title": "IT Support Specialist", "role_level": "L4", "start_date": "2023-03-01", "lifecycle_state": "Probation", "current_salary_kes": 95000},
        {"full_name": "Grace Akinyi", "work_email": "grace.akinyi@solvit.co.ke", "department": "Operations", "role_title": "Solvers Manager", "role_level": "L4", "start_date": "2022-11-01", "lifecycle_state": "Active", "current_salary_kes": 100000},
        {"full_name": "Robert Kiprotich", "work_email": "robert.kiprotich@solvit.co.ke", "department": "Operations", "role_title": "Valuation Officer", "role_level": "L2", "start_date": "2026-01-15", "lifecycle_state": "Onboarding", "current_salary_kes": 65000},
        {"full_name": "Stephen Kiragu", "work_email": "s.kiragu@solvit.co.ke", "department": "Valuation", "role_title": "Valuation Officer", "role_level": "L2", "start_date": "2021-10-01", "lifecycle_state": "Exited", "current_salary_kes": 68000},
    ]

    docs = []
    for emp in employees:
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            **emp,
            "preferred_name": None,
            "national_id_number": None,
            "kra_pin": None,
            "nssf_number": None,
            "sha_number": None,
            "phone_number": None,
            "line_manager_id": None,
            "employment_type": "Full_Time",
            "probation_end_date": None,
            "flight_risk_score": None,
            "flight_risk_level": None,
            "last_performance_score": None,
            "last_review_date": None,
            "project_ownership_eligible": False,
            "profile_photo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        docs.append(doc)
    if docs:
        await db.employees.insert_many(docs)

    # Seed a few solvers
    solvers = [
        {"full_name": "Peter Njoroge", "phone_number": "+254712345678", "vehicle_categories": ["Saloon", "SUV"], "zones_covered": ["Zone 1: CBD", "Zone 2: Westlands-Kileleshwa"], "lifecycle_state": "Active", "accuracy_score": 87.5, "reliability_score": 92.0, "timeliness_score": 88.0, "client_rating_average": 4.6, "performance_tier": "High_Performer"},
        {"full_name": "Alice Wairimu", "phone_number": "+254723456789", "vehicle_categories": ["Saloon"], "zones_covered": ["Zone 3: Karen-Langata"], "lifecycle_state": "Active", "accuracy_score": 95.0, "reliability_score": 96.0, "timeliness_score": 94.0, "client_rating_average": 4.9, "performance_tier": "Elite"},
        {"full_name": "Brian Mutua", "phone_number": "+254734567890", "vehicle_categories": ["Truck", "Van"], "zones_covered": ["Zone 4: Eastlands"], "lifecycle_state": "Registering", "accuracy_score": None, "reliability_score": None, "timeliness_score": None, "client_rating_average": None, "performance_tier": None},
    ]
    solver_docs = []
    for s in solvers:
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            **s,
            "kra_pin": None,
            "bank_account_number": None,
            "mpesa_number": s.get("phone_number"),
            "payment_method": "MPesa",
            "solver_agreement_signed": s["lifecycle_state"] == "Active",
            "solver_agreement_date": "2024-01-01" if s["lifecycle_state"] == "Active" else None,
            "activation_date": "2024-01-01" if s["lifecycle_state"] == "Active" else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        solver_docs.append(doc)
    if solver_docs:
        await db.solvers.insert_many(solver_docs)
    print("✅ Demo employees and solvers seeded")


async def seed_exit_interview(db):
    """Seed Stephen Kiragu exit interview"""
    existing = await db.exit_interviews.find_one({"employee_name": "Stephen Kiragu", "tenant_id": "solvit"})
    if existing:
        return
    await db.exit_interviews.insert_one({**EXIT_INTERVIEW_STEPHEN, "tenant_id": "solvit"})
    print("✅ Stephen Kiragu exit interview seeded")


async def seed_pay_band_alerts(db):
    """Seed pay band alerts"""
    existing = await db.pay_band_alerts.count_documents({"tenant_id": "solvit"})
    if existing > 0:
        return
    docs = [{**a, "id": str(uuid.uuid4()), "tenant_id": "solvit", "status": "Active", "created_at": datetime.now(timezone.utc).isoformat()} for a in PAY_BAND_ALERTS]
    await db.pay_band_alerts.insert_many(docs)
    print("✅ Pay band alerts seeded")


async def seed_performance_reviews(db):
    """Seed completed performance reviews so 9-box matrix has data"""
    existing = await db.performance_reviews.count_documents({"tenant_id": "solvit"})
    if existing > 0:
        return
    employees = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}).to_list(50)
    # Sample 9-box placements distributed across employees
    placements = [
        ("Stars", 1.2, "Exceeded", 95.0),
        ("Stars", 1.3, "Exceeded", 92.0),
        ("Core_Contributor", 1.7, "Met", 78.0),
        ("Core_Contributor", 1.8, "Met", 76.0),
        ("Core_Contributor", 1.9, "Met", 74.0),
        ("Culture_Risk", 1.6, "Met", 65.0),
        ("Realignment_Needed", 2.2, "Below", 55.0),
        ("Exit_Track", 2.6, "Forfeited", 35.0),
    ]
    docs = []
    employee_score_updates = []
    for i, emp in enumerate(employees[:len(placements)]):
        placement, score, rating, density = placements[i]
        emp_id = str(emp.get("id", str(emp["_id"])))
        rev = {
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "employee_id": emp_id,
            "cycle_type": "Year_End",
            "cycle_year": datetime.now(timezone.utc).year,
            "section_a_score": score - 0.1,
            "section_b_score": score,
            "section_c_score": score + 0.1,
            "overall_score": score,
            "rating": rating,
            "nine_box_placement": placement,
            "talent_density_pct": density,
            "consequence_workflow": None,
            "form_data_json": {},
            "employee_signature": "Auto-seeded",
            "manager_signature": "Auto-seeded",
            "hr_signature": "Auto-seeded",
            "employee_signature_at": datetime.now(timezone.utc).isoformat(),
            "manager_signature_at": datetime.now(timezone.utc).isoformat(),
            "hr_signature_at": datetime.now(timezone.utc).isoformat(),
            "status": "Completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        docs.append(rev)
        employee_score_updates.append((emp_id, score, placement == "Stars"))

    if docs:
        await db.performance_reviews.insert_many(docs)
    # Update employee records with last performance score
    for emp_id, score, eligible in employee_score_updates:
        await db.employees.update_one(
            {"id": emp_id},
            {"$set": {
                "last_performance_score": score,
                "last_review_date": datetime.now(timezone.utc).isoformat()[:10],
                "project_ownership_eligible": eligible
            }}
        )
    print(f"✅ {len(docs)} demo performance reviews seeded")
