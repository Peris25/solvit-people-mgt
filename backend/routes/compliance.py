from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

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
    db = get_db()
    now = datetime.now(timezone.utc)
    current_month = now.strftime("%Y-%m")

    statuses = await db.statutory_compliance.find(
        {"tenant_id": "solvit", "period": {"$regex": f"^{now.year}"}}
    ).sort("period", -1).to_list(24)

    return [fmt(s) for s in statuses]


@router.post("/statutory")
async def record_statutory_payment(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["finance", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **body,
        "recorded_by": user["id"],
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.statutory_compliance.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/paye-calculator")
async def calculate_paye(request: Request, gross_salary: float = 50000):
    user = await get_current_user(request)
    # Kenya PAYE bands (Income Tax Act Cap 470 — 2023 rates)
    paye = 0.0
    taxable = gross_salary

    # Personal relief: KES 2,400/month
    personal_relief = 2400.0

    bands = [
        (24000, 0.10),
        (8333, 0.25),
        (467667, 0.30),
        (float("inf"), 0.325),
    ]

    remaining = taxable
    for band_amount, rate in bands:
        if remaining <= 0:
            break
        taxable_in_band = min(remaining, band_amount)
        paye += taxable_in_band * rate
        remaining -= taxable_in_band

    paye = max(0, paye - personal_relief)

    # NSSF Tier 1 (Tier I: Lower Earnings Limit = 6,000, Upper = 18,000)
    nssf_tier1 = min(gross_salary, 6000) * 0.06
    nssf_tier2 = max(0, min(gross_salary - 6000, 12000)) * 0.06
    total_nssf = nssf_tier1 + nssf_tier2

    # SHA (Social Health Insurance Act 2023) — 2.75% of gross
    sha = gross_salary * 0.0275

    net_pay = gross_salary - paye - total_nssf - sha

    return {
        "gross_salary_kes": gross_salary,
        "paye_kes": round(paye, 2),
        "nssf_employee_kes": round(total_nssf, 2),
        "sha_kes": round(sha, 2),
        "total_deductions_kes": round(paye + total_nssf + sha, 2),
        "net_pay_kes": round(net_pay, 2),
        "personal_relief_applied": personal_relief
    }


@router.get("/nssf-rates")
async def get_nssf_rates(request: Request):
    user = await get_current_user(request)
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
