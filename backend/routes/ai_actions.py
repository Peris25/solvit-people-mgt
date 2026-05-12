"""Actionable AI — HR Assistant action catalog.

Each action has 3 phases:
  1. PROPOSE  — server parses HR's natural-language ask, resolves the entity
                from the live DB, and emits a `proposed_action` payload that
                the frontend renders as a confirmation card.
  2. CONFIRM  — HR clicks Confirm in the UI → server EXECUTES the action and
                writes an audit row to `ai_actions_audit`.
  3. CANCEL   — HR clicks Cancel → server marks the pending action `cancelled`.

Read-only "lookup" capabilities continue to flow through the standard
`/api/ai-agent/chat` and `/api/ai-agent/snapshot` endpoints.
"""
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from bson.errors import InvalidId
from typing import Dict, Any, Optional, List, Tuple
import re
import uuid


# ---- Risk levels drive the confirmation banner colour on the UI ----
RISK_LOW = "low"        # green confirm
RISK_MEDIUM = "medium"  # amber confirm
RISK_HIGH = "high"      # red confirm + must type CONFIRM (future)


# ---- Helper: resolve an employee by free-text query (first/last/full) ----
async def _resolve_employee(db, query: str):
    """Returns dict | None. Picks the highest-confidence employee match."""
    tokens = [t for t in re.findall(r"[A-Za-z][a-z']+", query) if t.lower() not in
              ("approve", "reject", "leave", "for", "the", "of", "to", "send",
               "recognition", "kudos", "mark", "task", "done", "complete",
               "assign", "training", "email", "policy", "from", "with", "please")]
    if not tokens:
        return None
    # Use the longest 2-3 capitalised tokens as the candidate name
    name = " ".join(tokens[:3])
    # Exact (case-insensitive) match first
    rx = "^" + re.escape(name) + "$"
    emp = await db.employees.find_one({"tenant_id": "solvit", "full_name": {"$regex": rx, "$options": "i"}})
    if emp:
        return emp
    # Then partial match
    rx2 = "|".join(re.escape(t) for t in tokens[:3])
    return await db.employees.find_one({"tenant_id": "solvit", "full_name": {"$regex": rx2, "$options": "i"}})


async def _find_leave(db, employee_id: str, status_in=("Pending_Manager", "Pending_HR")):
    return await db.leave_requests.find_one(
        {"tenant_id": "solvit", "employee_id": employee_id, "status": {"$in": list(status_in)}},
        sort=[("created_at", -1)],
    )


# ---- Intent detection. Returns a list of "intents" that can be proposed. ----
INTENT_PATTERNS = [
    ("approve_leave",     re.compile(r"\bapprove\b.+\bleave\b", re.I)),
    ("reject_leave",      re.compile(r"\b(reject|deny|decline)\b.+\bleave\b", re.I)),
    ("send_recognition",  re.compile(r"\b(recognise|recognize|kudos|appreciate|thank)\b", re.I)),
    ("send_recognition2", re.compile(r"\bsend\b.+\brecognition\b", re.I)),
    ("send_email",        re.compile(r"\bsend\b.+\b(email|message|notice|notification|acknowled|welcome|reminder|invitation|warning|letter)\b", re.I)),
    ("mark_task",         re.compile(r"\b(mark|close|complete|done)\b.+\btask\b", re.I)),
    ("assign_training",   re.compile(r"\b(assign|enroll|enrol)\b.+\btraining\b", re.I)),
]


def detect_intent(message: str) -> Optional[str]:
    for name, pat in INTENT_PATTERNS:
        if pat.search(message or ""):
            return "send_recognition" if name == "send_recognition2" else name
    return None


# ---- Build proposed_action payloads ----

async def propose_approve_leave(db, message: str, user: dict) -> Dict[str, Any]:
    emp = await _resolve_employee(db, message)
    if not emp:
        return {"error": "I couldn't match an employee name in your request. Try 'Approve <Full Name>'s leave'."}
    lv = await _find_leave(db, emp.get("id"))
    if not lv:
        return {"error": f"{emp['full_name']} has no leave currently pending approval."}
    return _action_payload(
        kind="approve_leave",
        risk=RISK_LOW,
        summary=f"Approve **{emp['full_name']}**'s {lv.get('leave_type')} leave: {lv.get('start_date')} → {lv.get('end_date')} ({lv.get('working_days')} working day(s)).",
        params={"leave_id": lv.get("id"), "employee_id": emp.get("id"), "employee_name": emp.get("full_name"),
                "leave_type": lv.get("leave_type"), "start_date": lv.get("start_date"),
                "end_date": lv.get("end_date"), "working_days": lv.get("working_days")},
        confirm_label="Approve Leave",
        cancel_label="Don't approve",
    )


