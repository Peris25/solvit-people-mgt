from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid
import re
from utils.legacy_security import module_access, audit
from utils.employee_integrity import tenant_of, integrity_write

router = APIRouter(prefix="/compliance", tags=["compliance"])


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/statutory")
async def get_statutory_status(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M19", write=request.method != "GET")
    db = get_db()
    now = datetime.now(timezone.utc)
    current_month = now.strftime("%Y-%m")

    statuses = await db.statutory_compliance.find(
        {"tenant_id": tenant_of(user), "period": {"$regex": f"^{now.year}"}}
    ).sort("period", -1).to_list(24)

    return [fmt(s) for s in statuses]


@router.post("/statutory")
async def record_statutory_payment(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["finance", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M19", write=request.method != "GET")
    db = get_db()
    body = await request.json()
    allowed = {"period", "obligation", "statutory_type", "type", "status", "amount_kes", "payment_date", "reference", "notes"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise HTTPException(422, "Invalid statutory register fields")
    if not re.fullmatch(r"\d{4}-\d{2}", str(body.get("period", ""))):
        raise HTTPException(422, "Period must be YYYY-MM")
    obligation = body.get("obligation") or body.get("statutory_type") or body.get("type")
    if obligation not in {"NSSF", "SHA", "PAYE"}:
        raise HTTPException(422, "Choose a documented statutory obligation")
    if body.get("status") not in {"Pending", "Paid", "Filed", "Completed"}:
        raise HTTPException(422, "Invalid statutory status")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **body,
        "recorded_by": user["id"],
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        if await db.statutory_compliance.find_one({"tenant_id": tenant_of(user), "period": body["period"], "obligation": obligation}):
            raise HTTPException(409, "This statutory period is already recorded")
        doc["obligation"] = obligation
        await audit(db, user, "compliance.payment.recorded", doc["id"])
        result = await db.statutory_compliance.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/paye-calculator")
async def calculate_paye(request: Request, gross_salary: float = 50000):
    user = await get_current_user(request)
    module_access(user, "M19")
    # Pull live rates from Masters Settings (Section 12 lookups + organisation rates).
    from routes.masters_settings import get_setting
    org = await get_setting("organisation") or {}
    paye_brackets = org.get("paye_brackets") or [
        {"min_kes": 0,      "max_kes": 24000,    "rate_pct": 10},
        {"min_kes": 24001,  "max_kes": 32333,    "rate_pct": 25},
        {"min_kes": 32334,  "max_kes": 500000,   "rate_pct": 30},
        {"min_kes": 500001, "max_kes": 800000,   "rate_pct": 32.5},
        {"min_kes": 800001, "max_kes": 99999999, "rate_pct": 35},
    ]
    nhif_rates = org.get("nhif_rates") or []
    nssf_employer_pct = float(org.get("nssf_employer_pct", 6.0))

    # PAYE: progressive across bracket widths
    personal_relief = 2400.0
    paye = 0.0
    remaining = gross_salary
    cumulative_min = 0
    for b in paye_brackets:
        bmin = float(b.get("min_kes", cumulative_min))
        bmax = float(b.get("max_kes", bmin))
        rate = float(b.get("rate_pct", 0)) / 100.0
        width = max(0.0, bmax - bmin + 1)
        taxable_in_band = max(0.0, min(remaining, width))
        if taxable_in_band <= 0:
            break
        paye += taxable_in_band * rate
        remaining -= taxable_in_band
        cumulative_min = bmax
    paye = max(0.0, paye - personal_relief)

    # NSSF (employee + employer share — show employee only here)
    nssf_tier1 = min(gross_salary, 6000) * 0.06
    nssf_tier2 = max(0, min(gross_salary - 6000, 12000)) * 0.06
    total_nssf = nssf_tier1 + nssf_tier2

    # NHIF (now SHIF/SHA) — table lookup if rates configured, else 2.75% fallback
    sha = 0.0
    if nhif_rates:
        for r in nhif_rates:
            if float(r.get("min_kes", 0)) <= gross_salary <= float(r.get("max_kes", 0)):
                sha = float(r.get("amount_kes", 0))
                break
        if sha == 0.0:
            sha = gross_salary * 0.0275
    else:
        sha = gross_salary * 0.0275

    net_pay = gross_salary - paye - total_nssf - sha

    return {
        "gross_salary_kes": gross_salary,
        "paye_kes": round(paye, 2),
        "nssf_employee_kes": round(total_nssf, 2),
        "nssf_employer_pct": nssf_employer_pct,
        "sha_kes": round(sha, 2),
        "total_deductions_kes": round(paye + total_nssf + sha, 2),
        "net_pay_kes": round(net_pay, 2),
        "personal_relief_applied": personal_relief,
        "config_source": "masters_settings.organisation",
    }


@router.get("/nssf-rates")
async def get_nssf_rates(request: Request):
    user = await get_current_user(request)
    module_access(user, "M19")
    return {
        "tier_1_lower_limit": 6000,
        "tier_1_upper_limit": 6000,
        "tier_1_rate": "6%",
        "tier_2_lower_limit": 6001,
        "tier_2_upper_limit": 18000,
        "tier_2_rate": "6%",
        "note": "NSSF Act 2013 — New tier rates"
    }


@router.get("/deadlines")
async def get_upcoming_deadlines(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["finance", "hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    module_access(user, "M19")
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    return {
        "nssf_sha_deadline": f"{year}-{month:02d}-15",
        "paye_deadline": f"{year}-{month:02d}-09",
        "nssf_sha_next": f"{next_year}-{next_month:02d}-15",
        "paye_next": f"{next_year}-{next_month:02d}-09",
        "annual_policy_audit": f"{year}-01-31",
        "note": "NSSF/SHA by 15th, PAYE by 9th of each month"
    }
