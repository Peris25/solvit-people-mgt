from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid
import re
import math
from utils.employee_integrity import tenant_query, tenant_of, integrity_write
from utils.solver_access import (solver_access, authorize_solver, find_solver, own_solver, solver_view,
                                 solver_key, solver_aliases, manager_fields, solver_identity_write)
from utils.solver_access import audit_solver, HR_ROLES

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


@router.get("")
async def list_solvers(request: Request, lifecycle_state: Optional[str] = None, search: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    entry = await solver_access(db, user)
    if entry.get("scope") == "aggregate":
        return []
    query = tenant_query(tenant_of(user))
    if entry.get("scope") == "own_record":
        own = await own_solver(db, user)
        query = {"$and": [query, {"_id": own["_id"]}]}
    if lifecycle_state:
        query = {"$and": [query, {"lifecycle_state": lifecycle_state}]}
    if search:
        query = {"$and": [query, {"$or": [
            {"full_name": {"$regex": re.escape(search), "$options": "i"}},
            {"phone_number": {"$regex": re.escape(search), "$options": "i"}}]}]}
    records = await db.solvers.find(query).sort("full_name", 1).to_list(500)
    for record in records:
        await find_solver(db, solver_key(record), user)
    if user.get("role") in HR_ROLES:
        await audit_solver(db, user, "solver.private_list.view", records)
    return [solver_view(record, user) for record in records]


@router.get("/stats")
async def get_solver_stats(request: Request):
    user = await get_current_user(request)
    db = get_db()
    entry = await solver_access(db, user)
    query = tenant_query(tenant_of(user))
    if entry.get("scope") == "own_record":
        own = await own_solver(db, user)
        query = {"$and": [query, {"_id": own["_id"]}]}
    records = await db.solvers.find(query, {"lifecycle_state": 1}).to_list(None)
    stats = {}
    for record in records:
        state = record.get("lifecycle_state") or "Unknown"
        stats[state] = stats.get(state, 0) + 1
    return {"by_state": stats, "total": sum(stats.values()), "active": stats.get("Active", 0),
            "can_manage": entry.get("level") in ("Full", "Manage") and entry.get("scope") not in ("own_record", "aggregate")}


@router.post("")
async def create_solver(solver: SolverCreate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    await solver_access(db, user, write=True)
    supplied = solver.model_dump(exclude_none=True)
    manager_fields(user, supplied)
    solver_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **supplied,
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
    async with integrity_write(db):
        changes = await solver_identity_write(db, supplied, user)
        solver_doc.update(changes)
        result = await db.solvers.insert_one(solver_doc)
        solver_doc["_id"] = result.inserted_id
    await audit_solver(db, user, "solver.created", [solver_doc], supplied)
    from automation.engine import automation_engine
    await automation_engine.fire_event("solver_registered", {"solver_id": str(solver_doc["_id"]), "tenant_id": tenant_of(user)})
    return solver_view(solver_doc, user)


@router.get("/{solver_id}")
async def get_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id)
    if user.get("role") in HR_ROLES:
        await audit_solver(db, user, "solver.private_record.view", [record])
    return solver_view(record, user)


@router.put("/{solver_id}")
async def update_solver(solver_id: str, upd: SolverUpdate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    supplied = upd.model_dump(exclude_none=True)
    await solver_access(db, user, write=True)
    manager_fields(user, supplied)
    if supplied.get("lifecycle_state") and supplied["lifecycle_state"] not in SOLVER_STATES:
        raise HTTPException(422, "Invalid Solver lifecycle state")
    async with integrity_write(db):
        original = await authorize_solver(db, user, solver_id, write=True)
        update_data = await solver_identity_write(db, supplied, user, original)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.solvers.find_one_and_update(
            {"$and": [tenant_query(tenant_of(user)), {"_id": original["_id"]}]},
            {"$set": update_data}, return_document=True)
    if not result:
        raise HTTPException(404, "Solver not found")
    await audit_solver(db, user, "solver.updated", [result], update_data)
    # Email the solver if a meaningful status/tier transition just happened
    try:
        from utils.email_triggers import fire_and_forget
        sol_email = result.get("email") or result.get("work_email")
        if sol_email:
            new_state = update_data.get("lifecycle_state")
            new_tier = update_data.get("performance_tier")
            solver_name = result.get("full_name")
            if new_state == "Suspended":
                await fire_and_forget(db, "solver.suspension", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "reason": update_data.get("suspension_reason") or "Performance review by Solver Manager",
                })
            elif new_state == "Active":
                await fire_and_forget(db, "solver.reactivation", to_override=sol_email, extra={
                    "solver_name": solver_name,
                })
            if new_tier in ("Top", "Premium"):
                await fire_and_forget(db, "solver.tier_upgrade", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "new_tier": new_tier,
                })
            elif new_tier in ("Bottom", "Probation"):
                await fire_and_forget(db, "solver.tier_downgrade", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "new_tier": new_tier,
                })
    except Exception:
        pass
    return solver_view(result, user)