async def propose_reject_leave(db, message: str, user: dict) -> Dict[str, Any]:
    emp = await _resolve_employee(db, message)
    if not emp:
        return {"error": "I couldn't match an employee. Try 'Reject <Full Name>'s leave because …'."}
    lv = await _find_leave(db, emp.get("id"))
    if not lv:
        return {"error": f"{emp['full_name']} has no leave currently pending approval."}
    # Pull reason after "because" / "—" / ":"
    reason = ""
    m = re.search(r"\bbecause\b(.+)$", message, re.I)
    if m:
        reason = m.group(1).strip(" .,;:'\"-")
    return _action_payload(
        kind="reject_leave",
        risk=RISK_MEDIUM,
        summary=f"Reject **{emp['full_name']}**'s {lv.get('leave_type')} leave ({lv.get('start_date')} → {lv.get('end_date')}).{(' Reason: ' + reason) if reason else ''}",
        params={"leave_id": lv.get("id"), "employee_id": emp.get("id"), "employee_name": emp.get("full_name"),
                "leave_type": lv.get("leave_type"), "reason": reason},
        confirm_label="Reject Leave",
        cancel_label="Don't reject",
        editable={"reason": reason},
    )


async def propose_send_recognition(db, message: str, user: dict) -> Dict[str, Any]:
    emp = await _resolve_employee(db, message)
    if not emp:
        return {"error": "I couldn't match an employee for the recognition. Try 'Send recognition to <Full Name> for …'."}
    # Pull message after "for"
    note = ""
    m = re.search(r"\b(for|saying|with the message)\b(.+)$", message, re.I)
    if m:
        note = m.group(2).strip(" .,;:'\"-")
    if not note:
        note = "Great work — appreciated by the whole team."
    return _action_payload(
        kind="send_recognition",
        risk=RISK_LOW,
        summary=f"Send manager-level recognition to **{emp['full_name']}** with the message: *\"{note}\"*",
        params={"employee_id": emp.get("id"), "employee_name": emp.get("full_name"), "message": note},
        confirm_label="Send Recognition",
        cancel_label="Don't send",
        editable={"message": note},
    )


async def propose_send_email(db, message: str, user: dict) -> Dict[str, Any]:
    # Try to find a template key in the message
    msg_l = message.lower()
    templates = [t async for t in db.email_templates.find({"tenant_id": "solvit"}, {"key": 1, "name": 1, "module": 1, "subject": 1})]
    if not templates:
        return {"error": "No email templates seeded yet — open Masters Settings → Email Templates first."}
    # Match by template name fragment first, then key fragment
    matched = None
    for t in templates:
        if t["name"].lower() in msg_l or t["key"].split(".")[-1].lower() in msg_l:
            matched = t
            break
    if not matched:
        # Suggest options (first 6)
        names = ", ".join(t["name"] for t in templates[:6])
        return {"error": f"I couldn't tell which email template you mean. Try one of: {names}…"}
    emp = await _resolve_employee(db, message)
    if not emp:
        return {"error": f"Found template **{matched['name']}** but couldn't match the recipient. Try 'Send {matched['name']} to <Full Name>'."}
    return _action_payload(
        kind="send_email",
        risk=RISK_MEDIUM,
        summary=f"Send **{matched['name']}** ({matched['module']}) to **{emp['full_name']}** at *{emp.get('work_email') or '—'}*.",
        params={"template_key": matched["key"], "template_name": matched["name"],
                "employee_id": emp.get("id"), "employee_name": emp.get("full_name"),
                "to_email": emp.get("work_email")},
        confirm_label="Send Email",
        cancel_label="Don't send",
    )


async def propose_mark_task(db, message: str, user: dict) -> Dict[str, Any]:
    # Resolve task by ID fragment or by the assignee
    task_id_match = re.search(r"\b([0-9a-f]{8})\b", message.lower())
    task = None
    if task_id_match:
        task = await db.tasks.find_one({"tenant_id": "solvit", "id": {"$regex": f"^{task_id_match.group(1)}", "$options": "i"}})
    if not task:
        task = await db.tasks.find_one({"tenant_id": "solvit", "assigned_to_user_id": user["id"], "status": {"$ne": "Done"}}, sort=[("created_at", -1)])
    if not task:
        return {"error": "I couldn't find a matching open task. Open /my-tasks to see the full list."}
    return _action_payload(
        kind="mark_task_complete",
        risk=RISK_LOW,
        summary=f"Mark task **{task.get('title') or task.get('description') or task.get('id')}** as complete.",
        params={"task_id": task.get("id"), "title": task.get("title")},
        confirm_label="Mark Complete",
        cancel_label="Leave open",
    )


