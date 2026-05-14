from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/recognition", tags=["recognition"])


class PeerNomination(BaseModel):
    nominee_id: str
    nominee_name: str
    values_demonstrated: List[str]
    specific_behaviour: str
    impact: str


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_recognitions(request: Request, recognition_type: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if recognition_type:
        query["recognition_type"] = recognition_type
    recs = await db.recognitions.find(query).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in recs]


@router.post("/peer-nomination")
async def create_peer_nomination(nom: PeerNomination, request: Request):
    user = await get_current_user(request)
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "recognition_type": "Peer",
        **nom.model_dump(),
        "nominator_id": user["id"],
        "nominator_name": user.get("full_name", user["email"]),
        "status": "Pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.recognitions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the nominee (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        values_str = ", ".join(nom.values_demonstrated or [])
        await fire_and_forget(db, "recognition.peer", employee_id=nom.nominee_id, extra={
            # primary keys
            "nominator_name": doc["nominator_name"],
            "values": values_str,
            "behaviour": nom.specific_behaviour,
            "impact": nom.impact,
            # back-compat aliases used by the existing default template
            "from_name": doc["nominator_name"],
            "message": nom.specific_behaviour,
        })
    except Exception:
        pass
    return doc


@router.post("/manager")
async def create_manager_recognition(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "recognition_type": "Manager",
        **body,
        "nominator_id": user["id"],
        "nominator_name": user.get("full_name", user["email"]),
        "status": "Approved",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.recognitions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Email the recipient (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        recipient_id = body.get("nominee_id") or body.get("employee_id")
        if recipient_id:
            behaviour_text = body.get("specific_behaviour") or body.get("behaviour", "")
            await fire_and_forget(db, "recognition.manager", employee_id=recipient_id, extra={
                "manager_name": doc["nominator_name"],
                "behaviour": behaviour_text,
                "impact": body.get("impact", ""),
                # back-compat alias used by the existing default template
                "message": behaviour_text,
                "from_name": doc["nominator_name"],
            })
    except Exception:
        pass
    return doc


@router.get("/solver-awards")
async def list_solver_awards(request: Request):
    user = await get_current_user(request)
    db = get_db()
    awards = await db.solver_awards.find({"tenant_id": "solvit"}).sort("created_at", -1).to_list(50)
    return [fmt(a) for a in awards]


@router.post("/solver-awards")
async def create_solver_award(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    award_amounts = {"Top Solver": 3000, "Runner-Up": 1500}
    tier = body.get("award_tier", "Top Solver")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **body,
        "award_tier": tier,
        "award_amount_kes": award_amounts.get(tier, 1500),
        "status": "Pending_Finance",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.solver_awards.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/long-service")
async def get_long_service_milestones(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    employees = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}).to_list(200)
    milestones = []
    now = datetime.now(timezone.utc)
    for emp in employees:
        start_date = emp.get("start_date")
        if not start_date:
            continue
        try:
            tenure_years = (now - datetime.fromisoformat(start_date)).days / 365.25
            for milestone in [2, 3, 5, 7, 10]:
                if abs(tenure_years - milestone) < 0.1:
                    milestones.append({
                        "employee_id": str(emp.get("id", str(emp["_id"]))),
                        "name": emp.get("full_name"),
                        "role": emp.get("role_title"),
                        "department": emp.get("department"),
                        "tenure_years": round(tenure_years, 1),
                        "milestone": milestone,
                        "start_date": start_date
                    })
        except Exception:
            pass
    return milestones
