"""Email sending pipeline — supports SendGrid + generic SMTP. Provider chosen via Settings."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


class EmailDeliveryError(Exception):
    pass


async def send_email(db, to: str, subject: str, html: str, text: Optional[str] = None) -> dict:
    """Send via the provider configured in /api/settings.
    Returns {provider, status, message}. Falls back gracefully when not configured."""
    settings_doc = await db.platform_settings.find_one({"tenant_id": "solvit"})
    if not settings_doc:
        return {"provider": "none", "status": "skipped", "message": "Email not configured"}

    provider = (settings_doc.get("email_provider") or "").lower()
    from_addr = settings_doc.get("email_from_address") or "noreply@solvit.co.ke"
    from_name = settings_doc.get("email_from_name") or "Solvit People Platform"

    if provider == "sendgrid":
        api_key = settings_doc.get("email_api_key") or os.environ.get("SENDGRID_API_KEY")
        if not api_key:
            return {"provider": "sendgrid", "status": "skipped", "message": "API key missing"}
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To, HtmlContent, PlainTextContent
            msg = Mail(
                from_email=Email(from_addr, from_name),
                to_emails=To(to),
                subject=subject,
                plain_text_content=PlainTextContent(text or _strip_html(html)),
                html_content=HtmlContent(html)
            )
            sg = SendGridAPIClient(api_key)
            resp = sg.send(msg)
            return {"provider": "sendgrid", "status": "sent" if resp.status_code in (200, 202) else "failed", "code": resp.status_code}
        except Exception as e:
            raise EmailDeliveryError(f"SendGrid: {e}")

    elif provider == "smtp":
        host = settings_doc.get("smtp_host")
        port = int(settings_doc.get("smtp_port") or 587)
        user = settings_doc.get("smtp_username")
        pwd = settings_doc.get("smtp_password") or settings_doc.get("email_api_key")
        use_tls = settings_doc.get("smtp_use_tls", True)
        if not (host and user and pwd):
            return {"provider": "smtp", "status": "skipped", "message": "SMTP not fully configured"}
        try:
            mime = MIMEMultipart("alternative")
            mime["Subject"] = subject
            mime["From"] = f"{from_name} <{from_addr}>"
            mime["To"] = to
            mime.attach(MIMEText(text or _strip_html(html), "plain"))
            mime.attach(MIMEText(html, "html"))
            with smtplib.SMTP(host, port, timeout=15) as server:
                if use_tls:
                    server.starttls()
                server.login(user, pwd)
                server.sendmail(from_addr, [to], mime.as_string())
            return {"provider": "smtp", "status": "sent"}
        except Exception as e:
            raise EmailDeliveryError(f"SMTP: {e}")

    return {"provider": provider or "none", "status": "skipped", "message": "Provider not configured"}


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html or "").strip()