async def propose_assign_training(db, message: str, user: dict) -> Dict[str, Any]:
    emp = await _resolve_employee(db, message)
    if not emp:
        return {"error": "I couldn't match an employee. Try 'Assign <training name> training to <Full Name>'."}
    # Extract training name between "assign" and "training" or after "in"
    m = re.search(r"\bassign\b(.+?)\btraining\b", message, re.I)
    training_name = m.group(1).strip(" .,;:'\"-") if m else None
    if not training_name:
        m2 = re.search(r"\btraining\b(.+?)\bto\b", message, re.I)
        training_name = m2.group(1).strip(" .,;:'\"-") if m2 else "General training"
    return _action_payload(
        kind="assign_training",
        risk=RISK_LOW,
        summary=f"Assign **{training_name}** training to **{emp['full_name']}**.",
        params={"employee_id": emp.get("id"), "employee_name": emp.get("full_name"), "training_name": training_name},
        confirm_label="Assign Training",
        cancel_label="Don't assign",
        editable={"training_name": training_name},
    )


def _action_payload(kind: str, risk: str, summary: str, params: dict,
                    confirm_label: str, cancel_label: str,
                    editable: Optional[dict] = None) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "risk": risk,
        "summary": summary,
        "params": params,
        "confirm_label": confirm_label,
        "cancel_label": cancel_label,
        "editable": editable or {},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    }


# ---- Dispatcher: takes a detected intent and produces a proposed_action ----

INTENT_PROPOSERS = {
    "approve_leave":    propose_approve_leave,
    "reject_leave":     propose_reject_leave,
    "send_recognition": propose_send_recognition,
    "send_email":       propose_send_email,
    "mark_task":        propose_mark_task,
    "assign_training":  propose_assign_training,
}


# ---- Action EXECUTORS — run after HR confirms ----

async def execute_approve_leave(db, params: dict, user: dict) -> Dict[str, Any]:
    leave_id = params["leave_id"]
    lv = await db.leave_requests.find_one({"id": leave_id})
    if not lv:
        return {"ok": False, "error": "Leave request not found"}
    now = datetime.now(timezone.utc).isoformat()
    # Mirror /api/leave/{id}/decision logic — flip to next stage or Approved.
    new_status = "Pending_HR" if lv.get("status") == "Pending_Manager" else "Approved"
    if user.get("role") in ("hr_admin", "hr_manager"):
        new_status = "Approved"
    await db.leave_requests.update_one(
        {"id": leave_id},
        {"$set": {"status": new_status, "approved_by": user["id"],
                  "approved_by_name": user.get("full_name") or user.get("email"),
                  "approved_at": now}}
    )
    # Notify employee
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "user_id": lv.get("employee_id"),
        "title": "Leave approved",
        "message": f"Your {lv.get('leave_type')} leave ({lv.get('start_date')} → {lv.get('end_date')}) was approved by {user.get('full_name') or user.get('email')} via AI Assistant.",
        "is_read": False, "created_at": now,
    })
    return {"ok": True, "new_status": new_status, "leave_id": leave_id}


async def execute_reject_leave(db, params: dict, user: dict) -> Dict[str, Any]:
    leave_id = params["leave_id"]
    now = datetime.now(timezone.utc).isoformat()
    lv = await db.leave_requests.find_one({"id": leave_id})
    if not lv:
        return {"ok": False, "error": "Leave request not found"}
    await db.leave_requests.update_one(
        {"id": leave_id},
        {"$set": {"status": "Rejected", "rejection_reason": params.get("reason") or "No reason given",
                  "rejected_by": user["id"], "rejected_by_name": user.get("full_name") or user.get("email"),
                  "rejected_at": now}}
    )
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "user_id": lv.get("employee_id"),
        "title": "Leave rejected",
        "message": f"Your {lv.get('leave_type')} leave was rejected. Reason: {params.get('reason') or '—'}.",
        "is_read": False, "created_at": now,
    })
    return {"ok": True, "leave_id": leave_id}


async def execute_send_recognition(db, params: dict, user: dict) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "recognition_type": "Manager",
        "employee_id": params["employee_id"],
        "employee_name": params.get("employee_name"),
        "message": params["message"],
        "category": "AI-assisted",
        "nominator_id": user["id"],
        "nominator_name": user.get("full_name") or user.get("email"),
        "status": "Approved",
        "created_at": now,
    }
    await db.recognitions.insert_one(doc)
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "user_id": params["employee_id"],
        "title": "You've been recognised",
        "message": f"{user.get('full_name') or 'Your manager'} recognised you: \"{params['message']}\"",
        "is_read": False, "created_at": now,
    })
    return {"ok": True, "recognition_id": doc["id"]}


