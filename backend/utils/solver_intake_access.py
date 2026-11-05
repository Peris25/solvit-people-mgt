"""Private applicant administration is limited to explicitly authorized roles."""
from fastapi import HTTPException

SOLVER_INTAKE_ROLES = frozenset({'hr_admin', 'it_admin'})


def can_administer_intake(user):
    return user.get('role') in SOLVER_INTAKE_ROLES


def require_intake_admin(user):
    if not can_administer_intake(user):
        raise HTTPException(403, 'Solver applicant administration requires HR Admin or IT Admin')
