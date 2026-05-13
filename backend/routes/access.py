"""Access Matrix endpoints — exposes Section A & B for the frontend to consume."""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user, ROLES
from utils.access_matrix import (
    ACCESS_MATRIX, DESTRUCTIVE_ACTIONS, CUSTOM_ROLE_DEFINITIONS,
    get_module_access, enforce_module, enforce_destructive,
    apply_override, add_custom_role, remove_custom_role, effective_matrix,
)
import uuid

router = APIRouter(prefix="/access", tags=["access"])

VALID_LEVELS = ("Full", "Manage", "Read")
SYSTEM_ROLES = set(ROLES)  # Anything in utils.auth.ROLES is system, non-deletable

# Human-readable labels for the 19 modules — used by the Roles & Permissions UI.
MODULE_LABELS = {
    "M01": "FTE Employee Database",
    "M02": "Solver Database",
    "M03": "Recruitment Pipeline",
    "M04": "Onboarding Tracker",
    "M05": "Performance Review Tracker",
    "M06": "Alignment Survey Engine",
    "M07": "Retention & Flight Risk",
    "M08": "Learning & Development",
    "M09": "Project Ownership Tracker",
    "M10": "Compensation Module",
    "M11": "Recognition Module",
    "M12": "Budget Governance",
    "M13": "Policy Library",
    "M14": "Disciplinary Case Module",
    "M15": "HR Calendar",
    "M16": "AI Agent Assistant",
    "M17": "Intelligent Forms Engine",
    "M18": "Leave Management",
    "M19": "Statutory Compliance Register",
}

ROLE_LABELS = {
    "hr_admin": "HR Admin",
    "hr_manager": "HR Manager",
    "line_manager": "Line Manager",
    "finance": "Finance & Ops Manager",
    "employee": "Employee",
    "solver": "Solver",
    "executive": "MD / Executive",
    "board": "Board",
    "it_admin": "IT Admin",
}


@router.get("/matrix")
async def get_access_matrix(request: Request):
    """Return the effective access matrix (defaults + runtime overrides +
    custom-role columns) plus the caller's role-specific row.
    """
    user = await get_current_user(request)
    role = user.get("role")
    eff = effective_matrix()
    role_view = {m: get_module_access(m, role) for m in ACCESS_MATRIX.keys()}
    # Merge labels: system + custom
    role_labels = dict(ROLE_LABELS)
    for k, cdef in CUSTOM_ROLE_DEFINITIONS.items():
        role_labels[k] = cdef.get("label", k)
    base_order = ["hr_admin", "hr_manager", "line_manager", "finance", "employee", "solver", "executive", "board", "it_admin"]
    custom_order = list(CUSTOM_ROLE_DEFINITIONS.keys())
    return {
        "role": role,
        "matrix": eff,
        "destructive_actions": sorted(DESTRUCTIVE_ACTIONS),
        "my_access": role_view,
        "module_labels": MODULE_LABELS,
        "role_labels": role_labels,
        "roles_order": base_order + custom_order,
        "system_roles": list(SYSTEM_ROLES),
        "custom_roles": [
            {"key": k, "label": v.get("label", k), "description": v.get("description", ""), "inherits_from": v.get("inherits_from")}
            for k, v in CUSTOM_ROLE_DEFINITIONS.items()
        ],
        "valid_levels": list(VALID_LEVELS),
    }


@router.put("/matrix/cell")
async def update_matrix_cell(request: Request):
    """Override a single (module × role) cell. IT Admin only.

    Body:
      { "module_id": "M18", "role": "finance", "level": "Manage"|"Read"|"Full"|null, "scope": "own_team"|null }

    Pass `level: null` to revoke access for that cell. Setting level == the
    default just persists the override; resetting to the seed default should
    use DELETE /access/matrix/cell.
    """
    actor = await get_current_user(request)
    if actor.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    module_id = body.get("module_id")
    role = body.get("role")
    level = body.get("level")
    scope = body.get("scope") or None
    if module_id not in ACCESS_MATRIX:
        raise HTTPException(status_code=400, detail=f"Unknown module {module_id}")
    if role not in SYSTEM_ROLES and role not in CUSTOM_ROLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown role {role}")
    if level is not None and level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {VALID_LEVELS} or null")

    entry = None if level is None else ({"level": level, "scope": scope} if scope else {"level": level})
    db = get_db()
    doc = {
        "tenant_id": "solvit",
        "module_id": module_id,
        "role": role,
        "level": level,
        "scope": scope,
        "removed": level is None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": actor["id"],
    }
    await db.permission_overrides.update_one(
        {"tenant_id": "solvit", "module_id": module_id, "role": role},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4())}},
        upsert=True,
    )
    apply_override(module_id, role, entry)

    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "access.matrix_cell_updated",
        "entity": "permission_override",
        "entity_id": f"{module_id}:{role}",
        "performed_by": actor["id"],
        "metadata": {"module_id": module_id, "role": role, "level": level, "scope": scope},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "module_id": module_id, "role": role, "effective": get_module_access(module_id, role)}


