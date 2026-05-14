from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/solvers", tags=["solvers"])

SOLVER_STATES = ["Registering", "Active", "Suspended", "Inactive", "Deactivated"]
VEHICLE_CATEGORIES = ["Saloon", "SUV", "Pick-Up", "Van", "Truck", "Motorcycle"]
NAIROBI_ZONES = ["Zone 1: CBD", "Zone 2: Westlands-Kileleshwa", "Zone 3: Karen-Langata",
                  "Zone 4: Eastlands", "Zone 5: Thika Rd Corridor", "Zone 6: South B-South C"]


class SolverCreate(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mpesa_number: Optional[str] = None
    payment_method: str = "MPesa"
    vehicle_categories: Optional[List[str]] = []
    zones_covered: Optional[List[str]] = []
    driving_licence_type: Optional[str] = None
    driving_licence_number: Optional[str] = None
    driving_licence_expiry: Optional[str] = None


class SolverUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mpesa_number: Optional[str] = None
    payment_method: Optional[str] = None
    vehicle_categories: Optional[List[str]] = None
    zones_covered: Optional[List[str]] = None
    lifecycle_state: Optional[str] = None
    accuracy_score: Optional[float] = None
    reliability_score: Optional[float] = None
    timeliness_score: Optional[float] = None
    client_rating_average: Optional[float] = None
    performance_tier: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_solvers(request: Request, lifecycle_state: Optional[str] = None, search: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if lifecycle_state:
        query["lifecycle_state"] = lifecycle_state
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"phone_number": {"$regex": search, "$options": "i"}}
        ]
    if user["role"] == "solver":
        query["phone_number"] = user.get("phone_number", "")
    elif user["role"] == "employee":
        return []
    solvers = await db.solvers.find(query).sort("full_name", 1).to_list(500)
    return [fmt(s) for s in solvers]


@router.get("/stats")
async def get_solver_stats(request: Request):
    user = await get_current_user(request)
    db = get_db()
    pipeline = [{"$match": {"tenant_id": "solvit"}}, {"$group": {"_id": "$lifecycle_state", "count": {"$sum": 1}}}]
    results = await db.solvers.aggregate(pipeline).to_list(10)
    stats = {r["_id"]: r["count"] for r in results}
    return {"by_state": stats, "total": sum(stats.values()), "active": stats.get("Active", 0)}


