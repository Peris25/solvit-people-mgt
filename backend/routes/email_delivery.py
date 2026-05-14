"""Email Delivery Settings — Testing (Mailtrap) / Production (Office 365) modes.

Stores config in collection `email_delivery_config` (singleton per tenant).
Only IT Admin can edit/switch modes; HR Admin can view active mode. Mode
changes are logged in `email_delivery_audit`.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from typing import Optional
from database import get_db
from utils.auth import get_current_user
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter(prefix="/email-delivery", tags=["email_delivery"])

DEFAULTS = {
    "active_mode": "testing",  # 'testing' or 'production'
    "testing": {
        "smtp_host": "sandbox.smtp.mailtrap.io",
        "smtp_port": 2525,
        "username": "",
        "password": "",
        "from_name": "Solvit People (Test)",
        "from_email": "no-reply@test.solvit.co.ke",
    },
    "production": {
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "encryption": "STARTTLS",
        "username": "",
        "password": "",
        "from_name": "Solvit People",
        "from_email": "no-reply@solvit.co.ke",
    },
    "last_test": None,
}


def _mask(s):
    if not s:
        return ""
    if len(s) <= 4:
        return "***"
    return s[:2] + "***" + s[-2:]


def _safe(cfg):
    """Return a copy with masked credentials."""
    import copy
    c = copy.deepcopy(cfg)
    for mode in ("testing", "production"):
        m = c.get(mode) or {}
        if m.get("password"):
            m["password"] = _mask(m["password"])
        c[mode] = m
    return c


def _is_it(role):
    return role == "it_admin"


@router.get("")
async def get_config(request: Request):
    user = await get_current_user(request)
    role = user.get("role")
    if role not in ("it_admin", "hr_admin", "hr_manager"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        cfg = {"tenant_id": "solvit", **DEFAULTS}
        await db.email_delivery_config.insert_one(cfg)
    cfg.pop("_id", None)
    return {"can_edit": _is_it(role), **_safe(cfg)}


@router.put("/{mode}")
async def update_mode_config(mode: str, request: Request):
    user = await get_current_user(request)
    if not _is_it(user.get("role")):
        raise HTTPException(status_code=403, detail="IT Admin only")
    if mode not in ("testing", "production"):
        raise HTTPException(status_code=400, detail="Unknown mode")
    db = get_db()
    body = await request.json()
    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        cfg = {"tenant_id": "solvit", **DEFAULTS}
        await db.email_delivery_config.insert_one(cfg)
    update = dict(cfg.get(mode) or {})
    update.update({k: v for k, v in body.items() if k in (
        "smtp_host", "smtp_port", "username", "password", "from_name", "from_email", "encryption"
    ) and v is not None})
    await db.email_delivery_config.update_one(
        {"tenant_id": "solvit"},
        {"$set": {mode: update, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}}
    )
    return {"updated": True, "mode": mode}


@router.post("/switch")
async def switch_mode(request: Request):
    user = await get_current_user(request)
    if not _is_it(user.get("role")):
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    mode = body.get("mode")
    if mode not in ("testing", "production"):
        raise HTTPException(status_code=400, detail="Mode must be 'testing' or 'production'")
    db = get_db()
    prev = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    old_mode = (prev or {}).get("active_mode")
    now = datetime.now(timezone.utc).isoformat()
    await db.email_delivery_config.update_one(
        {"tenant_id": "solvit"}, {"$set": {"active_mode": mode, "updated_at": now, "updated_by": user["id"]}}, upsert=True
    )
    await db.email_delivery_audit.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "action": "mode_switched", "old_mode": old_mode, "new_mode": mode,
        "by_user_id": user["id"], "by_user_name": user.get("full_name") or user.get("email"),
        "timestamp": now,
    })
    return {"active_mode": mode}


@router.post("/test-send")
async def test_send(request: Request):
    user = await get_current_user(request)
    if not _is_it(user.get("role")):
        raise HTTPException(status_code=403, detail="IT Admin only")
    body = await request.json()
    to_addr = body.get("to")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Missing `to`")
    db = get_db()
    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        raise HTTPException(status_code=400, detail="Email delivery not configured")
    mode = cfg.get("active_mode") or "testing"
    m = cfg.get(mode) or {}
    host, port = m.get("smtp_host"), int(m.get("smtp_port") or 0)
    user_name, pwd = m.get("username") or "", m.get("password") or ""
    from_name = m.get("from_name") or "Solvit People"
    from_email = m.get("from_email") or "no-reply@solvit.co.ke"
    encryption = (m.get("encryption") or "STARTTLS").upper()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Solvit Email Delivery Test ({mode})"
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_addr
    html = f"<p>This is a test email from <strong>Solvit People Platform</strong>.</p><p>Mode: <strong>{mode}</strong><br/>Sent at: {datetime.now(timezone.utc).isoformat()}</p>"
    msg.attach(MIMEText(html, "html"))

    status, code, error = "Success", "250", None
    try:
        if encryption == "SSL":
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if encryption == "STARTTLS":
                server.starttls()
        if user_name and pwd:
            server.login(user_name, pwd)
        server.sendmail(from_email, [to_addr], msg.as_string())
        server.quit()
    except smtplib.SMTPException as e:
        status, code, error = "Failed", str(getattr(e, "smtp_code", "")) or "SMTP", str(e)
    except Exception as e:
        status, code, error = "Failed", "ERR", str(e)

    now = datetime.now(timezone.utc).isoformat()
    last_test = {"to": to_addr, "mode": mode, "status": status, "smtp_code": code, "error": error, "tested_at": now,
                 "tested_by": user.get("full_name") or user.get("email")}
    await db.email_delivery_config.update_one({"tenant_id": "solvit"}, {"$set": {"last_test": last_test}})
    return last_test


@router.get("/audit")
async def get_audit(request: Request, limit: int = 50):
    user = await get_current_user(request)
    if user.get("role") not in ("it_admin", "hr_admin"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    rows = await db.email_delivery_audit.find({"tenant_id": "solvit"}).sort("timestamp", -1).to_list(min(limit, 200))
    for r in rows:
        r.pop("_id", None)
    return rows


@router.get("/log")
async def get_email_log(request: Request, limit: int = 100, status: Optional[str] = None):
    """Recent email send attempts across the platform.

    Combines two collections:
      - `email_log`        — sends from utils/email_service.send_email() (leave,
                             surveys, automation, settings)
      - `email_send_log`   — AI Agent send-email actions (separate audit doc).

    Read-only. Visible to IT Admin + HR Admin.
    """
    user = await get_current_user(request)
    if user.get("role") not in ("it_admin", "hr_admin", "hr_manager"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    n = min(max(limit, 1), 500)
    q = {"tenant_id": "solvit"}
    if status:
        q["status"] = status
    primary = await db.email_log.find(q).sort("sent_at", -1).to_list(n)
    ai = await db.email_send_log.find(q).sort("sent_at", -1).to_list(n)
    rows = []
    for r in primary:
        rows.append({
            "id": str(r.get("_id")),
            "to": r.get("to"),
            "subject": r.get("subject"),
            "template_key": r.get("template_key"),
            "mode": r.get("mode"),
            "status": r.get("status"),
            "error": r.get("error"),
            "sent_at": r.get("sent_at"),
            "source": "system",
        })
    for r in ai:
        rows.append({
            "id": str(r.get("_id")),
            "to": r.get("to_email"),
            "subject": r.get("subject"),
            "template_key": r.get("template_key"),
            "mode": r.get("mode"),
            "status": r.get("status"),
            "error": r.get("error"),
            "sent_at": r.get("sent_at"),
            "source": "ai_agent",
            "sent_by_name": r.get("sent_by_name"),
        })
    rows.sort(key=lambda r: r.get("sent_at") or "", reverse=True)
    return rows[:n]
