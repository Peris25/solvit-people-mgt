from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/performance", tags=["performance"])

NINE_BOX = ["Stars", "Core_Contributor", "Culture_Risk", "Realignment_Needed", "Exit_Track"]
RATING_LABELS = {(1.0, 1.49): "Exceeded", (1.5, 1.99): "Met", (2.0, 2.49): "Below", (2.5, 3.0): "Forfeited"}


def get_rating(score: float) -> str:
    if score <= 1.49:
        return "Exceeded"
    elif score <= 1.99:
        return "Met"
    elif score <= 2.49:
        return "Below"
    else:
        return "Forfeited"


class ReviewCreate(BaseModel):
    employee_id: str
    cycle_type: str  # Mid_Year or Year_End
    cycle_year: int


class ReviewUpdate(BaseModel):
    section_a_kpis: Optional[List[Dict[str, Any]]] = None
    section_a_score: Optional[float] = None
    section_b_score: Optional[float] = None
    section_c_nps: Optional[float] = None
    section_c_csat: Optional[float] = None
    section_c_score: Optional[float] = None
    nine_box_placement: Optional[str] = None
    development_priority: Optional[str] = None
    employee_signature: Optional[str] = None
    manager_signature: Optional[str] = None
    hr_signature: Optional[str] = None
    status: Optional[str] = None
    form_data_json: Optional[Dict[str, Any]] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


def calculate_overall_score(a: float, b: float, c: float) -> float:
    return round(a * 0.5 + b * 0.3 + c * 0.2, 1)


