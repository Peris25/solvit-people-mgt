"""CSV export endpoints — Employees, Pay Bands, Budget Allocations.
Streams text/csv responses with appropriate filenames. Role-gated per access matrix.
"""
import io
import csv
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/exports", tags=["exports"])


def _csv_response(rows, filename: str) -> StreamingResponse:
    """Convert a list of dicts to CSV streaming response."""
    if not rows:
        rows = [{"info": "no data"}]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([buf.read()]), media_type="text/csv", headers=headers)


@router.get("/employees.csv")
async def export_employees(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ("hr_admin", "hr_manager", "executive", "it_admin"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    employees = await db.employees.find({"tenant_id": "solvit"}).sort("full_name", 1).to_list(1000)
    # Hide MD/ED Board-only records
    if user["role"] not in ("board", "it_admin"):
        employees = [e for e in employees if not e.get("board_only")]
    rows = [{
        "employee_id": e.get("id", ""),
        "full_name": e.get("full_name", ""),
        "work_email": e.get("work_email", ""),
        "role_title": e.get("role_title", ""),
        "department": e.get("department", ""),
        "role_level": e.get("role_level", ""),
        "employment_type": e.get("employment_type", ""),
        "lifecycle_state": e.get("lifecycle_state", ""),
        "current_salary_kes": e.get("current_salary_kes", ""),
        "start_date": e.get("start_date", ""),
        "probation_end_date": e.get("probation_end_date", ""),
        "line_manager_id": e.get("line_manager_id", ""),
        "national_id_number": e.get("national_id_number", ""),
        "kra_pin": e.get("kra_pin", ""),
        "nssf_number": e.get("nssf_number", ""),
        "sha_number": e.get("sha_number", ""),
    } for e in employees]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(rows, f"employees_{stamp}.csv")


@router.get("/pay-bands.csv")
async def export_pay_bands(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ("hr_admin", "hr_manager", "finance", "executive", "it_admin"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    bands = await db.pay_bands.find({"tenant_id": "solvit"}).sort("band", 1).to_list(50)
    rows = [{
        "band": b.get("band", ""),
        "min_kes": b.get("min_kes", 0),
        "mid_kes": b.get("mid_kes", 0),
        "max_kes": b.get("max_kes", 0),
        "roles": ", ".join(b.get("roles", [])),
        "note": b.get("note", ""),
    } for b in bands]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(rows, f"pay_bands_{stamp}.csv")


@router.get("/budget-allocations.csv")
async def export_budget_allocations(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ("hr_admin", "hr_manager", "finance", "it_admin"):
        raise HTTPException(status_code=403, detail="No access")
    db = get_db()
    allocs = await db.budget_allocations.find({"tenant_id": "solvit"}).sort("created_at", -1).to_list(500)
    rows = [{
        "initiative_name": a.get("initiative_name", ""),
        "budget_cycle": a.get("budget_cycle", ""),
        "linked_module": a.get("linked_module", ""),
        "amount_kes": a.get("amount_kes", 0),
        "spent_amount_kes": a.get("spent_amount_kes", ""),
        "variance_kes": a.get("variance_kes", ""),
        "status": a.get("status", ""),
        "created_by": a.get("created_by_name", ""),
        "created_at": a.get("created_at", ""),
        "approved_at": a.get("approved_at", ""),
        "spent_at": a.get("spent_at", ""),
        "notes": a.get("notes", ""),
    } for a in allocs]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return _csv_response(rows, f"budget_allocations_{stamp}.csv")
