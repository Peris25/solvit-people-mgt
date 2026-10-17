from fastapi import HTTPException
from utils.employee_access import authorize_employee
from utils.employee_integrity import find_employee, user_employee_aliases, tenant_of
from utils.solver_access import authorize_solver


async def authorize_task(db, user, task, write=False):
    if task.get("task_type") == "exit_workflow":
        from utils.lifecycle_workflows import task_access
        await task_access(db, user, task, write=write)
        return
    if user.get("role") in ("hr_admin", "hr_manager"):
        return
    solver_reference = task.get("solver_id") or (task.get("entity_id") if task.get("entity_type") == "solver" else None)
    if solver_reference and user.get("role") in ("solver", "line_manager"):
        await authorize_solver(db, user, solver_reference)
    subject = task.get("employee_id") or (task.get("entity_id") if task.get("entity_type") in (None, "employee") else None)
    employee = await find_employee(db, subject, tenant_of(user)) if subject else None
    if subject and not employee:
        raise HTTPException(409, "Task employee needs an integrity review")
    if employee:
        await authorize_employee(db, user, subject, "M18" if user.get("role") == "finance" else "M04", write=write)
    assigned = task.get("assigned_to")
    if assigned:
        if assigned not in [user["id"]] + user_employee_aliases(user):
            raise HTTPException(403, "Task is assigned to another account")
    elif task.get("assigned_role") != user.get("role"):
        raise HTTPException(403, "Task is assigned to another role")
    elif not employee and user.get("role") in ("employee", "line_manager"):
        raise HTTPException(403, "Task subject needs an integrity review")


async def authorize_notification(db, user, notification):
    recipient = notification.get("recipient_id") or notification.get("user_id")
    if recipient:
        if recipient not in [user["id"]] + user_employee_aliases(user):
            raise HTTPException(403, "Notification belongs to another account")
    elif notification.get("recipient_role") != user.get("role"):
        raise HTTPException(403, "Notification belongs to another role")
    subject = (notification.get("data") or {}).get("employee_id")
    solver_reference = (notification.get("data") or {}).get("solver_id")
    if solver_reference and user.get("role") == "solver":
        await authorize_solver(db, user, solver_reference)
    if subject:
        await authorize_employee(db, user, subject, "M04")
