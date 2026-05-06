"""Full schemas for the remaining 24 forms (FRD §7). Imported by forms.py."""

# Solvers Code Comprehension Quiz — fill out remaining questions (form-03 had 5 of 10)
FORM_03_FULL_QUESTIONS = [
    {"id": "q4", "label": "Vehicle inspection report must be uploaded within how many hours?", "type": "radio", "required": True,
     "options": ["1 hour", "2 hours", "4 hours", "Same day"], "correct_answer": "2 hours"},
    {"id": "q5", "label": "If a client refuses to allow access to a vehicle component, you should:", "type": "radio", "required": True,
     "options": ["Skip and complete report", "Document the refusal and complete what is accessible", "Cancel the inspection", "Argue with client"],
     "correct_answer": "Document the refusal and complete what is accessible"},
    {"id": "q6", "label": "Which of these is NOT a Solvit non-negotiable value?", "type": "radio", "required": True,
     "options": ["Integrity", "Speed at any cost", "Hard Work & Ownership", "Timeliness"], "correct_answer": "Speed at any cost"},
    {"id": "q7", "label": "Solvers are paid per:", "type": "radio", "required": True,
     "options": ["Hour worked", "Completed inspection", "Monthly retainer", "Distance travelled"], "correct_answer": "Completed inspection"},
    {"id": "q10", "label": "If you discover a major safety defect not requested in the inspection, you should:", "type": "radio", "required": True,
     "options": ["Ignore — out of scope", "Note prominently in report and flag to support", "Tell client only", "Take photos for portfolio"],
     "correct_answer": "Note prominently in report and flag to support"},
]

