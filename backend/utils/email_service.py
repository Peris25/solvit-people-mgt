"""Email sending pipeline.

Single source of truth: the `email_delivery_config` collection (managed by
IT Admin under Platform Settings → Email Delivery). The active_mode flag
('testing' = Mailtrap, 'production' = Office 365) selects which credentials
to use. The 'Send Test Email' button on that page uses these same creds, so
if the test arrives, real emails will too.

Templates live in the `email_templates` collection and are merged with a
context dict via simple {{merge_tag}} substitution. If a template key is
missing the caller's explicit subject + html body fall back transparently.
"""
import asyncio
import re
import smtplib
import time
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)

# Mailtrap's sandbox plan is rate-limited to ~1 email/second. To avoid the
# `5.7.0 Too many emails per second` 550 error during burst sends (e.g. a leave
# submission fires 2-3 emails + an automation rule fires another 2), we serialize
# sends through this lock and enforce a minimum gap between SMTP transactions.
_SEND_LOCK = asyncio.Lock()
_LAST_SEND_TS = [0.0]
_MIN_INTERVAL_S = 2.5   # Mailtrap sandbox: 5 emails / 10 seconds = 2s ceiling. Margin = 0.5s.


class EmailDeliveryError(Exception):
    pass


def _merge(template: str, ctx: dict) -> str:
    """Substitute {{key}} tags with values from ctx. Missing keys become ''. """
    def sub(m):
        key = m.group(1).strip()
        v = ctx.get(key, "")
        return "" if v is None else str(v)
    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", sub, template or "")


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


async def send_email(
    db,
    to: str,
    subject: Optional[str] = None,
    html: Optional[str] = None,
    text: Optional[str] = None,
    template_key: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    """Send one email via the active SMTP config.

    Provide either:
      (a) explicit subject + html (legacy direct send), or
      (b) template_key (looked up in `email_templates`) + context dict.

    Returns {provider, status, message} and never raises into the caller —
    we log and swallow so a missing SMTP password never breaks core flows
    like leave submission. Caller can check `status` to know if it actually
    went out.
    """
    if not to:
        return {"status": "skipped", "message": "no recipient"}

    cfg = await db.email_delivery_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        return {"status": "skipped", "message": "email delivery not configured"}

    mode = cfg.get("active_mode") or "testing"
    bucket = cfg.get(mode) or {}
    host = bucket.get("smtp_host")
    port = int(bucket.get("smtp_port") or 587)
    user = bucket.get("username")
    pwd = bucket.get("password")
    from_addr = bucket.get("from_email") or "no-reply@solvit.co.ke"
    from_name = bucket.get("from_name") or "Solvit People Platform"
    encryption = (bucket.get("encryption") or ("STARTTLS" if mode == "production" else "")).upper()

    if not (host and pwd):  # username can be empty for some sandboxes
        logger.info("Email skipped: SMTP not fully configured (mode=%s)", mode)
        return {"status": "skipped", "message": f"SMTP not configured in '{mode}' mode"}

    # Resolve template if provided
    ctx = context or {}
    if template_key and (not subject or not html):
        tpl = await db.email_templates.find_one({"tenant_id": "solvit", "key": template_key})
        if tpl:
            subject = subject or _merge(tpl.get("subject", ""), ctx)
            html = html or _merge(tpl.get("body", ""), ctx)

    if not subject:
        subject = "Solvit People Platform"
    if not html:
        html = "<p>(no body)</p>"

    try:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = subject
        mime["From"] = f"{from_name} <{from_addr}>"
        mime["To"] = to
        mime.attach(MIMEText(text or _strip_html(html), "plain"))
        mime.attach(MIMEText(html, "html"))

        # Serialize SMTP transactions and pace them >1/s for Mailtrap sandbox.
        async with _SEND_LOCK:
            gap = time.monotonic() - _LAST_SEND_TS[0]
            if gap < _MIN_INTERVAL_S:
                await asyncio.sleep(_MIN_INTERVAL_S - gap)

            try:
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
            finally:
                # Always record attempt time — even on failure — so a rate-
                # limit rejection on one send doesn't cause the next send to
                # bypass the throttle window.
                _LAST_SEND_TS[0] = time.monotonic()

        # Log every send for audit / debugging
        from datetime import datetime, timezone
        await db.email_log.insert_one({
            "tenant_id": "solvit",
            "to": to,
            "subject": subject,
            "template_key": template_key,
            "mode": mode,
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Email sent to %s subject=%r mode=%s", to, subject, mode)
        return {"status": "sent", "mode": mode, "to": to}

    except Exception as e:
        logger.warning("Email send failed to %s: %s", to, e)
        from datetime import datetime, timezone
        await db.email_log.insert_one({
            "tenant_id": "solvit",
            "to": to,
            "subject": subject,
            "template_key": template_key,
            "mode": mode,
            "status": "failed",
            "error": str(e),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "failed", "error": str(e)}