@router.post("")
async def create_solver(solver: SolverCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    existing = await db.solvers.find_one({"phone_number": solver.phone_number, "tenant_id": "solvit"})
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    solver_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **solver.model_dump(),
        "lifecycle_state": "Registering",
        "accuracy_score": None,
        "reliability_score": None,
        "timeliness_score": None,
        "client_rating_average": None,
        "performance_tier": None,
        "solver_agreement_signed": False,
        "solver_agreement_date": None,
        "activation_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.solvers.insert_one(solver_doc)
    solver_doc["_id"] = str(result.inserted_id)
    solver_doc["id"] = str(result.inserted_id)

    from automation.engine import automation_engine
    await automation_engine.fire_event("solver_registered", {"solver_id": solver_doc["id"]})
    return solver_doc


@router.get("/{solver_id}")
async def get_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        s = await db.solvers.find_one({"_id": ObjectId(solver_id)})
    except Exception:
        s = await db.solvers.find_one({"id": solver_id})
    if not s:
        raise HTTPException(status_code=404, detail="Solver not found")
    return fmt(s)


@router.put("/{solver_id}")
async def update_solver(solver_id: str, upd: SolverUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    update_data = {k: v for k, v in upd.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.solvers.find_one_and_update(
            {"_id": ObjectId(solver_id)}, {"$set": update_data}, return_document=True
        )
    except Exception:
        result = await db.solvers.find_one_and_update(
            {"id": solver_id}, {"$set": update_data}, return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Solver not found")
    # Email the solver if a meaningful status/tier transition just happened
    try:
        from utils.email_triggers import fire_and_forget
        sol_email = result.get("email") or result.get("work_email")
        if sol_email:
            new_state = update_data.get("lifecycle_state")
            new_tier = update_data.get("performance_tier")
            ctx = {"solver_name": result.get("full_name")}
            if new_state == "Suspended":
                await fire_and_forget(db, "solver.suspension", to_override=sol_email, extra=ctx)
            elif new_state == "Active":
                await fire_and_forget(db, "solver.reactivation", to_override=sol_email, extra=ctx)
            if new_tier in ("Top", "Premium"):
                await fire_and_forget(db, "solver.tier_upgrade", to_override=sol_email, extra={**ctx, "new_tier": new_tier})
            elif new_tier in ("Bottom", "Probation"):
                await fire_and_forget(db, "solver.tier_downgrade", to_override=sol_email, extra={**ctx, "new_tier": new_tier})
    except Exception:
        pass
    return fmt(result)


@router.post("/{solver_id}/activate")
async def activate_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    try:
        result = await db.solvers.find_one_and_update(
            {"_id": ObjectId(solver_id)},
            {"$set": {"lifecycle_state": "Active", "activation_date": datetime.now(timezone.utc).isoformat()[:10], "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
    except Exception:
        result = await db.solvers.find_one_and_update(
            {"id": solver_id},
            {"$set": {"lifecycle_state": "Active", "activation_date": datetime.now(timezone.utc).isoformat()[:10], "updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=True
        )
    if not result:
        raise HTTPException(status_code=404, detail="Solver not found")
    # Email the solver activation confirmation (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        sol_email = result.get("email") or result.get("work_email")
        if sol_email:
            await fire_and_forget(db, "solver.activation", to_override=sol_email, extra={
                "solver_name": result.get("full_name"),
                "activation_date": result.get("activation_date"),
            })
    except Exception:
        pass
    return fmt(result)



@router.post("/{solver_id}/client-rating")
async def submit_client_rating(solver_id: str, request: Request):
    """Real-time client rating submission for a completed job (Fix 1).
    Body: { job_id, accuracy (0-100), timeliness (0-100), overall (0-100), client_id, comment }
    Writes the rating and recomputes the solver's 30-day / 90-day / all-time averages.
    """
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    for f in ("accuracy", "timeliness", "overall"):
        v = body.get(f)
        if v is None or not (0 <= float(v) <= 100):
            raise HTTPException(status_code=400, detail=f"{f} must be a number 0–100")
    rating_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "solver_id": solver_id,
        "job_id": body.get("job_id"),
        "client_id": body.get("client_id"),
        "accuracy": float(body["accuracy"]),
        "timeliness": float(body["timeliness"]),
        "overall": float(body["overall"]),
        "comment": body.get("comment", ""),
        "submitted_by": user["id"],
        "voided": False,
        "void_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.solver_ratings.insert_one(rating_doc)
    await _recompute_solver_averages(db, solver_id)
    return {"submitted": True, "rating_id": rating_doc["id"]}


async def _recompute_solver_averages(db, solver_id: str):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()
    all_ratings = await db.solver_ratings.find({"solver_id": solver_id, "voided": False}).to_list(1000)

    def _avg(ratings, field):
        if not ratings: return None
        return round(sum(r[field] for r in ratings) / len(ratings), 1)

    r_30 = [r for r in all_ratings if r["created_at"] >= cutoff_30]
    r_90 = [r for r in all_ratings if r["created_at"] >= cutoff_90]
    latest = max(all_ratings, key=lambda r: r["created_at"]) if all_ratings else None
    update = {
        "latest_client_rating": latest["overall"] if latest else None,
        "latest_rating_at": latest["created_at"] if latest else None,
        "client_rating_30d": _avg(r_30, "overall"),
        "client_rating_90d": _avg(r_90, "overall"),
        "accuracy_score": _avg(all_ratings, "accuracy"),
        "timeliness_score": _avg(all_ratings, "timeliness"),
        "client_rating_average": _avg(all_ratings, "overall"),
        "updated_at": now.isoformat(),
    }
    try:
        await db.solvers.update_one({"_id": ObjectId(solver_id)}, {"$set": update})
    except Exception:
        await db.solvers.update_one({"id": solver_id}, {"$set": update})


@router.get("/{solver_id}/ratings")
async def list_solver_ratings(solver_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ("hr_admin", "hr_manager", "it_admin", "line_manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    ratings = await db.solver_ratings.find({"solver_id": solver_id}).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in ratings]


@router.post("/ratings/{rating_id}/void")
async def void_rating(rating_id: str, request: Request):
    """IT Admin only — void a rating with a mandatory reason (Fix 1)."""
    user = await get_current_user(request)
    if user["role"] != "it_admin":
        raise HTTPException(status_code=403, detail="Only IT Admin can void ratings")
    body = await request.json()
    reason = (body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="A void reason of ≥5 characters is required")
    db = get_db()
    rating = await db.solver_ratings.find_one_and_update(
        {"id": rating_id},
        {"$set": {"voided": True, "void_reason": reason, "voided_by": user["id"], "voided_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True
    )
    if not rating:
        raise HTTPException(status_code=404, detail="Rating not found")
    await _recompute_solver_averages(db, rating["solver_id"])
    return {"voided": True}
