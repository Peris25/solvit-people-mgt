from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/settings", tags=["settings"])


class PlatformSettings(BaseModel):
    llm_provider: Optional[str] = None  # openai, anthropic, gemini
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    email_provider: Optional[str] = None  # sendgrid, smtp, none
    email_api_key: Optional[str] = None
    email_from_address: Optional[str] = None
    email_from_name: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    timezone: Optional[str] = "Africa/Nairobi"
    currency: Optional[str] = "KES"
    date_format: Optional[str] = "DD/MM/YYYY"
    tenant_name: Optional[str] = "Solvit Limited"
    tenant_logo_url: Optional[str] = None
    automation_enabled: Optional[bool] = True
    ai_agent_enabled: Optional[bool] = True


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc.get("_id", ""))
    doc["_id"] = str(doc.get("_id", ""))
    for field in ("llm_api_key", "email_api_key", "smtp_password"):
        if doc.get(field):
            doc[field] = "***"
    return doc


@router.get("")
async def get_settings(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    settings = await db.platform_settings.find_one({"tenant_id": "solvit"})
    if not settings:
        return {
            "tenant_id": "solvit",
            "tenant_name": "Solvit Limited",
            "timezone": "Africa/Nairobi",
            "currency": "KES",
            "date_format": "DD/MM/YYYY",
            "llm_provider": None,
            "llm_model": None,
            "email_provider": None,
            "automation_enabled": True,
            "ai_agent_enabled": True
        }
    return fmt(settings)


@router.put("")
async def update_settings(settings: PlatformSettings, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can update settings")
    db = get_db()
    update_data = {k: v for k, v in settings.model_dump().items() if v is not None}
    for field in ("llm_api_key", "email_api_key", "smtp_password"):
        if update_data.get(field) == "***":
            update_data.pop(field)
    update_data["updated_by"] = user["id"]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.platform_settings.find_one_and_update(
        {"tenant_id": "solvit"},
        {"$set": update_data},
        upsert=True,
        return_document=True
    )
    return fmt(result)


@router.get("/raw")
async def get_raw_settings(request: Request):
    """Internal use — returns settings with real keys for AI/email integrations"""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    settings = await db.platform_settings.find_one({"tenant_id": "solvit"})
    if not settings:
        return {}
    settings["id"] = str(settings["_id"])
    settings["_id"] = str(settings["_id"])
    return settings


@router.post("/email-test")
async def email_test(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can send test emails")
    body = await request.json()
    to = body.get("to") or user.get("email")
    if not to:
        raise HTTPException(status_code=400, detail="Missing recipient")
    db = get_db()
    from utils.email_service import send_email, EmailDeliveryError
    try:
        result = await send_email(
            db, to,
            subject="Solvit People Platform — Test Email",
            html=f"<p>Hello,</p><p>This is a test email sent from Solvit People Platform at {datetime.now(timezone.utc).isoformat()}.</p><p>Provider: <strong>{(await db.platform_settings.find_one({'tenant_id': 'solvit'}) or {}).get('email_provider') or 'none'}</strong></p><p>If you received this, your email pipeline is working.</p>"
        )
        return result
    except EmailDeliveryError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-demo-data")
async def reset_demo_data_endpoint(request: Request):
    """Wipe all transactional demo data and re-seed (keeps user accounts intact)"""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can reset demo data")
    db = get_db()
    from automation.seed_data import reset_demo_data
    await reset_demo_data(db)
    return {"status": "success", "message": "Demo data has been reset and re-seeded", "reset_at": datetime.now(timezone.utc).isoformat()}


@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 50, entity: Optional[str] = None):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    from utils import administrative_reporting as reporting
    from utils.employee_integrity import tenant_of
    db=get_db()
    result=await reporting.audit_feed(db,user,limit=limit,sources=['audit_log'])
    rows=result['items']
    if entity:
        wanted=reporting.opaque(str(tenant_of(user))+':'+entity,'target:')
        rows=[row for row in rows if row.get('target_reference')==wanted]
    await reporting.access_audit(db,user,'report.audit.viewed',source='audit_log')
    return [{**row,'action':row['event'],'performed_by':row['actor_id'],'entity':row['target_reference']} for row in rows]
