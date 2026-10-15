"""Bind form subjects and signatures to authenticated employees, not role names."""
from fastapi import HTTPException
from utils.employee_integrity import employee_key, find_employee, is_direct_report, tenant_of
from utils.employee_access import authorize_employee, saved_manager
from utils.solver_access import authorize_solver, find_solver


async def form_subject(db, user, body, matrix):
    data = dict(body.get("data") or {})
    solver_reference = body.get("solver_id") or data.get("solver_id")
    if solver_reference:
        if user.get("role") not in ("hr_admin", "hr_manager", "solver"):
            raise HTTPException(403, "No access to this solver's form")
        solver = await authorize_solver(db, user, solver_reference)
        solver_key = str(solver.get("id") or solver["_id"])
        for supplied in (body.get("solver_id"), data.get("solver_id")):
            if supplied:
                chosen = await find_solver(db, supplied, user)
                if chosen["_id"] != solver["_id"]:
                    raise HTTPException(403, "Form contains conflicting solver references")
        body["solver_id"] = solver_key
        if "solver_id" in data:
            data["solver_id"] = solver_key
    reference = body.get("employee_id") or data.get("employee_id") or user.get("employee_id")
    employee = None
    if reference:
        employee = await find_employee(db, reference, tenant_of(user))
        if not employee:
            raise HTTPException(404, "Form employee not found")
        if employee_key(employee) != user.get("employee_id"):
            await authorize_employee(db, user, reference, matrix.get("module") or "M04", write=True)
        # Alias references are accepted; contradictory subjects are not.
        for supplied in (body.get("employee_id"), data.get("employee_id")):
            if supplied:
                chosen = await find_employee(db, supplied, tenant_of(user))
                if not chosen or employee_key(chosen) != employee_key(employee):
                    raise HTTPException(403, "Form contains conflicting employee references")
        if data.get("line_manager_id"):
            data["line_manager_id"] = await saved_manager(db, user, employee, data["line_manager_id"])
        data["employee_id"] = employee_key(employee)
        body["employee_id"] = employee_key(employee)
    body["data"] = data
    return employee


async def authorize_signature(db, user, expected_role, subject_id, started_by=None):
    employee = await find_employee(db, subject_id, tenant_of(user)) if subject_id else None
    if expected_role == "employee":
        if not employee or employee_key(employee) != user.get("employee_id"):
            raise HTTPException(403, "Only the subject employee may sign this step")
        return
    if user.get("role") == "hr_admin":
        return  # Existing HR delegation, never the employee's own signature.
    if expected_role != user.get("role"):
        raise HTTPException(403, "This form step is assigned to a different role")
    if expected_role in ("line_manager", "executive") and employee:
        if not is_direct_report(employee, user):
            raise HTTPException(403, "Only the subject's saved manager may sign this step")
    if not employee and expected_role == "line_manager":
        raise HTTPException(403, "A subject employee is required for manager sign-off")