async def execute_send_email(db, params: dict, user: dict) -> Dict[str, Any]:
    """Render the template and persist a queued send. We do NOT bypass the
    Email Delivery config here — the SMTP send still goes through the live
    config; if it's the Mailtrap (Testing) mode the message is routed there.
    On any SMTP failure we record the error but still mark the action as
    'rendered' so it can be re-sent from /audit."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    template = await db.email_templates.find_one({"tenant_id": "solvit", "key": params["template_key"]})
    if not template:
        return {"ok": False, "error": "Template not found"}
    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"}) or {}
    mode = cfg.get("active_mode", "testing")
    m = cfg.get(mode) or {}
    # Render
    emp = await db.employees.find_one({"tenant_id": "solvit", "id": params["employee_id"]})
    merge = {
        "employee_name": (emp or {}).get("full_name") or params.get("employee_name"),
        "employee_email": (emp or {}).get("work_email") or params.get("to_email"),
        "manager_name": user.get("full_name") or "Solvit HR",
        "company_name": "Solvit Limited",
        "today": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
    }
    def render(tpl):
        return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", lambda mt: str(merge.get(mt.group(1), mt.group(0))), tpl or "")
    subject = render(template.get("subject"))
    body_html = render(template.get("body"))
    to_addr = params.get("to_email") or (emp or {}).get("work_email")
    if not to_addr:
        return {"ok": False, "error": "No destination email on the employee record."}
    now = datetime.now(timezone.utc).isoformat()
    log_doc = {
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "template_key": params["template_key"],
        "employee_id": params["employee_id"], "to_email": to_addr,
        "subject": subject, "body_html": body_html,
        "mode": mode, "status": "queued",
        "sent_by": user["id"], "sent_by_name": user.get("full_name") or user.get("email"),
        "sent_at": now,
    }
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{m.get('from_name') or 'Solvit'} <{m.get('from_email') or 'no-reply@solvit.co.ke'}>"
        msg["To"] = to_addr
        msg.attach(MIMEText(body_html, "html"))
        host = m.get("smtp_host"); port = int(m.get("smtp_port") or 0)
        if not host or not port:
            log_doc["status"] = "rendered_only"; log_doc["error"] = "SMTP not configured"
        else:
            enc = (m.get("encryption") or "STARTTLS").upper()
            if enc == "SSL":
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                if enc == "STARTTLS":
                    server.starttls()
            if m.get("username") and m.get("password"):
                server.login(m["username"], m["password"])
            server.sendmail(m.get("from_email"), [to_addr], msg.as_string())
            server.quit()
            log_doc["status"] = "sent"
    except Exception as e:
        log_doc["status"] = "failed"; log_doc["error"] = str(e)
    await db.email_send_log.insert_one(log_doc)
    return {"ok": log_doc["status"] in ("sent", "rendered_only"), "send_status": log_doc["status"],
            "error": log_doc.get("error"), "to": to_addr}


async def execute_mark_task(db, params: dict, user: dict) -> Dict[str, Any]:
    task_id = params["task_id"]
    now = datetime.now(timezone.utc).isoformat()
    res = await db.tasks.update_one({"id": task_id},
        {"$set": {"status": "Done", "completed_at": now, "completed_by": user["id"]}})
    return {"ok": res.modified_count > 0, "task_id": task_id}


async def execute_assign_training(db, params: dict, user: dict) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "employee_id": params["employee_id"], "employee_name": params.get("employee_name"),
        "title": params["training_name"], "name": params["training_name"],
        "status": "Approved", "source": "AI Assistant",
        "requested_by": user["id"], "requested_by_name": user.get("full_name") or user.get("email"),
        "created_at": now,
    }
    await db.training_requests.insert_one(doc)
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "user_id": params["employee_id"],
        "title": "Training assigned",
        "message": f"You've been assigned the training **{params['training_name']}**.",
        "is_read": False, "created_at": now,
    })
    return {"ok": True, "training_id": doc["id"]}


EXECUTORS = {
    "approve_leave":      execute_approve_leave,
    "reject_leave":       execute_reject_leave,
    "send_recognition":   execute_send_recognition,
    "send_email":         execute_send_email,
    "mark_task_complete": execute_mark_task,
    "assign_training":    execute_assign_training,
}


# ---- RBAC: who can confirm what ----
ACTION_REQUIRED_ROLES = {
    "approve_leave":      ("hr_admin", "hr_manager", "line_manager"),
    "reject_leave":       ("hr_admin", "hr_manager", "line_manager"),
    "send_recognition":   ("hr_admin", "hr_manager", "line_manager"),
    "send_email":         ("hr_admin", "hr_manager"),
    "mark_task_complete": ("hr_admin", "hr_manager", "line_manager", "employee", "finance", "executive", "it_admin"),
    "assign_training":    ("hr_admin", "hr_manager", "line_manager"),
}


def can_execute(action_kind: str, role: str) -> bool:
    return role in ACTION_REQUIRED_ROLES.get(action_kind, ())