@router.get("")
async def list_reviews(request: Request, employee_id: Optional[str] = None, cycle_year: Optional[int] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit"}
    if employee_id:
        query["employee_id"] = employee_id
    if cycle_year:
        query["cycle_year"] = cycle_year
    if status:
        query["status"] = status
    if user["role"] == "employee":
        query["employee_id"] = user.get("employee_id", user["id"])
    elif user["role"] == "line_manager":
        direct_reports = await db.employees.find({"line_manager_id": user.get("employee_id", user["id"])}).to_list(100)
        ids = [str(e.get("id", str(e["_id"]))) for e in direct_reports]
        query["employee_id"] = {"$in": ids}
    reviews = await db.performance_reviews.find(query).sort("created_at", -1).to_list(200)
    return [fmt(r) for r in reviews]


@router.post("")
async def create_review(review: ReviewCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    existing = await db.performance_reviews.find_one({
        "employee_id": review.employee_id,
        "cycle_type": review.cycle_type,
        "cycle_year": review.cycle_year
    })
    if existing:
        raise HTTPException(status_code=400, detail="Review already exists for this cycle")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **review.model_dump(),
        "section_a_score": None,
        "section_b_score": None,
        "section_c_score": None,
        "overall_score": None,
        "rating": None,
        "nine_box_placement": None,
        "talent_density_pct": None,
        "consequence_workflow": None,
        "form_data_json": {},
        "employee_signature_at": None,
        "manager_signature_at": None,
        "hr_signature_at": None,
        "status": "Draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.performance_reviews.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.get("/active-cycle")
async def get_active_cycle(request: Request):
    user = await get_current_user(request)
    db = get_db()
    now = datetime.now(timezone.utc)
    cycle_type = "Mid_Year" if now.month <= 6 else "Year_End"
    return {"cycle_type": cycle_type, "cycle_year": now.year, "is_active": True}


@router.get("/{review_id}")
async def get_review(review_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    try:
        r = await db.performance_reviews.find_one({"_id": ObjectId(review_id)})
    except Exception:
        r = await db.performance_reviews.find_one({"id": review_id})
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    return fmt(r)


@router.put("/{review_id}")
async def update_review(review_id: str, upd: ReviewUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    try:
        current = await db.performance_reviews.find_one({"_id": ObjectId(review_id)})
    except Exception:
        current = await db.performance_reviews.find_one({"id": review_id})
    if not current:
        raise HTTPException(status_code=404, detail="Review not found")

    update_data = {k: v for k, v in upd.model_dump().items() if v is not None}
    if upd.employee_signature:
        update_data["employee_signature_at"] = datetime.now(timezone.utc).isoformat()
    if upd.manager_signature:
        update_data["manager_signature_at"] = datetime.now(timezone.utc).isoformat()
    if upd.hr_signature:
        update_data["hr_signature_at"] = datetime.now(timezone.utc).isoformat()

    # Auto-calculate overall score
    a = upd.section_a_score or current.get("section_a_score")
    b = upd.section_b_score or current.get("section_b_score")
    c = upd.section_c_score or current.get("section_c_score")
    if a and b and c:
        overall = calculate_overall_score(a, b, c)
        update_data["overall_score"] = overall
        update_data["rating"] = get_rating(overall)

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.performance_reviews.find_one_and_update(
            {"_id": ObjectId(review_id)}, {"$set": update_data}, return_document=True
        )
    except Exception:
        result = await db.performance_reviews.find_one_and_update(
            {"id": review_id}, {"$set": update_data}, return_document=True
        )

    # Fire consequence workflows
    if update_data.get("overall_score"):
        from automation.engine import automation_engine
        await automation_engine.fire_event("performance_score_calculated", {
            "employee_id": result.get("employee_id"),
            "score": update_data["overall_score"],
            "rating": update_data.get("rating")
        })

    return fmt(result)


@router.get("/employee/{employee_id}/history")
async def get_review_history(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    reviews = await db.performance_reviews.find({"employee_id": employee_id}).sort("created_at", -1).to_list(20)
    return [fmt(r) for r in reviews]


@router.put("/nine-box/{employee_id}/placement")
async def update_nine_box_placement(employee_id: str, request: Request):
    """Update an employee's most-recent review nine_box_placement (drag-and-drop)."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    new_placement = body.get("placement")
    if new_placement not in NINE_BOX:
        raise HTTPException(status_code=400, detail=f"Invalid placement. Must be one of: {NINE_BOX}")
    db = get_db()
    cycle_year = body.get("cycle_year") or datetime.now(timezone.utc).year
    # Find latest review for this cycle
    review = await db.performance_reviews.find_one(
        {"employee_id": employee_id, "cycle_year": cycle_year, "tenant_id": "solvit"},
        sort=[("created_at", -1)]
    )
    if not review:
        raise HTTPException(status_code=404, detail=f"No performance review found for employee {employee_id} in cycle {cycle_year}. Create one first.")
    await db.performance_reviews.update_one(
        {"_id": review["_id"]},
        {"$set": {"nine_box_placement": new_placement, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    # Audit
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "action": "nine_box.placement.update",
        "entity": f"performance_review:{review['id']}",
        "performed_by": user["id"],
        "metadata": {"old": review.get("nine_box_placement"), "new": new_placement, "employee_id": employee_id},
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"status": "success", "employee_id": employee_id, "placement": new_placement}


@router.get("/nine-box/matrix")
async def get_nine_box_matrix(request: Request, cycle_year: Optional[int] = None):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    year = cycle_year or datetime.now(timezone.utc).year
    reviews = await db.performance_reviews.find({
        "tenant_id": "solvit",
        "cycle_year": year,
        "nine_box_placement": {"$exists": True, "$ne": None}
    }).to_list(200)
    matrix = {}
    for placement in NINE_BOX:
        matrix[placement] = []
    for r in reviews:
        placement = r.get("nine_box_placement")
        if placement in matrix:
            emp = await db.employees.find_one({"id": r["employee_id"]})
            if emp:
                matrix[placement].append({
                    "employee_id": r["employee_id"],
                    "name": emp.get("full_name"),
                    "role": emp.get("role_title"),
                    "department": emp.get("department"),
                    "score": r.get("overall_score"),
                    "rating": r.get("rating")
                })
    return matrix
