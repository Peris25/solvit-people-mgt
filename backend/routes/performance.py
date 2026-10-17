from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.employee_access import authorize_employee, scoped_employee_query, reference_ids, find_linked_record, reject_identity_changes
from utils.employee_integrity import user_employee_aliases, find_employee, tenant_of, tenant_query, integrity_write
from utils import performance_workflows as workflow
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


@router.get("/cycles")
async def list_cycles(request: Request):
    from utils.employee_access import personal_grant
    user = await get_current_user(request)
    personal_grant(user, "M05")
    rows = await get_db().performance_cycles.find(tenant_query(tenant_of(user))).sort("starts_on", -1).to_list(None)
    fields = {"id", "cycle_type", "cycle_year", "starts_on", "ends_on", "self_due_on", "manager_due_on", "status"}
    if user.get("role") in workflow.HR: fields.add("scoring_policy")
    return [{key: row.get(key) for key in fields} for row in rows]


@router.post("/cycles")
async def configure_cycle(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict): raise HTTPException(422, "An object body is required")
    db = get_db()
    async with integrity_write(db):
        return await workflow.create_cycle(db, user, body)


@router.put("/{review_id}/goals")
async def update_goals(review_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict): raise HTTPException(422, "An object body is required")
    db = get_db()
    async with integrity_write(db):
        return await workflow.goals(db, user, review_id, body)


