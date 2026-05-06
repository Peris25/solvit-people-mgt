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
    return fmt(result)
