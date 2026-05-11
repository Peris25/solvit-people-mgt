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

# MD KPIs (Board-administered) — fixed list per FRD §8 corrections.
MD_KPIS = [
    {"kpi": "Revenue Growth",                    "section": "Strategic Direction",      "target": "Per annual business plan"},
    {"kpi": "Solvit Alignment Survey Score",     "section": "Culture & Values Stewardship", "target": "Org-wide aggregate ≥ 70"},
    {"kpi": "Operational KPI Achievement",       "section": "Leadership Environment",    "target": "≥ 85% of departmental KPIs monthly"},
    {"kpi": "Budget Adherence",                  "section": "Financial Governance",      "target": "≤ 5% variance monthly"},
    {"kpi": "Client Retention",                  "section": "External Representation",   "target": "≥ 95% annually"},
    {"kpi": "CSAT Score",                        "section": "External Representation",   "target": "> 4.7"},
    {"kpi": "Channel Partner NPS",               "section": "External Representation",   "target": "> 50 monthly"},
    {"kpi": "Board Reporting",                   "section": "Board Governance",          "target": "Report submitted by 7th of each month"},
]


def get_rating(score: float) -> str:
    if score <= 1.49:
        return "Exceeded"
    elif score <= 1.99:
        return "Met"
    elif score <= 2.49:
        return "Below"
    else:
        return "Forfeited"


async def get_rating_live(score: float) -> str:
    """Threshold-driven classification — pulls bounds live from
    Masters Settings → performance.scoring_thresholds. Falls back to
    static defaults on miss."""
    if score is None:
        return "Pending"
    try:
        from routes.masters_settings import get_setting
        t = await get_setting("performance", "scoring_thresholds")
    except Exception:
        t = None
    if not t:
        return get_rating(float(score))
    s = float(score)
    for label in ("Exceeded", "Met", "Below"):
        bounds = t.get(label) or {}
        lo, hi = bounds.get("min"), bounds.get("max")
        if lo is not None and hi is not None and lo <= s <= hi:
            return label
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
    # Enrich with employee name + round scores (D02, D03)
    emp_ids = list({r.get("employee_id") for r in reviews if r.get("employee_id")})
    emp_map = {}
    if emp_ids:
        async for e in db.employees.find({"id": {"$in": emp_ids}}, {"id": 1, "full_name": 1, "role_title": 1, "department": 1}):
            emp_map[e.get("id")] = e
    out = []
    for r in reviews:
        rec = fmt(r)
        emp = emp_map.get(rec.get("employee_id"))
        if emp:
            rec["employee_name"] = emp.get("full_name")
            rec["role_title"] = emp.get("role_title")
            rec["department"] = emp.get("department")
        for k in ("overall_score", "section_a_score", "section_b_score", "section_c_score"):
            if rec.get(k) is not None:
                try:
                    rec[k] = round(float(rec[k]), 1)
                except Exception:
                    pass
        out.append(rec)
    return out


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