# 24 form schemas with realistic field structures
EXTRA_SCHEMAS = {
    "form-04": {
        "id": "form-04",
        "title": "Solvit Alignment Survey (FTE)",
        "description": "Quarterly alignment survey — 12 questions across 3 pillars (Environment, Values, Rewards)",
        "target_role": "employee",
        "anonymous": True,
        "sections": [
            {"id": "p1", "title": "Pillar 1: Environment",
             "fields": [
                 {"id": "q1", "label": "I have what I need to do my job effectively (tools, info, resources).", "type": "likert_5", "required": True},
                 {"id": "q2", "label": "My direct manager supports my growth and gives me feedback that helps.", "type": "likert_5", "required": True},
                 {"id": "q3", "label": "My role uses my strengths most of the time.", "type": "likert_5", "required": True},
                 {"id": "q4", "label": "I would recommend Solvit as a great place to work.", "type": "likert_5", "required": True},
             ]},
            {"id": "p2", "title": "Pillar 2: Values",
             "fields": [
                 {"id": "q5", "label": "Solvit's values (Integrity, Hard Work, Teamwork, Solution Orientation, Timeliness) are lived by leadership.", "type": "likert_5", "required": True},
                 {"id": "q6", "label": "I see colleagues holding each other to high standards.", "type": "likert_5", "required": True},
                 {"id": "q7", "label": "Concerns and grievances are taken seriously when raised.", "type": "likert_5", "required": True},
                 {"id": "q8", "label": "Decisions at Solvit are made fairly and transparently.", "type": "likert_5", "required": True},
             ]},
            {"id": "p3", "title": "Pillar 3: Rewards",
             "fields": [
                 {"id": "q9", "label": "My total compensation feels fair for the work I do.", "type": "likert_5", "required": True},
                 {"id": "q10", "label": "I understand exactly how my performance is measured and rewarded.", "type": "likert_5", "required": True},
                 {"id": "q11", "label": "Top performers at Solvit are recognized appropriately.", "type": "likert_5", "required": True},
                 {"id": "q12", "label": "I see a real career growth path for me at Solvit over the next 2 years.", "type": "likert_5", "required": True},
             ]},
            {"id": "comments", "title": "Open Feedback (Optional)",
             "fields": [
                 {"id": "what_works", "label": "What's working well at Solvit?", "type": "textarea", "required": False},
                 {"id": "what_change", "label": "If you could change one thing about Solvit, what would it be?", "type": "textarea", "required": False},
             ]},
        ]
    },
    "form-07": {
        "id": "form-07",
        "title": "Employee Self-Review",
        "description": "Self-assessment form — completed before manager review",
        "target_role": "employee",
        "requires_signatures": ["employee"],
        "sections": [
            {"id": "achievements", "title": "Achievements", "fields": [
                {"id": "top_3_achievements", "label": "Your top 3 achievements this cycle", "type": "textarea", "required": True},
                {"id": "kpi_self_score_a", "label": "Self-rate Section A KPIs (1=Exceeded, 2=Met, 3=Below)", "type": "number", "required": True, "min": 1, "max": 3},
                {"id": "evidence", "label": "Evidence supporting your KPI rating", "type": "textarea", "required": True},
            ]},
            {"id": "growth", "title": "Growth & Development", "fields": [
                {"id": "biggest_learning", "label": "Biggest learning this cycle", "type": "textarea", "required": True},
                {"id": "areas_to_develop", "label": "What do you want to develop next cycle?", "type": "textarea", "required": True},
                {"id": "support_needed", "label": "What support do you need from your manager?", "type": "textarea", "required": False},
            ]},
            {"id": "career", "title": "Career", "fields": [
                {"id": "career_aspiration", "label": "Where do you see yourself in 12-24 months?", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-08": {
        "id": "form-08",
        "title": "Probationary Review Form",
        "description": "Monthly probation check-in — completed by line manager during 3-month probation",
        "target_role": "line_manager",
        "requires_signatures": ["line_manager", "employee"],
        "sections": [
            {"id": "header", "title": "Probation Review", "fields": [
                {"id": "employee_name", "label": "Employee Name", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "review_month", "label": "Probation Month", "type": "dropdown", "required": True, "options": ["Month 1", "Month 2", "Month 3 (Final)"]},
            ]},
            {"id": "performance", "title": "Performance vs Role Expectations", "fields": [
                {"id": "delivery_rating", "label": "Delivery against role expectations", "type": "radio", "required": True, "options": ["Exceeds", "Meets", "Approaching", "Below"]},
                {"id": "values_rating", "label": "Values alignment", "type": "radio", "required": True, "options": ["Strong", "Adequate", "Concerns"]},
                {"id": "specific_examples", "label": "Specific examples", "type": "textarea", "required": True},
                {"id": "areas_for_improvement", "label": "Areas for improvement", "type": "textarea", "required": False},
            ]},
            {"id": "decision", "title": "Recommendation", "fields": [
                {"id": "recommendation", "label": "Manager Recommendation", "type": "radio", "required": True,
                 "options": ["Confirm — passed probation", "Extend probation by 1 month", "Terminate during probation"]},
                {"id": "rationale", "label": "Rationale", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-09": {
        "id": "form-09",
        "title": "Performance Improvement Plan (PIP)",
        "description": "8-week structured performance improvement plan",
        "target_role": "line_manager",
        "requires_signatures": ["line_manager", "employee", "hr_admin"],
        "sections": [
            {"id": "issues", "title": "Performance Concerns", "fields": [
                {"id": "performance_gaps", "label": "Specific performance gaps", "type": "textarea", "required": True},
                {"id": "evidence", "label": "Evidence and examples", "type": "textarea", "required": True},
                {"id": "previous_feedback", "label": "Previous feedback given (dates and content)", "type": "textarea", "required": True},
            ]},
            {"id": "objectives", "title": "PIP Objectives (8 weeks)", "fields": [
                {"id": "objective_1", "label": "Objective 1 (SMART)", "type": "textarea", "required": True},
                {"id": "metric_1", "label": "Success metric 1", "type": "text", "required": True},
                {"id": "objective_2", "label": "Objective 2 (SMART)", "type": "textarea", "required": True},
                {"id": "metric_2", "label": "Success metric 2", "type": "text", "required": True},
                {"id": "objective_3", "label": "Objective 3 (SMART)", "type": "textarea", "required": False},
                {"id": "metric_3", "label": "Success metric 3", "type": "text", "required": False},
            ]},
            {"id": "support", "title": "Support & Check-ins", "fields": [
                {"id": "support_provided", "label": "Support being provided (training, mentoring, tools)", "type": "textarea", "required": True},
                {"id": "review_schedule", "label": "Review check-in schedule", "type": "text", "required": True, "placeholder": "Weekly Mon 10am"},
                {"id": "consequences", "label": "Consequences of non-improvement", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-10": {
        "id": "form-10",
        "title": "Employee Exit Notice (HR Initiated)",
        "description": "HR-initiated exit (redundancy / role change / termination)",
        "target_role": "hr_admin",
        "requires_signatures": ["hr_admin", "employee"],
        "sections": [
            {"id": "details", "title": "Exit Details", "fields": [
                {"id": "exit_type", "label": "Exit Type", "type": "dropdown", "required": True, "options": ["Redundancy", "Restructure", "Termination — performance", "Termination — misconduct", "Mutual separation", "End of contract"]},
                {"id": "last_working_day", "label": "Last Working Day", "type": "date", "required": True},
                {"id": "notice_period_paid", "label": "Notice Period (months)", "type": "number", "required": True, "min": 0, "max": 6},
                {"id": "severance_kes", "label": "Severance Amount (KES)", "type": "number", "required": False},
                {"id": "rationale", "label": "Rationale", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-11": {
        "id": "form-11",
        "title": "Goal-Setting and OKR Form",
        "description": "Annual OKR / KPI goal-setting at start of cycle",
        "target_role": "line_manager",
        "requires_signatures": ["employee", "line_manager"],
        "sections": [
            {"id": "kpis", "title": "KPI Objectives (3 minimum)", "fields": [
                {"id": "kpi_1_objective", "label": "KPI 1 — Objective", "type": "text", "required": True},
                {"id": "kpi_1_metric", "label": "KPI 1 — Measurement", "type": "text", "required": True},
                {"id": "kpi_1_target", "label": "KPI 1 — Target", "type": "text", "required": True},
                {"id": "kpi_2_objective", "label": "KPI 2 — Objective", "type": "text", "required": True},
                {"id": "kpi_2_metric", "label": "KPI 2 — Measurement", "type": "text", "required": True},
                {"id": "kpi_2_target", "label": "KPI 2 — Target", "type": "text", "required": True},
                {"id": "kpi_3_objective", "label": "KPI 3 — Objective", "type": "text", "required": True},
                {"id": "kpi_3_metric", "label": "KPI 3 — Measurement", "type": "text", "required": True},
                {"id": "kpi_3_target", "label": "KPI 3 — Target", "type": "text", "required": True},
            ]},
            {"id": "stretch", "title": "Stretch Goals (optional)", "fields": [
                {"id": "stretch_goal", "label": "Stretch goal that would qualify for 'Exceeded'", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-12": {
        "id": "form-12",
        "title": "Individual Development Plan (IDP)",
        "description": "Annual development plan — career aspirations, skills to build, actions",
        "target_role": "employee",
        "requires_signatures": ["employee", "line_manager"],
        "sections": [
            {"id": "career", "title": "Career Aspirations", "fields": [
                {"id": "current_role", "label": "Current Role", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "next_role_target", "label": "Next role target (12-24 months)", "type": "text", "required": True},
                {"id": "long_term_goal", "label": "Long-term career goal (3-5 years)", "type": "textarea", "required": False},
            ]},
            {"id": "development", "title": "Development Priorities", "fields": [
                {"id": "skill_1", "label": "Skill / capability to develop #1", "type": "text", "required": True},
                {"id": "actions_1", "label": "Actions to develop skill #1", "type": "textarea", "required": True},
                {"id": "skill_2", "label": "Skill / capability to develop #2", "type": "text", "required": False},
                {"id": "actions_2", "label": "Actions to develop skill #2", "type": "textarea", "required": False},
            ]},
            {"id": "support", "title": "Support Needed", "fields": [
                {"id": "training_required", "label": "Training / certification required", "type": "textarea", "required": False},
                {"id": "mentor_request", "label": "Mentor request", "type": "text", "required": False},
                {"id": "stretch_assignments", "label": "Stretch assignments", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-13": {
        "id": "form-13",
        "title": "Training Request",
        "description": "External training / certification request",
        "target_role": "employee",
        "requires_signatures": ["employee", "line_manager"],
        "sections": [
            {"id": "training", "title": "Training Details", "fields": [
                {"id": "training_name", "label": "Training Name", "type": "text", "required": True},
                {"id": "provider", "label": "Provider", "type": "text", "required": True},
                {"id": "delivery_method", "label": "Delivery", "type": "radio", "required": True, "options": ["External", "Internal", "Online", "Mixed"]},
                {"id": "cost_kes", "label": "Cost (KES)", "type": "number", "required": True, "min": 0},
                {"id": "duration_days", "label": "Duration (days)", "type": "number", "required": True, "min": 1},
                {"id": "start_date", "label": "Proposed start date", "type": "date", "required": True},
                {"id": "business_justification", "label": "Business Justification", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-14": {
        "id": "form-14",
        "title": "Skills Matrix Self-Assessment",
        "description": "Self-rate competencies (Beginner / Intermediate / Advanced / Expert)",
        "target_role": "employee",
        "sections": [
            {"id": "core", "title": "Core Competencies", "fields": [
                {"id": "communication", "label": "Communication", "type": "radio", "required": True, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
                {"id": "problem_solving", "label": "Problem Solving", "type": "radio", "required": True, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
                {"id": "ownership", "label": "Ownership", "type": "radio", "required": True, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
                {"id": "time_management", "label": "Time Management", "type": "radio", "required": True, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
            ]},
            {"id": "technical", "title": "Technical Skills (relevant to role)", "fields": [
                {"id": "tech_skill_1", "label": "Primary technical skill", "type": "text", "required": True},
                {"id": "tech_level_1", "label": "Level", "type": "radio", "required": True, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
                {"id": "tech_skill_2", "label": "Secondary technical skill", "type": "text", "required": False},
                {"id": "tech_level_2", "label": "Level", "type": "radio", "required": False, "options": ["Beginner", "Intermediate", "Advanced", "Expert"]},
            ]},
        ]
    },
    "form-16": {
        "id": "form-16",
        "title": "Policy Acknowledgement",
        "description": "Acknowledge that you have read and understood a published policy",
        "target_role": "employee",
        "requires_signatures": ["employee"],
        "sections": [
            {"id": "ack", "title": "Acknowledgement", "fields": [
                {"id": "policy_id", "label": "Policy", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "policy_version", "label": "Version", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "read_confirmation", "label": "I have read and understood this policy", "type": "radio", "required": True, "options": ["Yes"]},
                {"id": "questions", "label": "Any questions on this policy?", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-17": {
        "id": "form-17",
        "title": "Disciplinary Hearing Notice",
        "description": "Notice to attend a disciplinary hearing",
        "target_role": "hr_admin",
        "sections": [
            {"id": "notice", "title": "Hearing Details", "fields": [
                {"id": "case_ref", "label": "Case Reference", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "allegation_summary", "label": "Allegation Summary", "type": "textarea", "required": True},
                {"id": "hearing_date", "label": "Hearing Date", "type": "date", "required": True},
                {"id": "hearing_time", "label": "Hearing Time", "type": "text", "required": True},
                {"id": "hearing_location", "label": "Location / Link", "type": "text", "required": True},
                {"id": "panel_members", "label": "Panel Members", "type": "textarea", "required": True},
                {"id": "rights_advised", "label": "Right to be accompanied advised", "type": "radio", "required": True, "options": ["Yes"]},
            ]},
        ]
    },
    "form-18": {
        "id": "form-18",
        "title": "Disciplinary Outcome Letter",
        "description": "Formal outcome of a disciplinary hearing",
        "target_role": "hr_admin",
        "requires_signatures": ["hr_admin"],
        "sections": [
            {"id": "outcome", "title": "Outcome", "fields": [
                {"id": "case_ref", "label": "Case Reference", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "finding", "label": "Finding", "type": "radio", "required": True, "options": ["Allegation upheld", "Allegation not upheld", "Partially upheld"]},
                {"id": "sanction", "label": "Sanction", "type": "dropdown", "required": True, "options": ["No action", "Verbal warning", "Written warning", "Final written warning", "Demotion", "Dismissal"]},
                {"id": "rationale", "label": "Rationale", "type": "textarea", "required": True},
                {"id": "appeal_rights", "label": "Right of appeal communicated", "type": "radio", "required": True, "options": ["Yes"]},
                {"id": "appeal_deadline_days", "label": "Days to appeal", "type": "number", "required": True, "min": 1, "max": 14},
            ]},
        ]
    },
    "form-19": {
        "id": "form-19",
        "title": "Grievance Form",
        "description": "Formal grievance filed by employee",
        "target_role": "employee",
        "requires_signatures": ["employee"],
        "sections": [
            {"id": "grievance", "title": "Grievance Details", "fields": [
                {"id": "grievance_category", "label": "Category", "type": "dropdown", "required": True, "options": ["Harassment", "Discrimination", "Manager conduct", "Pay/Benefits", "Working conditions", "Other"]},
                {"id": "incident_summary", "label": "Summary of incident(s)", "type": "textarea", "required": True},
                {"id": "incident_dates", "label": "Date(s) of incident(s)", "type": "text", "required": True},
                {"id": "people_involved", "label": "People involved", "type": "textarea", "required": True},
                {"id": "informal_resolution_attempted", "label": "Have you attempted informal resolution?", "type": "radio", "required": True, "options": ["Yes", "No", "Not appropriate"]},
                {"id": "desired_outcome", "label": "Desired outcome", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-20": {
        "id": "form-20",
        "title": "Whistleblower Report",
        "description": "Confidential whistleblower report",
        "target_role": "employee",
        "anonymous": True,
        "sections": [
            {"id": "report", "title": "Confidential Report", "fields": [
                {"id": "report_anonymously", "label": "Submit anonymously?", "type": "radio", "required": True, "options": ["Yes", "No"]},
                {"id": "concern_category", "label": "Concern Category", "type": "dropdown", "required": True, "options": ["Fraud / Bribery", "Theft", "Safety", "Discrimination", "Harassment", "Conflict of interest", "Other"]},
                {"id": "concern_details", "label": "Concern Details", "type": "textarea", "required": True},
                {"id": "evidence_available", "label": "Evidence available?", "type": "radio", "required": True, "options": ["Yes", "No"]},
                {"id": "evidence_description", "label": "Evidence description (if any)", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-22": {
        "id": "form-22",
        "title": "Stay Interview",
        "description": "Conducted with retained employees, especially those at risk",
        "target_role": "hr_admin",
        "sections": [
            {"id": "satisfaction", "title": "Engagement & Satisfaction", "fields": [
                {"id": "what_makes_stay", "label": "What makes you stay at Solvit?", "type": "textarea", "required": True},
                {"id": "what_might_leave", "label": "What might cause you to leave?", "type": "textarea", "required": True},
                {"id": "energising", "label": "What part of your role energises you most?", "type": "textarea", "required": False},
                {"id": "frustrating", "label": "What part frustrates you?", "type": "textarea", "required": False},
            ]},
            {"id": "growth", "title": "Growth", "fields": [
                {"id": "career_path_clear", "label": "Is your career path clear?", "type": "radio", "required": True, "options": ["Very clear", "Somewhat", "Not at all"]},
                {"id": "manager_support_rating", "label": "Manager support (1-5)", "type": "number", "required": True, "min": 1, "max": 5},
                {"id": "growth_actions", "label": "What can Solvit do to support your growth?", "type": "textarea", "required": False},
            ]},
            {"id": "actions", "title": "Action Plan", "fields": [
                {"id": "agreed_actions", "label": "Agreed actions following this conversation", "type": "textarea", "required": True},
                {"id": "follow_up_date", "label": "Follow-up date", "type": "date", "required": True},
            ]},
        ]
    },
    "form-23": {
        "id": "form-23",
        "title": "Exit Clearance Checklist",
        "description": "23-task clearance across IT, Admin, Finance, HR",
        "target_role": "hr_admin",
        "sections": [
            {"id": "it", "title": "IT Clearance",
             "fields": [{"id": f"it_{i}", "label": l, "type": "radio", "required": True, "options": ["Done", "Pending", "N/A"]}
                        for i, l in enumerate(["Laptop returned", "Email account suspended", "VPN access revoked", "Phone returned", "Software licences revoked", "Cloud accounts deactivated"])]},
            {"id": "admin", "title": "Admin Clearance",
             "fields": [{"id": f"admin_{i}", "label": l, "type": "radio", "required": True, "options": ["Done", "Pending", "N/A"]}
                        for i, l in enumerate(["Office key returned", "Access card returned", "Parking pass returned", "Branded items returned", "Desk cleared"])]},
            {"id": "finance", "title": "Finance Clearance",
             "fields": [{"id": f"fin_{i}", "label": l, "type": "radio", "required": True, "options": ["Done", "Pending", "N/A"]}
                        for i, l in enumerate(["Final salary calculated", "Loans / advances reconciled", "Per diem reconciled", "Expense claims settled", "P9A issued"])]},
            {"id": "hr", "title": "HR Clearance",
             "fields": [{"id": f"hr_{i}", "label": l, "type": "radio", "required": True, "options": ["Done", "Pending", "N/A"]}
                        for i, l in enumerate(["Exit interview completed", "Reference letter issued", "NSSF/SHA/PAYE confirmation", "Confidentiality reminder signed", "Personal file archived", "NDA signed", "Final pay slip issued"])]},
        ]
    },
    "form-24": {
        "id": "form-24",
        "title": "Post-Employment Confidentiality & Non-Solicitation",
        "description": "Reaffirms confidentiality and non-solicitation obligations",
        "target_role": "employee",
        "requires_signatures": ["employee"],
        "sections": [
            {"id": "ack", "title": "Acknowledgements", "fields": [
                {"id": "confidentiality_acknowledged", "label": "I will not disclose confidential information of Solvit, its clients, or its Solvers", "type": "radio", "required": True, "options": ["I agree"]},
                {"id": "ip_acknowledged", "label": "All IP created during employment remains property of Solvit", "type": "radio", "required": True, "options": ["I agree"]},
                {"id": "non_solicit_period", "label": "I will not solicit Solvit clients or Solvers for 12 months", "type": "radio", "required": True, "options": ["I agree"]},
                {"id": "comments", "label": "Comments", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-25": {
        "id": "form-25",
        "title": "Reference Letter Request",
        "description": "Request a reference letter (employment, character)",
        "target_role": "employee",
        "sections": [
            {"id": "request", "title": "Reference Request", "fields": [
                {"id": "letter_type", "label": "Letter Type", "type": "radio", "required": True, "options": ["Employment Reference", "Character Reference", "Bank/Loan Reference", "Visa Letter"]},
                {"id": "addressed_to", "label": "Addressed To", "type": "text", "required": True},
                {"id": "purpose", "label": "Purpose", "type": "text", "required": True},
                {"id": "deadline", "label": "Required by", "type": "date", "required": True},
            ]},
        ]
    },
    "form-26": {
        "id": "form-26",
        "title": "360 Peer Review",
        "description": "Anonymous peer review feeding Section B of FTE Performance Review",
        "target_role": "employee",
        "anonymous": True,
        "sections": [
            {"id": "values", "title": "Rate the colleague on Solvit values (1-5)", "fields": [
                {"id": "integrity", "label": "Integrity", "type": "likert_5", "required": True},
                {"id": "hard_work", "label": "Hard Work & Ownership", "type": "likert_5", "required": True},
                {"id": "teamwork", "label": "Teamwork & Decency", "type": "likert_5", "required": True},
                {"id": "solution", "label": "Solution Orientation", "type": "likert_5", "required": True},
                {"id": "timeliness", "label": "Timeliness", "type": "likert_5", "required": True},
            ]},
            {"id": "comments", "title": "Open Comments (Anonymous)", "fields": [
                {"id": "strengths", "label": "Strengths", "type": "textarea", "required": False},
                {"id": "growth_area", "label": "Suggested area for growth", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-27": {
        "id": "form-27",
        "title": "Manager Recognition",
        "description": "Manager-initiated recognition for team members",
        "target_role": "line_manager",
        "sections": [
            {"id": "recognition", "title": "Recognition", "fields": [
                {"id": "nominee_name", "label": "Team Member", "type": "text", "required": True},
                {"id": "values_demonstrated", "label": "Values Demonstrated", "type": "multi_checkbox", "required": True,
                 "options": ["Integrity", "Hard Work & Ownership", "Teamwork & Decency", "Solution Orientation", "Timeliness"]},
                {"id": "specific_behaviour", "label": "Specific behaviour observed", "type": "textarea", "required": True},
                {"id": "impact", "label": "Impact (on team / customer / business)", "type": "textarea", "required": True},
                {"id": "reward_recommended", "label": "Reward recommended", "type": "dropdown", "required": False,
                 "options": ["Public shout-out only", "Spot award (KES 5,000)", "Spot award (KES 10,000)", "Quarterly award nomination"]},
            ]},
        ]
    },
    "form-28": {
        "id": "form-28",
        "title": "Long Service Award",
        "description": "Tenure milestone recognition (3, 5, 10 years)",
        "target_role": "hr_admin",
        "sections": [
            {"id": "award", "title": "Long Service Award", "fields": [
                {"id": "employee_name", "label": "Employee", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "years_of_service", "label": "Years of Service", "type": "dropdown", "required": True, "options": ["3 years", "5 years", "10 years", "15 years"]},
                {"id": "milestone_date", "label": "Milestone Date", "type": "date", "required": True},
                {"id": "award_value_kes", "label": "Award Value (KES)", "type": "number", "required": True, "min": 0},
                {"id": "award_form", "label": "Form of Award", "type": "dropdown", "required": True, "options": ["Cash bonus", "Voucher", "Extra leave days", "Custom plaque", "Combination"]},
            ]},
        ]
    },
    "form-29": {
        "id": "form-29",
        "title": "Solver Suspension Notice",
        "description": "Issued when a Solver is temporarily suspended pending investigation",
        "target_role": "hr_admin",
        "sections": [
            {"id": "suspension", "title": "Suspension Details", "fields": [
                {"id": "solver_name", "label": "Solver Name", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "reason", "label": "Reason for Suspension", "type": "dropdown", "required": True, "options": ["Quality issue", "Client complaint", "Integrity concern", "Failed assessment", "No-show pattern", "Other"]},
                {"id": "incident_summary", "label": "Incident Summary", "type": "textarea", "required": True},
                {"id": "suspension_start", "label": "Suspension Start", "type": "date", "required": True},
                {"id": "expected_review_date", "label": "Expected Review Date", "type": "date", "required": True},
                {"id": "during_suspension", "label": "Restrictions during suspension", "type": "textarea", "required": True},
            ]},
        ]
    },
    "form-30": {
        "id": "form-30",
        "title": "Solver Performance Score Review",
        "description": "Quarterly Solver performance review (5-state lifecycle)",
        "target_role": "hr_manager",
        "sections": [
            {"id": "metrics", "title": "Quarterly Metrics", "fields": [
                {"id": "solver_name", "label": "Solver", "type": "text", "readonly": True, "auto_populated": True},
                {"id": "inspections_completed", "label": "Inspections Completed (Q)", "type": "number", "required": True, "min": 0},
                {"id": "client_csat", "label": "Avg Client CSAT (1-5)", "type": "number", "required": True, "min": 1, "max": 5},
                {"id": "no_show_count", "label": "No-shows / late arrivals", "type": "number", "required": True, "min": 0},
                {"id": "quality_audit_score", "label": "Quality Audit Score (%)", "type": "number", "required": True, "min": 0, "max": 100},
                {"id": "values_complaints", "label": "Values complaints raised", "type": "number", "required": True, "min": 0},
            ]},
            {"id": "tier", "title": "Tier Assignment", "fields": [
                {"id": "performance_tier", "label": "Performance Tier", "type": "radio", "required": True, "options": ["Elite", "High Performer", "Standard", "Watchlist"]},
                {"id": "lifecycle_action", "label": "Lifecycle Action", "type": "radio", "required": True, "options": ["Maintain Active", "Move to Watchlist", "Suspend pending review", "Deactivate"]},
                {"id": "comments", "label": "Comments", "type": "textarea", "required": False},
            ]},
        ]
    },
    "form-32": {
        "id": "form-32",
        "title": "Solver Quarterly Award Nomination",
        "description": "Nominate a Solver for the quarterly Bronze / Silver / Gold awards",
        "target_role": "line_manager",
        "sections": [
            {"id": "nomination", "title": "Nomination", "fields": [
                {"id": "solver_name", "label": "Solver Name", "type": "text", "required": True},
                {"id": "award_tier", "label": "Award Tier", "type": "radio", "required": True, "options": ["Bronze (KES 5,000)", "Silver (KES 10,000)", "Gold (KES 25,000)"]},
                {"id": "quarter", "label": "Quarter", "type": "dropdown", "required": True, "options": ["Q1", "Q2", "Q3", "Q4"]},
                {"id": "rationale", "label": "Rationale (specific behaviours)", "type": "textarea", "required": True},
                {"id": "client_quotes", "label": "Client / colleague quotes (optional)", "type": "textarea", "required": False},
                {"id": "metrics_supporting", "label": "Metrics supporting nomination", "type": "textarea", "required": True},
            ]},
        ]
    },
}