@router.post("/{solver_id}/activate")
async def activate_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        original = await authorize_solver(db, user, solver_id, write=True)
        result = await db.solvers.find_one_and_update(
            {"$and": [tenant_query(tenant_of(user)), {"_id": original["_id"]}]},
            {"$set": {"lifecycle_state": "Active", "activation_date": datetime.now(timezone.utc).isoformat()[:10],
                      "updated_at": datetime.now(timezone.utc).isoformat()}}, return_document=True)
    if not result:
        raise HTTPException(404, "Solver not found")
    await audit_solver(db, user, "solver.activated", [result], ["lifecycle_state", "activation_date"])
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
    return solver_view(result, user)



@router.post("/{solver_id}/client-rating")
async def submit_client_rating(solver_id: str, request: Request):
    """Real-time client rating submission for a completed job (Fix 1).
    Body: { job_id, accuracy (0-100), timeliness (0-100), overall (0-100), client_id, comment }
    Writes the rating and recomputes the solver's 30-day / 90-day / all-time averages.
    """
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id, write=True)
    body = await request.json()
    for f in ("accuracy", "timeliness", "overall"):
        try:
            v = float(body.get(f))
        except (TypeError, ValueError):
            raise HTTPException(400, f"{f} must be a number 0-100")
        if not math.isfinite(v) or not (0 <= v <= 100):
            raise HTTPException(status_code=400, detail=f"{f} must be a number 0â€“100")
    rating_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "solver_id": solver_key(record),
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
    async with integrity_write(db):
        await authorize_solver(db, user, solver_id, write=True)
        await db.solver_ratings.insert_one(rating_doc)
        await _recompute_solver_averages(db, solver_key(record), user)
    await audit_solver(db, user, "solver.rating.created", [record], ["accuracy", "timeliness", "overall"])
    return {"submitted": True, "rating_id": rating_doc["id"]}


async def _recompute_solver_averages(db, solver_id: str, user):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()
    record = await find_solver(db, solver_id, user)
    all_ratings = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)),
        {"solver_id": {"$in": solver_aliases(record)}, "voided": False}]}).to_list(1000)

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
    await db.solvers.update_one({"$and": [tenant_query(tenant_of(user)), {"_id": record["_id"]}]}, {"$set": update})


@router.get("/{solver_id}/ratings")
async def list_solver_ratings(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    if user.get("role") == "it_admin":
        record = await find_solver(db, solver_id, user)  # Existing rating-audit exception only.
    else:
        record = await authorize_solver(db, user, solver_id)
    ratings = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)),
        {"solver_id": {"$in": solver_aliases(record)}}]}).sort("created_at", -1).to_list(200)
    return [{"id": str(r["_id"]), "accuracy": r.get("accuracy"), "timeliness": r.get("timeliness"),
             "overall": r.get("overall"), "created_at": r.get("created_at"), "voided": r.get("voided", False)}
            for r in ratings]


@router.post("/ratings/{rating_id}/void")
async def void_rating(rating_id: str, request: Request):
    """IT Admin only â€” void a rating with a mandatory reason (Fix 1)."""
    user = await get_current_user(request)
    if user["role"] != "it_admin":
        raise HTTPException(status_code=403, detail="Only IT Admin can void ratings")
    body = await request.json()
    reason = (body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="A void reason of â‰¥5 characters is required")
    db = get_db()
    clauses = [{"id": rating_id}, {"_id": rating_id}]
    if ObjectId.is_valid(rating_id):
        clauses.append({"_id": ObjectId(rating_id)})
    async with integrity_write(db):
        found = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)), {"$or": clauses}]}).to_list(2)
        if len(found) != 1:
            raise HTTPException(409 if found else 404, "Rating not found or ambiguous")
        rating = found[0]
        await find_solver(db, rating.get("solver_id"), user)
        await db.solver_ratings.update_one({"$and": [tenant_query(tenant_of(user)), {"_id": rating["_id"]}]},
            {"$set": {"voided": True, "void_reason": reason, "voided_by": user["id"],
                      "voided_at": datetime.now(timezone.utc).isoformat()}})
        await _recompute_solver_averages(db, rating["solver_id"], user)
    await audit_solver(db, user, "solver.rating.voided", [await find_solver(db, rating["solver_id"], user)], ["voided"])
    return {"voided": True}
