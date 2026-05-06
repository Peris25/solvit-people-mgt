"""Access Rule Matrix (Section A) and Destructive Action Restrictions (Section B).
Authoritative source for module access. Enforced at the API layer.

Levels:
- "Full"   : read, write, configure, approve
- "Manage" : read, write, approve (no system configuration)
- "Read"   : view only
- None     : no access

Scope qualifiers (string suffixes):
- ":own_reports"      : Line Manager — only own direct reports
- ":own_record"       : self only
- ":own_team"         : own department / direct reports
- ":own_dept_pipeline": own department recruitment pipeline
- ":aggregate"        : aggregate-only view, no individual records
- ":salary_band"      : salary and band fields only
- ":own_cases"        : own active cases only (no resolved historical)
- ":statutory_only"   : statutory compliance deadlines only
- ":monetary_approve" : approve monetary components only
- ":finance_gated"    : Finance-gated forms only
- ":solver_only"      : Solver-specific resources only
- ":solvers_manager"  : Line Manager who is the Solvers Manager only
- ":contextual"       : forms assigned to caller only
"""
from fastapi import HTTPException

# Role list (must match utils/auth.ROLES + "executive")
ROLES = ("hr_admin", "hr_manager", "line_manager", "finance", "employee", "solver", "executive")


def _level(value: str, scope: str = None) -> dict:
    """Helper to build an access entry."""
    if value is None:
        return None
    return {"level": value, "scope": scope}


# Module access matrix per Section A. hr_manager is treated as a delegate of hr_admin
# (full access where HR Admin has full, manage where HR Admin has manage).
ACCESS_MATRIX = {
    "M01": {  # FTE Employee Database
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_reports"),
        "finance":      _level("Read",   "salary_band"),
        "employee":     _level("Read",   "own_record"),
        "solver":       None,
        "executive":    _level("Read",   "aggregate"),
    },
    "M02": {  # Solver Database
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "solvers_manager"),
        "finance":      None,
        "employee":     None,
        "solver":       _level("Read",   "own_record"),
        "executive":    _level("Read",   "aggregate"),
    },
    "M03": {  # Recruitment Pipeline
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Read",   "own_dept_pipeline"),
        "finance":      None,
        "employee":     None,
        "solver":       None,
        "executive":    _level("Read",   "headcount_summary"),
    },
    "M04": {  # Onboarding Tracker
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Manage", "own_record"),
        "solver":       _level("Manage", "own_record"),
        "executive":    None,
    },
    "M05": {  # Performance Review Tracker
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Read",   "own_record"),
        "solver":       None,
        "executive":    _level("Read",   "aggregate"),
    },
    "M06": {  # Alignment Survey Engine
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": None,
        "finance":      None,
        "employee":     _level("Manage", "respond_only"),
        "solver":       _level("Manage", "respond_only"),
        "executive":    _level("Read",   "aggregate"),
    },
    "M07": {  # Retention and Flight Risk
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": None,
        "finance":      None,
        "employee":     None,
        "solver":       None,
        "executive":    _level("Read",   "aggregate"),
    },
    "M08": {  # Learning and Development
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Manage", "own_record"),
        "solver":       None,
        "executive":    None,
    },
    "M09": {  # Project Ownership Tracker
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Read",   "own_record"),
        "solver":       None,
        "executive":    None,
    },
    "M10": {  # Compensation Module
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": None,
        "finance":      _level("Full",   "no_perf_no_disciplinary"),
        "employee":     None,
        "solver":       None,
        "executive":    _level("Read",   "envelope_only"),
    },
    "M11": {  # Recognition Module
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      _level("Read",   "monetary_approve"),
        "employee":     _level("Manage", "own_peer_nominations"),
        "solver":       _level("Read",   "own_record"),
        "executive":    None,
    },
    "M12": {  # Budget Governance
        "hr_admin":     _level("Read"),
        "hr_manager":   _level("Read"),
        "line_manager": None,
        "finance":      _level("Full"),
        "employee":     None,
        "solver":       None,
        "executive":    _level("Read",   "envelope_only"),
    },
    "M13": {  # Policy Library
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Read"),
        "finance":      _level("Read"),
        "employee":     _level("Read",   "acknowledge_only"),
        "solver":       _level("Read",   "solver_only"),
        "executive":    _level("Read"),
    },
    "M14": {  # Disciplinary Case Module
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Read",   "own_cases"),
        "finance":      None,
        "employee":     _level("Read",   "own_record"),
        "solver":       None,
        "executive":    None,
    },
    "M15": {  # HR Calendar
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Read",   "own_team"),
        "finance":      _level("Read",   "statutory_only"),
        "employee":     None,
        "solver":       None,
        "executive":    None,
    },
    "M16": {  # AI Agent Assistant
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     None,
        "solver":       None,
        "executive":    None,
    },
    "M17": {  # Intelligent Forms Engine
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "contextual"),
        "finance":      _level("Manage", "finance_gated"),
        "employee":     _level("Manage", "contextual"),
        "solver":       _level("Manage", "solver_only"),
        "executive":    None,
    },
    "M18": {  # Leave Management
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Manage", "own_record"),
        "solver":       None,
        "executive":    None,
    },
    "M19": {  # Statutory Compliance Register
        "hr_admin":     _level("Read"),
        "hr_manager":   _level("Read"),
        "line_manager": None,
        "finance":      _level("Full"),
        "employee":     None,
        "solver":       None,
        "executive":    None,
    },
}


# Section B: destructive actions restricted to HR Admin only.
DESTRUCTIVE_ACTIONS = {
    "employee.lifecycle.manual_change",
    "automation.rule.toggle",
    "survey.individual_response.read",
    "disciplinary.outcome.issue",
    "review_cycle.configure",
    "employee.archive_or_delete",
    "policy.publish_or_update",
}


def get_module_access(module_id: str, role: str) -> dict | None:
    """Return access entry for (module, role) or None if no access."""
    return ACCESS_MATRIX.get(module_id, {}).get(role)


def enforce_module(module_id: str, role: str, required_level: str = "Read") -> dict:
    """Raise 403 if role does not meet required level for module.
    Levels rank: Full > Manage > Read.
    """
    entry = get_module_access(module_id, role)
    if entry is None:
        raise HTTPException(status_code=403, detail=f"No access to module {module_id}")
    rank = {"Read": 1, "Manage": 2, "Full": 3}
    if rank.get(entry["level"], 0) < rank.get(required_level, 0):
        raise HTTPException(status_code=403, detail=f"Module {module_id} requires {required_level}, you have {entry['level']}")
    return entry


def enforce_destructive(action: str, role: str) -> None:
    """Section B restriction — only HR Admin may invoke listed destructive actions."""
    if action in DESTRUCTIVE_ACTIONS and role != "hr_admin":
        raise HTTPException(status_code=403, detail=f"Destructive action '{action}' restricted to HR Admin only")
