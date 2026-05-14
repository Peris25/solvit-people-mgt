"""Email triggers — single entry point for "fire the template that matches an
action". Routes call `trigger(db, template_key, employee_id, extra={})` and
this helper resolves the employee, builds a standard merge context, and sends
via the shared email_service (which throttles + logs).

Adding a new trigger = just calling trigger() with the right template key in
the route. The mapping between actions and templates lives at the call sites,
not in a separate registry, so it's easy to find via grep.

Conventions:
  - Best-effort: never raises into the caller. A missing template, employee
    without an email, or SMTP failure are all silently logged.
  - Standard merge tags always available: employee_name, manager_name,
    company_name, today, login_url, employee_email.
  - Pass extra={"reason": "...", "amount_kes": 50000} to enrich the template.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def _resolve_employee(db, employee_id: str) -> dict:
    if not employee_id:
        return {}
    emp = await db.employees.find_one({"tenant_id": "solvit", "id": employee_id})
    if not emp:
        return {}
    return emp


async def _resolve_manager(db, employee: dict) -> dict:
    lm_id = (employee or {}).get("line_manager_id")
    if not lm_id:
        return {}
    return await db.employees.find_one({"tenant_id": "solvit", "id": lm_id}) or {}


async def trigger(
    db,
    template_key: str,
    employee_id: Optional[str] = None,
    extra: Optional[dict] = None,
    to_override: Optional[str] = None,
) -> dict:
    """Fire the email template for a specific action.

    Args:
      db: Motor database handle
      template_key: matches email_templates.key (e.g. "onboarding.welcome")
      employee_id: target employee (used to resolve work_email, full_name, etc.)
      extra: additional merge tags (overrides any auto-resolved values)
      to_override: explicit recipient (used when employee_id is the *subject*
        but the email goes to someone else, e.g. peer recognition where the
        recipient is the manager)

    Returns the send-result dict from email_service (or a skip notice).
    """
    extra = extra or {}
    emp = await _resolve_employee(db, employee_id) if employee_id else {}
    mgr = await _resolve_manager(db, emp) if emp else {}
    to = to_override or emp.get("work_email")
    if not to:
        logger.info("trigger(%s) skipped — no recipient email", template_key)
        return {"status": "skipped", "message": "no recipient"}

    context = {
        "employee_name": emp.get("full_name", ""),
        "employee_email": emp.get("work_email", ""),
        "manager_name": mgr.get("full_name", ""),
        "manager_email": mgr.get("work_email", ""),
        "department": emp.get("department", ""),
        "role_title": emp.get("role_title", ""),
        "start_date": emp.get("start_date", ""),
        "company_name": "Solvit Limited",
        "today": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "login_url": "https://solvit.co.ke/login",
        **extra,
    }

    try:
        from utils.email_service import send_email
        return await send_email(db, to=to, template_key=template_key, context=context)
    except Exception as e:
        logger.warning("trigger(%s) failed: %s", template_key, e)
        return {"status": "failed", "error": str(e)}


async def fire_and_forget(db, template_key: str, **kwargs) -> None:
    """Convenience wrapper for routes that don't care about the send result."""
    try:
        await trigger(db, template_key, **kwargs)
    except Exception as e:  # pragma: no cover — safety net
        logger.warning("fire_and_forget(%s) caught: %s", template_key, e)
