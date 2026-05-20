"""Email sending pipeline.

Single source of truth: the `email_delivery_config` collection.

Special behaviours:
  - Mailtrap sandbox throttle (2.5 sec / send)
  - Formal Template Override: templates flagged is_formal=True ALWAYS use the
    production SMTP config, even when active_mode='testing'. Legal documents
    (Notice to Show Cause, Written Warning, Confidentiality Ack, Offer Letter)
    must reach the real recipient.
  - Retry-on-failure: 5 min → 30 min → 2 hr (queued in `email_retry_queue`,
    processed by a background coroutine in this module).
  - After 3 failed retries, an in-platform alert is created for IT Admin.
"""
import asyncio
import re
import smtplib
import time
import logging
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

# Mailtrap sandbox: ~5 emails / 10 seconds.
_SEND_LOCK = asyncio.Lock()
_LAST_SEND_TS = [0.0]
_MIN_INTERVAL_S = 2.5

# Templates that must ALWAYS bypass Mailtrap and use the production SMTP
# config — legal / contractual documents the recipient must actually receive.
FORMAL_TEMPLATE_KEYS = {
    "disciplinary.show_cause",     # DISC-01 Notice to Show Cause
    "disciplinary.written",         # DISC-03 Written Warning
    "disciplinary.final",           # Final Warning (also formal)
    "disciplinary.dismissal",       # Dismissal letter
    "exit.confidentiality_ack",     # EXIT-03 Post-Employment Confidentiality
    "recruitment.offer",            # RECR-07 Offer Letter
}

RETRY_DELAYS_MIN = [5, 30, 120]  # minutes after each attempt


class EmailDeliveryError(Exception):
    pass


async def _log_skip(db, to: Optional[str], reason: str, template_key: Optional[str] = None, mode: Optional[str] = None) -> None:
    try:
        await db.email_log.insert_one({
            "tenant_id": "solvit",
            "to": to, "subject": None, "template_key": template_key,
            "mode": mode, "status": "skipped", "error": reason,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


def _merge(template: str, ctx: dict) -> str:
    def sub(m):
        v = ctx.get(m.group(1).strip(), "")
        return "" if v is None else str(v)
    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", sub, template or "")


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _wrap_solvit_brand(body_html: str) -> str:
    """Wrap rendered template body in a brand-consistent Solvit header/footer."""
    if "<!--solvit-wrapped-->" in body_html:
        return body_html
    return f"""<!--solvit-wrapped-->
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F5F5F5;font-family:Barlow,Arial,sans-serif;padding:20px 0;">
  <tr><td align="center">
    <table cellpadding="0" cellspacing="0" border="0" width="600" style="background:#FFFFFF;border-top:4px solid #FF353F;">
      <tr><td style="padding:20px 32px 8px 32px;">
        <span style="font-size:22px;font-weight:900;letter-spacing:-0.04em;color:#191919;">SOLVIT</span>
        <span style="font-size:10px;font-weight:700;letter-spacing:0.2em;color:#FF353F;margin-left:4px;">PEOPLE PLATFORM</span>
      </td></tr>
      <tr><td style="padding:18px 32px 28px 32px;color:#191919;font-size:14px;line-height:1.55;font-family:Nunito Sans,Arial,sans-serif;">
        {body_html}
      </td></tr>
      <tr><td style="padding:14px 32px;background:#191919;color:#9CA3AF;font-size:10px;letter-spacing:0.1em;">
        SOLVIT LIMITED · NAIROBI, KENYA · NO-REPLY@SOLVIT.CO.KE
      </td></tr>
    </table>
  </td></tr>
</table>"""


async def _resolve_smtp(db, formal: bool) -> tuple:
    """Return (mode, smtp config dict) honouring the formal-override rule."""
    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        return (None, {})
    if formal:
        # Formal templates always use production credentials regardless of toggle.
        prod = cfg.get("production") or {}
        if prod.get("smtp_host") and prod.get("password"):
            return ("production", prod)
        # Fall back if no production config — caller will skip with reason.
        return ("production_missing", prod)
    mode = cfg.get("active_mode") or "testing"
    return (mode, cfg.get(mode) or {})


async def _attempt_send(host, port, encryption, user, pwd, from_addr, from_name, to, mime) -> None:
    """Perform one SMTP transaction. Raises on failure."""
    if encryption == "SSL":
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)
        if encryption == "STARTTLS":
            server.starttls()
    try:
        if user:
            server.login(user, pwd)
        elif pwd:
            server.login("", pwd)
        server.sendmail(from_addr, [to], mime.as_string())
    finally:
        server.quit()


async def _attempt_send_sender_net(api_key, from_addr, from_name, to, subject, html, text) -> None:
    """Send via Sender.net's transactional HTTP API.

    Docs: https://api.sender.net/v2/email/send
    Raises on non-2xx so the existing retry / log path is reused.
    """
    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "to": [{"email": to}],
        "from": {"email": from_addr, "name": from_name},
        "subject": subject,
        "html": html,
        "text": text,
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://api.sender.net/v2/email/send",
                          headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"sender.net HTTP {r.status_code}: {r.text[:200]}")