@router.get("/review-panel/{employee_id}")
async def get_review_panel(employee_id: str, request: Request):
    """Return the Review Meeting Panel for an employee per FRD Correction §2.

    Rules (matrix-authoritative):
    - MD / CEO              → []           (board-led, not in platform)
    - Reports to MD         → [MD, HR Admin]
    - Reports to Finance Ops Mgr → [HR Admin, Line Manager:finance_ops]
    - All other employees   → [HR Admin, Line Manager]
    Casting vote: HR Admin (recorded in `casting_vote_role`).
    """
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager", "executive", "board", "it_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    try:
        emp = await db.employees.find_one({"_id": ObjectId(employee_id)})
    except Exception:
        emp = await db.employees.find_one({"id": employee_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    role_title = (emp.get("role_title") or "").lower()
    is_md = bool(emp.get("is_md")) or role_title in ("managing director", "ceo", "md", "chief executive officer")
    is_ed = bool(emp.get("is_ed")) or role_title == "executive director"
    reports_to_md = bool(emp.get("reports_to_md"))
    reports_to_finance_ops = bool(emp.get("reports_to_finance_ops"))

    if is_md or is_ed:
        return {
            "employee_id": str(emp.get("id", str(emp["_id"]))),
            "employee_name": emp.get("full_name"),
            "panel": [],
            "panel_type": "board_led",
            "casting_vote_role": "board_chair",
            "note": ("MD performance is Board-led — coordinated by the Board Chair. HR has no involvement."
                     if is_md else
                     "Executive Director review follows the same Board-led model as the MD. HR is not involved."),
        }

    panel_roles = []
    if reports_to_md:
        panel_type = "md_direct_report"
        panel_roles = ["md", "hr_admin"]
    elif reports_to_finance_ops:
        panel_type = "finance_ops_report"
        panel_roles = ["hr_admin", "line_manager:finance_ops"]
    else:
        panel_type = "standard"
        panel_roles = ["hr_admin", "line_manager"]

    # Resolve actual users for each role slot
    panel = []
    for slot in panel_roles:
        if slot == "md":
            md_user = await db.users.find_one({"role": "executive", "tenant_id": "solvit"})
            panel.append({"role": "md", "user_id": str(md_user["_id"]) if md_user else None,
                          "name": md_user.get("full_name") if md_user else "Managing Director",
                          "email": md_user.get("email") if md_user else None})
        elif slot == "hr_admin":
            hr_user = await db.users.find_one({"role": "hr_admin", "tenant_id": "solvit"})
            panel.append({"role": "hr_admin", "user_id": str(hr_user["_id"]) if hr_user else None,
                          "name": hr_user.get("full_name") if hr_user else "HR Admin",
                          "email": hr_user.get("email") if hr_user else None})
        elif slot.startswith("line_manager"):
            lm_id = emp.get("line_manager_id")
            lm = None
            if lm_id:
                lm = await db.employees.find_one({"id": lm_id}) or await db.users.find_one({"id": lm_id})
            panel.append({"role": "line_manager", "user_id": lm_id,
                          "name": (lm or {}).get("full_name", "Line Manager"),
                          "email": (lm or {}).get("work_email") or (lm or {}).get("email")})

    return {
        "employee_id": str(emp.get("id", str(emp["_id"]))),
        "employee_name": emp.get("full_name"),
        "panel": panel,
        "panel_type": panel_type,
        "casting_vote_role": "hr_admin",
        "rationale": {
            "is_md": is_md,
            "reports_to_md": reports_to_md,
            "reports_to_finance_ops": reports_to_finance_ops,
        }
    }


@router.get("/talent-density")
async def get_talent_density_kpi(request: Request, cycle_year: Optional[int] = None):
    """Composite organisational health metric. Target 85%."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    year = cycle_year or datetime.now(timezone.utc).year

    active_count = await db.employees.count_documents({"tenant_id": "solvit", "lifecycle_state": "Active"})
    reviews = await db.performance_reviews.find({"tenant_id": "solvit", "cycle_year": year}).to_list(500)
    in_target = sum(1 for r in reviews if r.get("nine_box_placement") in ["Stars", "Core_Contributor"])
    primary_pct = (in_target / max(active_count, 1)) * 100 if active_count else 0

    section_b_scores = [r.get("section_b_score") for r in reviews if r.get("section_b_score") is not None]
    sec_b_avg = sum(section_b_scores) / len(section_b_scores) if section_b_scores else 0
    section_b_pct = max(0, min(100, (3 - sec_b_avg) / 2 * 100)) if sec_b_avg else 0

    survey_pct = 70
    latest_survey = await db.survey_responses.find({"tenant_id": "solvit"}).sort("created_at", -1).limit(50).to_list(50)
    if latest_survey:
        scores = []
        for s in latest_survey:
            scores.extend([v for v in (s.get("scores") or {}).values() if isinstance(v, (int, float))])
        if scores:
            survey_pct = sum(scores) / len(scores) * 20

    composite = round(primary_pct * 0.6 + section_b_pct * 0.25 + survey_pct * 0.15, 1)
    from routes.masters_settings import get_setting
    target = int(await get_setting("performance", "talent_density_target_pct", 85) or 85)
    return {
        "score_pct": composite,
        "target_pct": target,
        "status": "Healthy" if composite >= target else "Below Target" if composite >= max(target - 15, 50) else "Critical",
        "components": {
            "primary_stars_core_pct": round(primary_pct, 1),
            "secondary_values_avg_pct": round(section_b_pct, 1),
            "tertiary_alignment_pct": round(survey_pct, 1),
        },
        "active_employees": active_count,
        "in_target_quadrant": in_target,
        "cycle_year": year
    }


@router.get("/md-kpis")
async def get_md_kpis(request: Request):
    """Return the eight MD KPIs (Board-administered).
    Visible to Board, MD, and IT Admin only — HR has no read access to MD KPIs."""
    user = await get_current_user(request)
    if user["role"] not in ("board", "executive", "it_admin"):
        raise HTTPException(status_code=403, detail="MD KPIs are Board-only. HR has no access.")
    return {"kpis": MD_KPIS, "count": len(MD_KPIS), "administered_by": "Board of Directors"}


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
    rec = fmt(r)
    # Enrich + round (D02 / D03)
    emp = await db.employees.find_one({"id": rec.get("employee_id")})
    if emp:
        rec["employee_name"] = emp.get("full_name")
        rec["role_title"] = emp.get("role_title")
        rec["department"] = emp.get("department")
    for k in ("overall_score", "section_a_score", "section_b_score", "section_c_score"):
        if rec.get(k) is not None:
            try:
                rec[k] = round(float(rec[k]), 1)
            except Exception:
                pass
    return rec


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