@router.post("/{review_id}/assessments/{stage}")
async def submit_assessment(review_id: str, stage: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    if not isinstance(body, dict): raise HTTPException(422, "An object body is required")
    db = get_db()
    async with integrity_write(db):
        return await workflow.assess(db, user, review_id, stage, body)


@router.get("")
async def list_reviews(request: Request, employee_id: Optional[str] = None, cycle_year: Optional[int] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = await scoped_employee_query(db, user, "M05", employee_id)
    if cycle_year:
        query = {"$and": [query, {"cycle_year": cycle_year}]}
    if status:
        query = {"$and": [query, {"status": status}]}
    reviews = await db.performance_reviews.find(query).sort("created_at", -1).to_list(200)
    out = []
    for row in reviews:
        try:
            employee = await workflow.employee_access(db, user, row.get("employee_id"))
        except HTTPException as error:
            if error.status_code in (403, 404): continue
            raise
        out.append(workflow.projection(row, user, employee))
    return out


@router.post("")
async def create_review(review: ReviewCreate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        return await workflow.create_review(db, user, review.model_dump())


@router.get("/active-cycle")
async def get_active_cycle(request: Request):
    user = await get_current_user(request)
    from utils.employee_access import personal_grant
    personal_grant(user, "M05")
    today = datetime.now(timezone.utc).date().isoformat()
    rows = await get_db().performance_cycles.find(tenant_query(tenant_of(user))).to_list(None)
    active = [row for row in rows if row.get("starts_on", "z") <= today <= row.get("ends_on", "")]
    if len(active) > 1:
        raise HTTPException(409, "Overlapping active cycles require HR review")
    if not active: return {"is_active": False, "cycle_type": None, "cycle_year": None}
    return {"is_active": True, **{key: active[0].get(key) for key in ("id", "cycle_type", "cycle_year", "starts_on", "ends_on")}}


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
    emp = await find_employee(db, employee_id, tenant_of(user))
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if user["role"] not in ("board", "it_admin"):
        await authorize_employee(db, user, employee_id, "M05")

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
            md_user = await db.users.find_one({"role": "executive", "tenant_id": tenant_of(user)})
            panel.append({"role": "md", "user_id": str(md_user["_id"]) if md_user else None,
                          "name": md_user.get("full_name") if md_user else "Managing Director",
                          "email": md_user.get("email") if md_user else None})
        elif slot == "hr_admin":
            hr_user = await db.users.find_one({"role": "hr_admin", "tenant_id": tenant_of(user)})
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
    from utils.access_matrix import get_module_access
    if not get_module_access("M05", user.get("role")):
        raise HTTPException(403, "No performance aggregate permission")
    db = get_db()
    year = cycle_year or datetime.now(timezone.utc).year

    active_count = await db.employees.count_documents({"tenant_id": tenant_of(user), "lifecycle_state": "Active"})
    reviews = await db.performance_reviews.find({"tenant_id": tenant_of(user), "cycle_year": year}).to_list(500)
    in_target = sum(1 for r in reviews if r.get("nine_box_placement") in ["Stars", "Core_Contributor"])
    primary_pct = (in_target / max(active_count, 1)) * 100 if active_count else 0

    section_b_scores = [r.get("section_b_score") for r in reviews if r.get("section_b_score") is not None]
    sec_b_avg = sum(section_b_scores) / len(section_b_scores) if section_b_scores else 0
    section_b_pct = max(0, min(100, (3 - sec_b_avg) / 2 * 100)) if sec_b_avg else 0

    survey_pct = None
    latest_survey = await db.survey_responses.find({"tenant_id": tenant_of(user)}).sort("created_at", -1).limit(50).to_list(50)
    if latest_survey:
        scores = []
        for s in latest_survey:
            scores.extend([v for v in (s.get("scores") or {}).values() if isinstance(v, (int, float))])
        if scores:
            survey_pct = sum(scores) / len(scores) * 20

    composite = round(primary_pct * 0.6 + section_b_pct * 0.25 + survey_pct * 0.15, 1) if survey_pct is not None and section_b_scores else None
    from routes.masters_settings import get_setting
    target = int(await get_setting("performance", "talent_density_target_pct", 85) or 85)
    return {
        "score_pct": composite,
        "target_pct": target,
        "status": "Insufficient data" if composite is None else "Healthy" if composite >= target else "Below Target" if composite >= max(target - 15, 50) else "Critical",
        "components": {
            "primary_stars_core_pct": round(primary_pct, 1),
            "secondary_values_avg_pct": round(section_b_pct, 1),
            "tertiary_alignment_pct": round(survey_pct, 1) if survey_pct is not None else None,
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
    row, employee = await workflow.record(get_db(), user, review_id)
    return workflow.projection(row, user, employee)


@router.put("/{review_id}")
async def update_review(review_id: str, upd: ReviewUpdate, request: Request):
    user = await get_current_user(request)
    await workflow.record(get_db(), user, review_id)
    raise HTTPException(409, "Use the staged assessment workflow. Historical scores require approved reconciliation.")


@router.get("/employee/{employee_id}/history")
async def get_review_history(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await authorize_employee(db, user, employee_id, "M05")
    reviews = await db.performance_reviews.find({"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": reference_ids(employee) + [employee["_id"]]}}]}).sort("created_at", -1).to_list(200)
    await workflow.employee_access(db, user, employee_id)
    return [workflow.projection(row, user, employee) for row in reviews]


@router.put("/nine-box/{employee_id}/placement")
async def update_nine_box_placement(employee_id: str, request: Request):
    """Update an employee's most-recent review nine_box_placement (drag-and-drop)."""
    user = await get_current_user(request)
    workflow.require_hr(user)
    body = await request.json()
    if not isinstance(body, dict) or body.get("placement") not in NINE_BOX:
        raise HTTPException(422, "Choose a valid placement")
    db = get_db()
    async with integrity_write(db):
        employee = await workflow.employee_access(db, user, employee_id, write=True)
        if employee.get("id") == user.get("employee_id"):
            raise HTTPException(403, "Employees cannot classify their own performance")
        reviews = await db.performance_reviews.find({"$and": [tenant_query(tenant_of(user)), {
            "employee_id": {"$in": reference_ids(employee) + [employee["_id"]]},
            "cycle_year": body.get("cycle_year") or datetime.now(timezone.utc).year}]}).sort("created_at", -1).to_list(1)
        if not reviews: raise HTTPException(404, "No review found for this period")
        if reviews[0].get("workflow_version") == 1 and reviews[0].get("status") not in {"HR_Reviewed", "Completed"}:
            raise HTTPException(409, "HR assessment must be completed before classification")
        await workflow.save(db, user, reviews[0], {"nine_box_placement": body["placement"]}, "performance.placement.changed")
    return {"status": "success", "employee_id": employee_id, "placement": body["placement"]}


@router.get("/nine-box/matrix")
async def get_nine_box_matrix(request: Request, cycle_year: Optional[int] = None):
    user = await get_current_user(request)
    if user.get("role") not in workflow.HR: raise HTTPException(403, "Named performance matrix is HR-only")
    from utils.employee_access import personal_grant
    personal_grant(user, "M05")
    db = get_db()
    year = cycle_year or datetime.now(timezone.utc).year
    reviews = await db.performance_reviews.find({
        "tenant_id": tenant_of(user),
        "cycle_year": year,
        "nine_box_placement": {"$exists": True, "$ne": None}
    }).to_list(200)
    matrix = {}
    for placement in NINE_BOX:
        matrix[placement] = []
    for r in reviews:
        placement = r.get("nine_box_placement")
        if placement in matrix:
            try:
                emp = await workflow.employee_access(db, user, r["employee_id"])
            except HTTPException as error:
                if error.status_code in (403, 404): continue
                raise
            if emp:
                visible = workflow.projection(r, user, emp)
                if visible.get("nine_box_placement") != placement:
                    continue
                matrix[placement].append({
                    "employee_id": emp.get("id") or str(emp["_id"]),
                    "name": emp.get("full_name"),
                    "role": emp.get("role_title"),
                    "department": emp.get("department"),
                    "score": visible.get("overall_score"),
                    "rating": visible.get("rating")
                })
    return matrix