async def send_email(
    db,
    to: str,
    subject: Optional[str] = None,
    html: Optional[str] = None,
    text: Optional[str] = None,
    template_key: Optional[str] = None,
    context: Optional[dict] = None,
    retry_count: int = 0,
) -> dict:
    if not to:
        await _log_skip(db, None, "no recipient", template_key)
        return {"status": "skipped", "message": "no recipient"}

    is_formal = template_key in FORMAL_TEMPLATE_KEYS
    mode, bucket = await _resolve_smtp(db, is_formal)
    if not bucket:
        await _log_skip(db, to, "email delivery not configured", template_key)
        return {"status": "skipped", "message": "email delivery not configured"}

    host = bucket.get("smtp_host")
    port = int(bucket.get("smtp_port") or 587)
    user = bucket.get("username")
    pwd = bucket.get("password")
    from_addr = bucket.get("from_email") or "jmining@solvit.co.ke"
    from_name = bucket.get("from_name") or "Solvit People Platform"
    encryption = (bucket.get("encryption") or ("STARTTLS" if mode == "production" else "")).upper()
    provider = (bucket.get("provider") or "smtp").lower()
    api_key = bucket.get("api_key") or pwd  # sender.net stores its key in password OR api_key

    if provider == "sender_net":
        if not api_key:
            msg = f"Sender.net API key not configured in '{mode}' mode"
            await _log_skip(db, to, msg, template_key, mode=mode)
            return {"status": "skipped", "message": msg}
    elif not (host and pwd):
        msg = f"SMTP not configured in '{mode}' mode"
        if is_formal and mode == "production_missing":
            msg = "Formal template requires production SMTP — none configured"
        await _log_skip(db, to, msg, template_key, mode=mode)
        return {"status": "skipped", "message": msg}

    ctx = context or {}
    if template_key and (not subject or not html):
        tpl = await db.email_templates.find_one({"tenant_id": "solvit", "key": template_key})
        if tpl:
            subject = subject or _merge(tpl.get("subject", ""), ctx)
            html = html or _merge(tpl.get("body", ""), ctx)

    subject = subject or "Solvit People Platform"
    html = _wrap_solvit_brand(html or "<p>(no body)</p>")

    mime = MIMEMultipart("alternative")
    mime["Subject"] = subject
    mime["From"] = f"{from_name} <{from_addr}>"
    mime["To"] = to
    if is_formal:
        mime["X-Formal-Document"] = "true"
    mime.attach(MIMEText(text or _strip_html(html), "plain"))
    mime.attach(MIMEText(html, "html"))

    try:
        async with _SEND_LOCK:
            gap = time.monotonic() - _LAST_SEND_TS[0]
            if gap < _MIN_INTERVAL_S:
                await asyncio.sleep(_MIN_INTERVAL_S - gap)
            try:
                if provider == "sender_net":
                    await _attempt_send_sender_net(
                        api_key, from_addr, from_name, to, subject, html,
                        text or _strip_html(html))
                else:
                    await _attempt_send(host, port, encryption, user, pwd,
                                         from_addr, from_name, to, mime)
            finally:
                _LAST_SEND_TS[0] = time.monotonic()
        await db.email_log.insert_one({
            "tenant_id": "solvit", "to": to, "subject": subject,
            "template_key": template_key, "mode": mode, "status": "sent",
            "provider": provider,
            "formal": is_formal, "retry_count": retry_count,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "sent", "mode": mode, "provider": provider, "to": to, "formal": is_formal}

    except Exception as e:
        err = str(e)
        await db.email_log.insert_one({
            "tenant_id": "solvit", "to": to, "subject": subject,
            "template_key": template_key, "mode": mode, "status": "failed",
            "error": err, "formal": is_formal, "retry_count": retry_count,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        # Queue a retry if not exhausted
        if retry_count < len(RETRY_DELAYS_MIN):
            await _queue_retry(db, to, template_key, ctx, subject, html, retry_count)
        else:
            await _alert_it_admin_failure(db, to, template_key, err)
        return {"status": "failed", "error": err}


async def _queue_retry(db, to, template_key, ctx, subject, html, retry_count):
    delay_min = RETRY_DELAYS_MIN[retry_count]
    next_at = (datetime.now(timezone.utc) + timedelta(minutes=delay_min)).isoformat()
    await db.email_retry_queue.insert_one({
        "tenant_id": "solvit",
        "to": to, "template_key": template_key,
        "context": ctx, "subject": subject, "html": html,
        "retry_count": retry_count + 1,
        "next_attempt_at": next_at,
        "status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    })


async def _alert_it_admin_failure(db, to, template_key, err):
    import uuid
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "recipient_role": "it_admin",
        "category": "Email",
        "title": "Email delivery failed after 3 attempts",
        "message": f"Template '{template_key}' to {to} failed permanently. Error: {err}. Check Notification Log → Settings → Email Delivery.",
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def process_retry_queue(db) -> int:
    """Process any retries whose next_attempt_at has passed. Called by scheduler."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = db.email_retry_queue.find({
        "tenant_id": "solvit", "status": "pending",
        "next_attempt_at": {"$lte": now},
    })
    rows = await cursor.to_list(50)
    processed = 0
    for row in rows:
        await db.email_retry_queue.update_one(
            {"_id": row["_id"]}, {"$set": {"status": "processing"}}
        )
        result = await send_email(
            db, to=row["to"],
            subject=row["subject"], html=row["html"],
            template_key=row.get("template_key"),
            context=row.get("context") or {},
            retry_count=row["retry_count"],
        )
        final_status = "sent" if result.get("status") == "sent" else "exhausted" if row["retry_count"] >= len(RETRY_DELAYS_MIN) else "requeued"
        await db.email_retry_queue.update_one(
            {"_id": row["_id"]},
            {"$set": {"status": final_status, "completed_at": datetime.now(timezone.utc).isoformat()}}
        )
        processed += 1
    return processed
