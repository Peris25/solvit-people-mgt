"""Email triggers — single entry point for "fire the template that matches an
action". Routes call `trigger(db, template_key, employee_id, extra={})` and
this helper resolves the employee, builds a standard merge context, and sends
via the shared email_service (which throttles + logs + retries).

Standard merge tags populated automatically:
  employee_name, employee_first_name, employee_email, employee_role,
  employee_department, line_manager_name, line_manager_email, hr_name,
  company_name, action_date, due_date (placeholder), platform_link,
  current_year, today, login_url
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import os

logger = logging.getLogger(__name__)


async def _resolve_employee(db, employee_id: str) -> dict:
    if not employee_id:
        return {}
    return await db.employees.find_one({"tenant_id": "solvit", "id": employee_id}) or {}


async def _resolve_manager(db, employee: dict) -> dict:
    lm_id = (employee or {}).get("line_manager_id")
    if not lm_id:
        return {}
    return await db.employees.find_one({"tenant_id": "solvit", "id": lm_id}) or {}


async def _resolve_hr_name(db) -> str:
    hr = await db.users.find_one({"tenant_id": "solvit", "role": "hr_admin"})
    return (hr or {}).get("full_name", "Solvit HR & Admin")


def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0] if full_name else ""


async def trigger(
    db,
    template_key: str,
    employee_id: Optional[str] = None,
    extra: Optional[dict] = None,
    to_override: Optional[str] = None,
    cc_roles: Optional[list] = None,
) -> dict:
    """Fire the email template for a specific action.

    Args:
      db: Motor database handle
      template_key: matches email_templates.key (e.g. "onboarding.welcome")
      employee_id: target employee (used to resolve work_email, full_name, etc.)
      extra: additional merge tags (overrides any auto-resolved values)
      to_override: explicit recipient (used when employee_id is the *subject*
        but the email goes to someone else, e.g. recruitment candidate, IT
        Admin alert about an employee).
      cc_roles: optional list of roles to also notify (each gets a copy with
        the same template + context). E.g. ["hr_admin", "it_admin"].
    """
    extra = extra or {}
    emp = await _resolve_employee(db, employee_id) if employee_id else {}
    mgr = await _resolve_manager(db, emp) if emp else {}
    hr_name = await _resolve_hr_name(db)
    to = to_override or emp.get("work_email")

    public_url = os.environ.get("FRONTEND_URL", "https://solvit.co.ke")
    now = datetime.now(timezone.utc)

    context = {
        # employee
        "employee_name": emp.get("full_name", ""),
        "employee_first_name": _first_name(emp.get("full_name", "")),
        "employee_email": emp.get("work_email", ""),
        "employee_role": emp.get("role_title", ""),
        "employee_department": emp.get("department", ""),
        # back-compat aliases used by some existing templates
        "role_title": emp.get("role_title", ""),
        "department": emp.get("department", ""),
        "start_date": emp.get("start_date", ""),
        # manager
        "line_manager_name": mgr.get("full_name", ""),
        "line_manager_email": mgr.get("work_email", ""),
        "manager_name": mgr.get("full_name", ""),       # back-compat
        "manager_email": mgr.get("work_email", ""),     # back-compat
        # hr / company
        "hr_name": hr_name,
        "company_name": "Solvit Limited",
        # platform / time
        "platform_link": public_url,
        "login_url": public_url + "/login",             # back-compat
        "action_date": now.strftime("%d %B %Y"),
        "due_date": extra.get("due_date", ""),
        "current_year": str(now.year),
        "today": now.strftime("%d/%m/%Y"),
        **extra,
    }

    if not to:
        logger.info("trigger(%s) skipped — no recipient email", template_key)
        # Still record so SKIPPED filter populates
        from utils.email_service import _log_skip
        await _log_skip(db, None, f"no recipient for {template_key}", template_key)
        return {"status": "skipped", "message": "no recipient"}

    try:
        from utils.email_service import send_email
        result = await send_email(db, to=to, template_key=template_key, context=context)
    except Exception as e:
        logger.warning("trigger(%s) failed: %s", template_key, e)
        return {"status": "failed", "error": str(e)}

    # CC roles
    if cc_roles:
        for role in cc_roles:
            users = await db.users.find({"tenant_id": "solvit", "role": role}).to_list(20)
            for u in users:
                if u.get("email") and u["email"] != to:
                    try:
                        from utils.email_service import send_email
                        await send_email(db, to=u["email"], template_key=template_key, context=context)
                    except Exception:
                        pass
    return result


async def fire_and_forget(db, template_key: str, **kwargs) -> None:
    """Convenience wrapper for routes that don't care about the send result."""
    try:
        await trigger(db, template_key, **kwargs)
    except Exception as e:
        logger.warning("fire_and_forget(%s) caught: %s", template_key, e)