@router.delete("/matrix/cell")
async def reset_matrix_cell(request: Request):
    """Remove the override for a cell — value reverts to ACCESS_MATRIX default.
    Body: { "module_id": "...", "role": "..." }
    """
    actor = await get_current_user(request)
    if actor.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    module_id = body.get("module_id")
    role = body.get("role")
    db = get_db()
    res = await db.permission_overrides.delete_one({"tenant_id": "solvit", "module_id": module_id, "role": role})
    # Also clear from runtime (apply_override with entry=None clears it).
    from utils.access_matrix import RUNTIME_OVERRIDES
    RUNTIME_OVERRIDES.pop((module_id, role), None)
    return {"ok": True, "deleted": res.deleted_count, "effective": get_module_access(module_id, role)}


@router.post("/roles")
async def create_custom_role(request: Request):
    """Create a new custom role that inherits permissions from a base role.
    IT Admin only.

    Body: { "key": "ops_lead", "label": "Operations Lead", "description": "...", "inherits_from": "line_manager" }
    """
    actor = await get_current_user(request)
    if actor.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    key = (body.get("key") or "").strip().lower().replace(" ", "_")
    label = (body.get("label") or "").strip()
    description = (body.get("description") or "").strip()
    inherits_from = body.get("inherits_from") or "employee"
    if not key or not label:
        raise HTTPException(status_code=400, detail="key and label are required")
    if key in SYSTEM_ROLES:
        raise HTTPException(status_code=400, detail=f"'{key}' is a system role and cannot be redefined")
    if key in CUSTOM_ROLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Custom role '{key}' already exists")
    if inherits_from not in SYSTEM_ROLES:
        raise HTTPException(status_code=400, detail=f"inherits_from must be a system role (got {inherits_from})")

    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "key": key,
        "label": label,
        "description": description,
        "inherits_from": inherits_from,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": actor["id"],
    }
    await db.custom_roles.insert_one(doc)
    add_custom_role(key, label, description, inherits_from)
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "access.custom_role_created",
        "entity": "custom_role",
        "entity_id": key,
        "performed_by": actor["id"],
        "metadata": {"label": label, "inherits_from": inherits_from},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    doc.pop("_id", None)
    return doc


@router.delete("/roles/{key}")
async def delete_custom_role(key: str, request: Request):
    """Delete a custom role. System roles are protected. Any users currently
    assigned this role are rebased to `employee` to keep auth functional.
    """
    actor = await get_current_user(request)
    if actor.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    if key in SYSTEM_ROLES:
        raise HTTPException(status_code=400, detail=f"'{key}' is a system role and cannot be deleted")
    if key not in CUSTOM_ROLE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Custom role not found")
    db = get_db()
    # Rebase users on this role to 'employee'
    rebased = await db.users.update_many(
        {"tenant_id": "solvit", "role": key},
        {"$set": {"role": "employee", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.custom_roles.delete_one({"tenant_id": "solvit", "key": key})
    await db.permission_overrides.delete_many({"tenant_id": "solvit", "role": key})
    remove_custom_role(key)
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "access.custom_role_deleted",
        "entity": "custom_role",
        "entity_id": key,
        "performed_by": actor["id"],
        "metadata": {"rebased_users": rebased.modified_count},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "deleted": key, "rebased_users": rebased.modified_count}


@router.get("/check/{module_id}")
async def check_module_access(module_id: str, request: Request):
    """Return the caller's access entry for a single module (or null)."""
    user = await get_current_user(request)
    return {"module": module_id, "role": user.get("role"), "access": get_module_access(module_id, user.get("role"))}


# ---- Roles & Permissions admin — IT Admin only ----

@router.get("/users")
async def list_users_with_roles(request: Request):
    """List all platform users with their primary role. IT Admin only."""
    user = await get_current_user(request)
    if user.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    db = get_db()
    rows = await db.users.find({"tenant_id": "solvit"}).sort("full_name", 1).to_list(500)
    out = []
    for u in rows:
        out.append({
            "id": str(u.get("_id")),
            "email": u.get("email"),
            "full_name": u.get("full_name"),
            "department": u.get("department"),
            "role": u.get("role"),
            "is_active": u.get("is_active", True),
            "created_at": u.get("created_at"),
        })
    return out


@router.put("/users/{user_id}/role")
async def update_user_role(user_id: str, request: Request):
    """Change a user's primary role. IT Admin only.

    Body: { "role": "<one of ROLES>" }
    Audit trail recorded with old + new role.
    """
    actor = await get_current_user(request)
    if actor.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    new_role = body.get("role")
    allowed_roles = set(ROLES) | set(CUSTOM_ROLE_DEFINITIONS.keys())
    if new_role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {sorted(allowed_roles)}")
    db = get_db()
    try:
        target = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    old_role = target.get("role")
    if old_role == new_role:
        return {"id": user_id, "role": new_role, "unchanged": True}

    await db.users.update_one(
        {"_id": target["_id"]},
        {"$set": {"role": new_role, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "user.role_changed",
        "entity": "user",
        "entity_id": str(target["_id"]),
        "performed_by": actor["id"],
        "metadata": {"old_role": old_role, "new_role": new_role, "target_email": target.get("email")},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"id": str(target["_id"]), "email": target.get("email"), "role": new_role, "previous_role": old_role}


@router.get("/roles")
async def list_roles(request: Request):
    """Return the canonical role list with labels. Available to all authenticated users."""
    await get_current_user(request)
    return {
        "roles": [{"key": r, "label": ROLE_LABELS.get(r, r)} for r in ROLES],
    }
