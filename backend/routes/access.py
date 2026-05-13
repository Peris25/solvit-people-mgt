"""Access Matrix endpoints — exposes Section A & B for the frontend to consume."""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user, ROLES
from utils.access_matrix import (
    ACCESS_MATRIX, DESTRUCTIVE_ACTIONS,
    get_module_access, enforce_module, enforce_destructive
)
import uuid

router = APIRouter(prefix="/access", tags=["access"])

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
    """Return the entire access matrix + the caller's role-specific row."""
    user = await get_current_user(request)
    role = user.get("role")
    role_view = {m: get_module_access(m, role) for m in ACCESS_MATRIX.keys()}
    return {
        "role": role,
        "matrix": ACCESS_MATRIX,
        "destructive_actions": sorted(DESTRUCTIVE_ACTIONS),
        "my_access": role_view,
        "module_labels": MODULE_LABELS,
        "role_labels": ROLE_LABELS,
        "roles_order": ["hr_admin", "hr_manager", "line_manager", "finance", "employee", "solver", "executive", "board", "it_admin"],
    }


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
    if new_role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {ROLES}")
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
