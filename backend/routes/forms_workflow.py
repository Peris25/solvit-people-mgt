"""Form-Workflow-User Matrix metadata (authoritative, supersedes FRD).
Each form ID maps to: module, workflow_trigger, completing_users_sequence,
required_signatures, outcome_rule. Used by forms.py to enforce workflow rules."""

FORM_WORKFLOW_MATRIX = {
    "form-01": {"module": "M04", "module_name": "Solver Onboarding", "workflow_trigger": "AR-OB-05: Solver registration record created", "completing_users_sequence": ["solver"], "required_signatures": [], "outcome_rule": "stage1.complete"},
    "form-02": {"module": "M03", "module_name": "Solver Recruitment", "workflow_trigger": "Solvers Manager initiates after eligibility screening pass", "completing_users_sequence": ["solver"], "required_signatures": [], "outcome_rule": "vehicle.assessment.complete"},
    "form-03": {"module": "M04", "module_name": "Solver Onboarding", "workflow_trigger": "Solver completes induction video (Stage 2)", "completing_users_sequence": ["solver"], "required_signatures": [], "outcome_rule": "code.quiz.complete"},
    "form-04": {"module": "M06", "module_name": "Alignment Survey Engine", "workflow_trigger": "AR-SV-01: HR Admin activates survey window", "completing_users_sequence": ["employee"], "required_signatures": [], "outcome_rule": "alignment.survey.submitted"},
    "form-05": {"module": "M06", "module_name": "Alignment Survey Engine (Solver)", "workflow_trigger": "AR-SV-01 concurrent with FTE survey", "completing_users_sequence": ["solver"], "required_signatures": [], "outcome_rule": "solver.alignment.submitted"},
    "form-06": {"module": "M05", "module_name": "Performance Review", "workflow_trigger": "AR-PF-03: Review meeting scheduled (Week 2)", "completing_users_sequence": ["employee", "line_manager", "hr_admin"], "required_signatures": ["employee", "line_manager", "hr_admin"], "outcome_rule": "review.completed"},
    "form-07": {"module": "M05", "module_name": "Performance Review", "workflow_trigger": "AR-PF-01: HR Admin activates review cycle", "completing_users_sequence": ["employee"], "required_signatures": [], "outcome_rule": "self_review.submitted"},
    "form-08": {"module": "M04", "module_name": "Probation Management", "workflow_trigger": "AR-PR-01/02/03: 28/56/84 days after probation entry", "completing_users_sequence": ["line_manager", "hr_admin", "employee"], "required_signatures": ["line_manager", "hr_admin", "employee"], "outcome_rule": "probation.review.complete"},
    "form-09": {"module": "M05", "module_name": "PIP Management", "workflow_trigger": "HR decision after Forfeited score (2.5+)", "completing_users_sequence": ["hr_admin", "line_manager", "employee"], "required_signatures": ["hr_admin", "line_manager", "employee"], "outcome_rule": "pip.activated"},
    "form-10": {"module": "M05", "module_name": "Performance Management", "workflow_trigger": "AR-PF-04: Below score (2.0–2.49)", "completing_users_sequence": ["line_manager", "employee"], "required_signatures": ["line_manager", "employee"], "outcome_rule": "realignment.activated"},
    "form-11": {"module": "M05", "module_name": "Performance Management + Onboarding", "workflow_trigger": "Onboarding Week 3 OR start of review cycle", "completing_users_sequence": ["line_manager", "employee"], "required_signatures": ["line_manager", "employee"], "outcome_rule": "goals.set"},
    "form-12": {"module": "M08", "module_name": "Learning & Development", "workflow_trigger": "First review cycle completion", "completing_users_sequence": ["employee", "line_manager"], "required_signatures": ["line_manager", "employee"], "outcome_rule": "idp.signed"},
    "form-13": {"module": "M08", "module_name": "Learning & Development", "workflow_trigger": "Employee identifies training need", "completing_users_sequence": ["employee", "line_manager", "hr_admin"], "required_signatures": ["employee", "line_manager", "hr_admin"], "outcome_rule": "training.approved"},
    "form-14": {"module": "M09", "module_name": "Project Ownership Programme", "workflow_trigger": "AR-RK-07: Exceeded score → 30-day project assignment window", "completing_users_sequence": ["hr_admin", "line_manager", "employee"], "required_signatures": ["hr_admin", "line_manager", "employee"], "outcome_rule": "project.assigned"},
    "form-15": {"module": "M18", "module_name": "Leave Management", "workflow_trigger": "Employee initiates leave request", "completing_users_sequence": ["employee", "line_manager", "hr_admin"], "required_signatures": ["employee", "line_manager", "hr_admin"], "outcome_rule": "leave.approved"},
    "form-16": {"module": "M13", "module_name": "Policy Library", "workflow_trigger": "AR-CP-04/05: New policy or annual re-sign", "completing_users_sequence": ["employee"], "required_signatures": ["employee"], "outcome_rule": "policy.acknowledged"},
    "form-17": {"module": "M14", "module_name": "Disciplinary Process", "workflow_trigger": "HR Admin opens disciplinary case", "completing_users_sequence": ["hr_manager", "employee"], "required_signatures": ["hr_manager", "employee"], "outcome_rule": "show_cause.responded"},
    "form-18": {"module": "M14", "module_name": "Disciplinary Process", "workflow_trigger": "Hearing outcome = warning", "completing_users_sequence": ["hr_admin", "line_manager", "employee"], "required_signatures": ["line_manager", "hr_admin", "employee"], "outcome_rule": "warning.issued"},
    "form-19": {"module": "M14", "module_name": "Disciplinary Process", "workflow_trigger": "HR records suspension (always paid, precautionary)", "completing_users_sequence": ["hr_manager", "executive", "employee"], "required_signatures": ["hr_manager", "executive", "employee"], "outcome_rule": "suspension.activated"},
    "form-20": {"module": "M14", "module_name": "Disciplinary Process", "workflow_trigger": "Hearing date reached", "completing_users_sequence": ["hr_admin", "line_manager"], "required_signatures": ["line_manager", "hr_admin"], "outcome_rule": "hearing.recorded"},
    "form-21": {"module": "M07", "module_name": "Offboarding", "workflow_trigger": "AR-EX-01: resignation/termination triggers exit workflow", "completing_users_sequence": ["hr_admin"], "required_signatures": ["hr_admin"], "outcome_rule": "exit_interview.recorded"},
    "form-22": {"module": "M07", "module_name": "Retention", "workflow_trigger": "AR-RT-05 (Q3) OR flight risk Elevated/High/Critical", "completing_users_sequence": ["hr_admin"], "required_signatures": ["hr_admin"], "outcome_rule": "stay_interview.recorded"},
    "form-23": {"module": "M07", "module_name": "Offboarding (Task T04)", "workflow_trigger": "AR-EX-01: auto-created within 60s of exit", "completing_users_sequence": ["employee", "line_manager", "hr_admin", "finance"], "required_signatures": ["employee", "line_manager", "hr_admin", "finance"], "outcome_rule": "clearance.signed_off"},
    "form-24": {"module": "M07", "module_name": "Offboarding (Task T03)", "workflow_trigger": "AR-EX-01: auto-sent during exit", "completing_users_sequence": ["employee", "hr_admin"], "required_signatures": ["employee", "hr_admin"], "outcome_rule": "confidentiality.signed"},
    "form-25": {"module": "M03", "module_name": "Solver Recruitment", "workflow_trigger": "Eligibility screening pass (Stage 1)", "completing_users_sequence": ["line_manager"], "required_signatures": ["line_manager"], "outcome_rule": "solver.recruitment.complete"},
    "form-26": {"module": "M05", "module_name": "Performance Review (Section B)", "workflow_trigger": "AR-PF-01: review cycle activation", "completing_users_sequence": ["employee"], "required_signatures": [], "outcome_rule": "peer_review.submitted"},
    "form-27": {"module": "M11", "module_name": "Recognition", "workflow_trigger": "Any FTE initiates nomination", "completing_users_sequence": ["employee", "hr_admin"], "required_signatures": ["employee", "hr_admin"], "outcome_rule": "recognition.recorded"},
    "form-28": {"module": "M10+M12", "module_name": "Compensation / Budget Governance", "workflow_trigger": "HR Admin initiates bonus calculation cycle", "completing_users_sequence": ["finance"], "required_signatures": ["finance"], "outcome_rule": "gp_gate.set"},
    "form-29": {"module": "M06", "module_name": "Engagement Survey", "workflow_trigger": "AR-SV-04: Annual Q1 (January)", "completing_users_sequence": ["employee"], "required_signatures": [], "outcome_rule": "engagement.submitted"},
    "form-30": {"module": "M06", "module_name": "Solver Engagement", "workflow_trigger": "AR-SV-05: Quarterly auto-trigger", "completing_users_sequence": ["solver"], "required_signatures": [], "outcome_rule": "solver.pulse.submitted"},
    "form-31": {"module": "M07", "module_name": "Offboarding", "workflow_trigger": "Employee chooses to resign", "completing_users_sequence": ["employee"], "required_signatures": ["employee"], "outcome_rule": "resignation.submitted"},
    "form-32": {"module": "M11", "module_name": "Solver Recognition", "workflow_trigger": "AR-RK-06: Quarterly auto-create", "completing_users_sequence": ["line_manager", "finance"], "required_signatures": ["line_manager", "finance"], "outcome_rule": "solver_award.approved"},
    "form-33": {"module": "M10+M12", "module_name": "Budget Governance — Annual Tier Confirmation", "workflow_trigger": "Finance Manager initiates annual gate confirmation", "completing_users_sequence": ["finance", "hr_admin"], "required_signatures": ["finance", "hr_admin"], "outcome_rule": "form_33_tier_confirmed"},
}


def review_panel_for(employee: dict, db_users: list = None) -> list:
    """Return the ordered panel of role names that should review this employee.
    Per Correction Brief §2 (matrix-authoritative).
    Args:
        employee: employee dict with 'reports_to_md' (bool), 'reports_to_finance_ops' (bool), 'is_md' (bool), 'is_executive_director' (bool)
        db_users: optional list for resolving line_manager
    """
    if employee.get("is_md") or (employee.get("role_title", "") or "").lower() in ("managing director", "ceo"):
        return []  # Board-led, not in platform
    if employee.get("reports_to_md"):
        return ["md", "hr_admin"]
    if employee.get("reports_to_finance_ops"):
        return ["hr_admin", "line_manager:finance_ops"]
    return ["hr_admin", "line_manager"]
