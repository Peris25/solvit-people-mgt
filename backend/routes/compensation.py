from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid
from utils.access_matrix import get_module_access
from utils.employee_integrity import tenant_of, tenant_query


def compensation_access(user, write=False):
    entry=get_module_access("M10",user.get("role"))
    if not entry or entry.get("level") not in ({"Manage","Full"} if write else {"Read","Manage","Full"}):
        raise HTTPException(403,"Compensation permission is required")

router = APIRouter(prefix="/compensation", tags=["compensation"])


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/pay-bands")
async def get_pay_bands(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=False)
    if user["role"] not in ["hr_admin", "hr_manager", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    bands = await db.pay_bands.find(tenant_query(tenant_of(user))).sort("band", 1).to_list(20)
    return [fmt(b) for b in bands]


@router.put("/pay-bands/{band_id}")
async def update_pay_band(band_id: str, request: Request):
    """HR Admin (or HR Manager) can edit pay band min/mid/max and roles."""
    user = await get_current_user(request)
    compensation_access(user,write=True)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can edit pay bands")
    db = get_db()
    from utils.employee_integrity import integrity_write
    from utils.employee_access import find_linked_record
    from utils.benefits import audit
    import math
    body=await request.json()
    allowed={"min_kes","mid_kes","max_kes","roles","note"}
    if not isinstance(body,dict) or not body or set(body)-allowed:
        raise HTTPException(422,"Invalid pay-band fields")
    async with integrity_write(db):
        current=await find_linked_record(db.pay_bands,band_id,user)
        combined={**current,**body}
        for key in ("min_kes","mid_kes","max_kes"):
            value=combined.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or value<0: raise HTTPException(422,"Invalid pay-band range")
        if not combined["min_kes"]<=combined["mid_kes"]<=combined["max_kes"]: raise HTTPException(422,"Pay-band range must be ordered")
        if "roles" in body and (not isinstance(body["roles"],list) or any(not isinstance(role,str) for role in body["roles"])): raise HTTPException(422,"Invalid roles")
        if "note" in body and not isinstance(body["note"],str): raise HTTPException(422,"Invalid pay-band note")
        update={**body,"updated_at":datetime.now(timezone.utc).isoformat(),"updated_by":user["id"]}
        await audit(db,user,"compensation.pay_band.updated",current.get("id") or str(current["_id"]),before={key:current.get(key) for key in body},after=body)
        await db.pay_bands.update_one({"_id":current["_id"]},{"$set":update})
    return fmt({**current,**update})


@router.get("/pay-bands/alerts")
async def get_pay_band_alerts(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=False)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    alerts = await db.pay_band_alerts.find({"$and":[tenant_query(tenant_of(user)),{"status":"Active"}]}).to_list(50)
    return [fmt(a) for a in alerts]


@router.get("/salary-review")
async def get_salary_reviews(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=False)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    reviews = await db.salary_reviews.find(tenant_query(tenant_of(user))).sort("created_at", -1).to_list(100)
    if user.get("role")=="finance":
        allowed={"id","employee_id","old_salary_kes","new_salary_kes","increment_pct","effective_date","rationale","reason","status","created_at"}
        return [{"id":str(row.get("id") or row["_id"]),**{key:value for key,value in row.items() if key in allowed}} for row in reviews]
    return [fmt(r) for r in reviews]


@router.post("/salary-review")
async def create_salary_review(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=True)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    from utils.employee_integrity import integrity_write, tenant_of, employee_key
    from utils.employee_access import authorize_employee
    from utils.benefits import privileged, audit, text, day
    import math
    privileged(user,write=True)
    body = await request.json()
    allowed = {"employee_id","old_salary_kes","new_salary_kes","increment_pct","effective_date","rationale","reason"}
    if not isinstance(body,dict) or set(body)-allowed:
        raise HTTPException(422,"Unknown salary review fields")
    async with integrity_write(db):
        employee = await authorize_employee(db,user,body.get("employee_id"),"M01",write=True)
        for key in ("old_salary_kes","new_salary_kes","increment_pct"):
            if key in body and (type(body[key]) not in (int,float) or not math.isfinite(body[key]) or body[key]<0):
                raise HTTPException(422,"Invalid salary review amount")
        if "new_salary_kes" not in body: raise HTTPException(422,"Proposed salary is required")
        if body.get("effective_date"): day(body["effective_date"])
        doc={**body,"id":str(uuid.uuid4()),"tenant_id":tenant_of(user),"employee_id":employee_key(employee),
             "status":"Pending_Finance_Approval","rationale":text(body.get("rationale") or body.get("reason"),"salary review rationale"),
             "created_by":user["id"],"created_at":datetime.now(timezone.utc).isoformat()}
        await audit(db,user,"compensation.salary_review.proposed",doc["id"],employee_id=employee_key(employee))
        await db.salary_reviews.insert_one(doc)
    # Pending proposals are not approved outcomes and must never be emailed to staff.
    # Existing Finance approval/release policy must be confirmed before outcome delivery.
    return {key:value for key,value in doc.items() if key!="_id"}


@router.get("/bonus/calculator")
async def get_bonus_calculator(request: Request, tier: str = "Tier1"):
    user = await get_current_user(request)
    compensation_access(user,write=False)
    if user["role"] not in ["hr_admin", "hr_manager", "finance"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    # Get active employees with performance scores
    employees = await db.employees.find({"$and":[tenant_query(tenant_of(user)),{
        "lifecycle_state":"Active","last_performance_score":{"$ne":None}}]}).to_list(100)

    tier_rates = {
        "Tier1": {"Exceeded": 0.15, "Met": 0.08, "Below": 0.0},
        "Tier2": {"Exceeded": 0.20, "Met": 0.12, "Below": 0.0}
    }
    rates = tier_rates.get(tier, tier_rates["Tier1"])

    bonuses = []
    for emp in employees:
        score = emp.get("last_performance_score", 2.0)
        if score <= 1.49:
            rating = "Exceeded"
        elif score <= 1.99:
            rating = "Met"
        else:
            rating = "Below"
        salary = emp.get("current_salary_kes", 0) or 0
        rate = rates.get(rating, 0)
        bonus_amount = int(salary * rate)
        bonuses.append({
            "employee_id": str(emp.get("id", str(emp["_id"]))),
            "name": emp.get("full_name"),
            "role": emp.get("role_title"),
            "department": emp.get("department"),
            "salary": salary,
            "performance_score": score,
            "rating": rating,
            "bonus_rate": rate,
            "bonus_amount_kes": bonus_amount,
            "tier": tier
        })
    if user.get("role")=="finance":
        for bonus in bonuses: bonus.pop("performance_score",None)
    total = sum(b["bonus_amount_kes"] for b in bonuses)
    return {"tier": tier, "employees": bonuses, "total_bonus_kes": total}


@router.get("/gp-gate")
async def get_gp_gate(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=False)
    if user["role"] not in ["hr_admin", "finance", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    gate = await db.gp_gate.find_one(tenant_query(tenant_of(user)), sort=[("created_at", -1)])
    if not gate:
        return {"gate_open": False, "message": "No GP gate decision recorded"}
    return fmt(gate)


@router.post("/gp-gate")
async def set_gp_gate(request: Request):
    user = await get_current_user(request)
    compensation_access(user,write=True)
    if user["role"] not in ["finance"]:
        raise HTTPException(status_code=403, detail="Only Finance can update GP gate")
    db = get_db()
    from utils.employee_integrity import integrity_write
    from utils.benefits import audit
    body = await request.json()
    if not isinstance(body,dict) or set(body)&{"id","_id","tenant_id","confirmed_by","created_at"}:
        raise HTTPException(422,"Invalid Finance gate fields")
    if "gate_open" in body and not isinstance(body["gate_open"],bool):
        raise HTTPException(422,"Gate confirmation must be boolean")
    doc={**body,"id":str(uuid.uuid4()),"tenant_id":tenant_of(user),"confirmed_by":user["id"],"created_at":datetime.now(timezone.utc).isoformat()}
    async with integrity_write(db):
        await audit(db,user,"compensation.gate.recorded",doc["id"])
        await db.gp_gate.insert_one(doc)
    return {key:value for key,value in doc.items() if key!="_id"}
