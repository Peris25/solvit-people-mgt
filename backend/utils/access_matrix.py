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
        "finance":      _level("Manage", "own_record"),
        "employee":     _level("Manage", "own_record"),
        "solver":       _level("Manage", "own_record"),
        "executive":    None,
    },
    "M05": {  # Performance Review Tracker
        "hr_admin":     _level("Full"),
        "hr_manager":   _level("Full"),
        "line_manager": _level("Manage", "own_team"),
        "finance":      None,
        "employee":     _level("Manage", "own_record"),  # Own goals/self-assessment only; stage guards enforce this.
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
        "finance":      _level("Read",   "own_record"),
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
        # Additive layer rule: Finance is a Finance & Operations Manager. They get
        # Manage with own_team (approve direct reports' leave) — and as employees
        # themselves they can always apply leave for their own record.
        "finance":      _level("Manage", "own_team"),
        "employee":     _level("Manage", "own_record"),
        "solver":       None,
        "executive":    _level("Manage", "own_team"),  # Actual direct-report leave only; checked dual approval.
        "board":        _level("Manage", "own_team"),  # Only stored direct reports (e.g. a Board Chair's MD).
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
    """Return access entry for (module, role) or None if no access.

    Resolution order:
      1) Runtime override in RUNTIME_OVERRIDES[(module, role)] (set by IT Admin
         via PUT /api/access/matrix/cell — see routes/access.py).
      2) Custom-role default from CUSTOM_ROLE_DEFINITIONS (created by IT Admin
         via POST /api/access/roles — inherits from `inherits_from` role for
         any module not explicitly overridden).
      3) Static ACCESS_MATRIX (the seed defaults).
    """
    key = (module_id, role)
    if key in RUNTIME_OVERRIDES:
        return RUNTIME_OVERRIDES[key] or None
    if role in CUSTOM_ROLE_DEFINITIONS:
        cdef = CUSTOM_ROLE_DEFINITIONS[role]
        # Custom roles inherit a base role's matrix wholesale; explicit
        # per-cell overrides are stored in RUNTIME_OVERRIDES.
        inherit = cdef.get("inherits_from") or "employee"
        return get_module_access(module_id, inherit)
    return ACCESS_MATRIX.get(module_id, {}).get(role)


# ============================================================================
# Runtime override store — populated from MongoDB on startup. Mutated by the
# /access/matrix/cell endpoint and read by gatekeepers through a request snapshot.
# ============================================================================
# Maps (module_id, role) → {"level": "Full|Manage|Read", "scope": str|None}
# A value of None means an explicit "remove access" override.
# A stable proxy preserves imports in existing helpers while HTTP requests use
# isolated snapshots. Outside requests, scripts/tests retain the explicit store.
from collections.abc import MutableMapping
from contextvars import ContextVar
from contextlib import asynccontextmanager
from fastapi import HTTPException

_permission_state = ContextVar("permission_state", default=None)


class PermissionStore(MutableMapping):
    def __init__(self, name):
        self.name = name
        self.fallback = {}

    def current(self):
        state = _permission_state.get()
        return state[self.name] if state is not None else self.fallback

    def __getitem__(self, key): return self.current()[key]
    def __setitem__(self, key, value): self.current()[key] = value
    def __delitem__(self, key): del self.current()[key]
    def __iter__(self): return iter(self.current())
    def __len__(self): return len(self.current())
    def copy(self): return self.current().copy()


RUNTIME_OVERRIDES = PermissionStore("overrides")
CUSTOM_ROLE_DEFINITIONS = PermissionStore("roles")


async def read_runtime_state(db):
    """Read primary MongoDB on every request; never reuse a worker cache.

    Build off to the side, then publish only a complete request-local snapshot.
    No TTL window, global clear/refill, new index or historical rewrite.
    """
    overrides, roles = {}, {}
    try:
        async for doc in db.permission_overrides.find({"tenant_id": "solvit"}):
            key = (doc.get("module_id"), doc.get("role"))
            if not all(isinstance(value, str) and value for value in key) or key in overrides:
                raise ValueError("Ambiguous permission configuration")
            if not doc.get("removed") and doc.get("level") not in {"Read", "Manage", "Full"}:
                raise ValueError("Invalid permission level")
            if doc.get("scope") is not None and not isinstance(doc["scope"], str):
                raise ValueError("Invalid permission scope")
            entry = None if doc.get("removed") else {"level": doc["level"]}
            if entry is not None and doc.get("scope"): entry["scope"] = doc["scope"]
            overrides[key] = entry
        async for doc in db.custom_roles.find({"tenant_id": "solvit"}):
            key, parent = doc.get("key"), doc.get("inherits_from", "employee")
            if not isinstance(key, str) or not key or key in roles or parent not in {*ROLES, "it_admin", "board"}:
                raise ValueError("Invalid custom role configuration")
            roles[key] = {"label": doc.get("label", key), "description": doc.get("description", ""), "inherits_from": parent}
    except Exception as error:
        raise HTTPException(503, "Permission configuration is unavailable; access was not granted") from error
    return {"overrides": overrides, "roles": roles}


@asynccontextmanager
async def request_permissions(db):
    token = _permission_state.set(await read_runtime_state(db))
    try:
        yield
    finally:
        _permission_state.reset(token)


def apply_override(module_id: str, role: str, entry: dict | None) -> None:
    """Set an explicit override; None denies. Reset deletes the key separately."""
    if entry is None:
        RUNTIME_OVERRIDES[(module_id, role)] = None
    else:
        # Normalize: only persist level + scope keys, drop anything else.
        norm = {"level": entry.get("level")}
        if entry.get("scope"):
            norm["scope"] = entry["scope"]
        RUNTIME_OVERRIDES[(module_id, role)] = norm


def add_custom_role(key: str, label: str, description: str = "", inherits_from: str = "employee") -> None:
    CUSTOM_ROLE_DEFINITIONS[key] = {
        "label": label,
        "description": description,
        "inherits_from": inherits_from,
    }


def remove_custom_role(key: str) -> None:
    CUSTOM_ROLE_DEFINITIONS.pop(key, None)
    # Clean up any orphan overrides for this role
    for mod, role in list(RUNTIME_OVERRIDES.keys()):
        if role == key:
            RUNTIME_OVERRIDES.pop((mod, role), None)


async def load_runtime_state(db) -> None:
    """Explicit non-request initialization; request guards never trust this copy."""
    state = await read_runtime_state(db)
    RUNTIME_OVERRIDES.clear()
    RUNTIME_OVERRIDES.update(state["overrides"])
    CUSTOM_ROLE_DEFINITIONS.clear()
    CUSTOM_ROLE_DEFINITIONS.update(state["roles"])


def effective_matrix() -> dict:
    """Build the effective module × role matrix including overrides and custom
    role columns. Returned to the frontend by GET /api/access/matrix.
    """
    base_roles = list(ROLES)
    all_roles = base_roles + list(CUSTOM_ROLE_DEFINITIONS.keys())
    out: dict[str, dict] = {}
    for mod in ACCESS_MATRIX.keys():
        row = {}
        for r in all_roles:
            row[r] = get_module_access(mod, r)
        out[mod] = row
    return out


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
