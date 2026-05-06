"""Access Matrix endpoints — exposes Section A & B for the frontend to consume."""
from fastapi import APIRouter, Request
from utils.auth import get_current_user
from utils.access_matrix import (
    ACCESS_MATRIX, DESTRUCTIVE_ACTIONS,
    get_module_access, enforce_module, enforce_destructive
)

router = APIRouter(prefix="/access", tags=["access"])


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
    }


@router.get("/check/{module_id}")
async def check_module_access(module_id: str, request: Request):
    """Return the caller's access entry for a single module (or null)."""
    user = await get_current_user(request)
    return {"module": module_id, "role": user.get("role"), "access": get_module_access(module_id, user.get("role"))}
