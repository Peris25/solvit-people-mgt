from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.employee_access import authorize_employee
from utils.employee_integrity import employee_key, find_employee, tenant_of, tenant_query, integrity_write, is_direct_report, user_employee_aliases
from utils.legacy_security import module_access, audit, projection, HR
from utils.solver_access import authorize_solver, solver_access, own_solver, solver_aliases, solver_key
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
    module_access(user, "M11")
    if user.get("role") == "solver":
        raise HTTPException(403, "Use your own Solver awards")
    rows = await db.recognitions.find(tenant_query(tenant_of(user))).sort("created_at", -1).to_list(None)
    out = []
    for row in rows:
        if recognition_type and row.get("recognition_type") != recognition_type:
            continue
        target = await find_employee(db, row.get("employee_id") or row.get("nominee_id"), tenant_of(user))
        own = target and employee_key(target) in user_employee_aliases(user)
        team = target and user.get("role") == "line_manager" and is_direct_report(target, user)
        # Pending nominations are visible only to HR and the actual nominator.
        if user["role"] not in HR and not (row.get("nominator_id") == user["id"] or (row.get("status") == "Approved" and (own or team))):
            continue
        fields = {"recognition_type", "nominee_id", "nominee_name", "employee_id", "values_demonstrated", "specific_behaviour", "impact", "status", "created_at", "nominator_name", "message"}
        if user["role"] in HR: fields |= {"nominator_id"}
        out.append(projection(row, fields))
    return out[:200]


@router.post("/peer-nomination")
async def create_peer_nomination(nom: PeerNomination, request: Request):
    user = await get_current_user(request)
    db = get_db()
    module_access(user, "M11", write=True)
    sender = await find_employee(db, user.get("employee_id"), tenant_of(user))
    if not sender or sender.get("lifecycle_state") not in {"Active", "Probation", "Onboarding", "On Leave", "On_Leave"}:
        raise HTTPException(403, "An eligible linked employee is required")
    # Peer nominations intentionally target other staff; sender identity is server-owned.
    target = await find_employee(db, nom.nominee_id, tenant_of(user))
    if not target or target.get("lifecycle_state") not in {"Active", "Probation"} or target.get("board_only"):
        raise HTTPException(404, "Eligible nominee not found")
    nom = nom.model_copy(update={"nominee_id": employee_key(target), "nominee_name": target.get("full_name", "")})
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "recognition_type": "Peer",
        **nom.model_dump(),
        "nominator_id": user["id"],
        "nominator_name": user.get("full_name") or user.get("email", ""),
        "status": "Pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        duplicate = {"$and": [tenant_query(tenant_of(user)), {"nominator_id": user["id"], "nominee_id": doc["nominee_id"], "recognition_type": doc["recognition_type"], "specific_behaviour": doc.get("specific_behaviour"), "impact": doc.get("impact")} ]}
        if await db.recognitions.find_one(duplicate):
            raise HTTPException(409, "This recognition is already recorded")
        await audit(db, user, "recognition.created", doc["id"])
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
    return await record_manager_recognition(db, user, await request.json())


async def record_manager_recognition(db, user, body):
    module_access(user, "M11", write=True)
    allowed = {"nominee_id", "employee_id", "nominee_name", "specific_behaviour", "behaviour", "impact", "values_demonstrated", "recognition_type"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise HTTPException(422, "Only non-monetary recognition fields are accepted")
    target = await authorize_employee(db, user, body.get("nominee_id") or body.get("employee_id"), "M11", write=True)
    body.pop("recognition_type", None)
    body["nominee_name"] = target.get("full_name", "")
    body["nominee_id"] = employee_key(target)
    body["employee_id"] = employee_key(target)
    body.pop("tenant_id", None)
    body.pop("id", None)
    body.pop("_id", None)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "recognition_type": "Manager",
        **body,
        "message": body.get("specific_behaviour") or body.get("behaviour", ""),
        "nominator_id": user["id"],
        "nominator_name": user.get("full_name") or user.get("email", ""),
        "status": "Approved",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        duplicate = {"$and": [tenant_query(tenant_of(user)), {"nominator_id": user["id"], "nominee_id": doc["nominee_id"], "recognition_type": doc["recognition_type"], "specific_behaviour": doc.get("specific_behaviour"), "impact": doc.get("impact")} ]}
        if await db.recognitions.find_one(duplicate):
            raise HTTPException(409, "This recognition is already recorded")
        await audit(db, user, "recognition.created", doc["id"])
        result = await db.recognitions.insert_one(doc)
        await db.notifications.insert_one({"_id": "recognition:" + doc["id"], "id": "recognition:" + doc["id"], "tenant_id": tenant_of(user),
            "recipient_id": employee_key(target), "category": "Recognition", "title": "Recognition recorded",
            "message": "View your authorized recognition record.", "data": {"employee_id": employee_key(target)},
            "is_read": False, "created_at": doc["created_at"]})
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
    module_access(user, "M11")
    entry = await solver_access(db, user)
    query = tenant_query(tenant_of(user))
    if entry.get("scope") == "aggregate":
        raise HTTPException(403, "No access to individual awards")
    if user.get("role") == "solver":
        subject = await own_solver(db, user)
        query = {"$and": [query, {"solver_id": {"$in": solver_aliases(subject)}}, {"status": {"$in": ["Approved", "Paid", "Released"]}}]}
    awards = await db.solver_awards.find(query).sort("created_at", -1).to_list(50)
    fields = {"solver_id", "solver_name", "award_tier", "award_amount_kes", "quarter", "period", "status", "created_at"}
    return [projection(row, fields) for row in awards]


@router.post("/solver-awards")
async def create_solver_award(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    body = await request.json()
    module_access(user, "M11", write=True)
    if not isinstance(body, dict) or set(body) - {"solver_id", "solver_name", "award_tier", "quarter", "period", "rationale"}:
        raise HTTPException(422, "Invalid Solver award fields")
    target = await authorize_solver(db, user, body.get("solver_id"), write=True)
    if not body.get("quarter") and not body.get("period"):
        raise HTTPException(422, "Award period is required")
    body["solver_id"] = solver_key(target)
    body["solver_name"] = target.get("full_name", "")
    award_amounts = {"Top Solver": 3000, "Runner-Up": 1500}
    tier = body.get("award_tier", "Top Solver")
    if tier not in award_amounts:
        raise HTTPException(422, "Invalid award tier")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **body,
        "award_tier": tier,
        "award_amount_kes": award_amounts.get(tier, 1500),
        "status": "Pending_Finance",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        if await db.solver_awards.find_one({"$and": [tenant_query(tenant_of(user)), {"solver_id": {"$in": solver_aliases(target)}, "quarter": body.get("quarter"), "period": body.get("period")}]}):
            raise HTTPException(409, "An award for this Solver and period already exists")
        await audit(db, user, "recognition.solver_award.proposed", doc["id"])
        result = await db.solver_awards.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/long-service")
async def get_long_service_milestones(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    module_access(user, "M11")
    employees = await db.employees.find({"tenant_id": tenant_of(user), "lifecycle_state": "Active"}).to_list(200)
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
