"""First-Login Onboarding Walkthrough — per-user completion flag + admin controls."""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/onboarding-tour", tags=["onboarding_tour"])

DEFAULT_HEADLINE_PREFIX = "Welcome to Solvit People"
DEFAULT_BODY = "Your central platform for HR, performance, leave, and people decisions — built for Solvit Limited. Take the quick tour to get oriented."

ROLE_STEPS = {
    "hr_admin": [
        {"id": "employees", "title": "Employee Database", "target": "/employees", "body": "Manage every FTE record — search, edit, export and view profiles."},
        {"id": "performance", "title": "Performance Reviews", "target": "/performance", "body": "Track review cycles, 9-box placements and individual outcomes."},
        {"id": "leave", "title": "Leave Management", "target": "/leave", "body": "Approve team leave, see calendars and accrual balances at a glance."},
        {"id": "data-import", "title": "Data Import", "target": "/data-import", "body": "Bulk-import employees, solvers and historical performance data via Excel."},
        {"id": "masters", "title": "General Masters Settings", "target": "/masters", "body": "Tweak every system-wide variable — thresholds, lookups and templates."},
        {"id": "calendar", "title": "HR Calendar", "target": "/calendar", "body": "Compliance, leave, reviews and key events on one timeline."},
    ],
    "line_manager": [
        {"id": "team", "title": "My Team", "target": "/employees", "body": "Your direct reports — performance, leave and 1-on-1 history."},
        {"id": "leave", "title": "Leave Approvals", "target": "/leave", "body": "Approve or reject team leave requests."},
        {"id": "performance", "title": "Performance Reviews", "target": "/performance", "body": "Complete reviews and track team development."},
        {"id": "my-tasks", "title": "1-on-1 Log & Tasks", "target": "/my-tasks", "body": "Your action items, follow-ups and pending tasks."},
        {"id": "surveys", "title": "Team Alignment Scores", "target": "/surveys", "body": "See your team's alignment survey results."},
    ],
    "employee": [
        {"id": "profile", "title": "My Profile", "target": "/dashboard", "body": "Your personal dashboard, profile and pay details."},
        {"id": "leave", "title": "Leave Application", "target": "/leave", "body": "Apply for leave, track balances and approvals."},
        {"id": "performance", "title": "My Goals", "target": "/performance", "body": "Your KPI goals and review history."},
        {"id": "lnd", "title": "My Development Plan", "target": "/lnd", "body": "Training, skills and IDP."},
        {"id": "recognition", "title": "Peer Recognition", "target": "/recognition", "body": "Recognise teammates or view recognition you've received."},
    ],
    "solver": [
        {"id": "jobs", "title": "My Jobs", "target": "/dashboard", "body": "Today's assignments and history."},
        {"id": "performance", "title": "My Performance Score", "target": "/performance", "body": "Your accuracy, reliability and rating."},
        {"id": "ratings", "title": "My Ratings", "target": "/surveys", "body": "Client ratings from inspections you've completed."},
        {"id": "availability", "title": "Availability", "target": "/dashboard", "body": "Mark yourself available or off-duty."},
    ],
    "finance": [
        {"id": "budget", "title": "Budget Overview", "target": "/budget", "body": "People-cost envelope and headroom allocations."},
        {"id": "tier", "title": "Tier Confirmation", "target": "/budget", "body": "Form 28 — confirm GP Actual to unlock bonus & salary changes."},
        {"id": "compensation", "title": "Compensation", "target": "/compensation", "body": "Pay bands, alerts and salary management."},
        {"id": "bonus", "title": "Bonus Calculator", "target": "/compensation", "body": "Model bonus scenarios per tier."},
    ],
    "executive": [
        {"id": "overview", "title": "Organisation Overview", "target": "/dashboard", "body": "Executive view of headcount, attrition and KPIs."},
        {"id": "performance", "title": "Performance Dashboard", "target": "/performance", "body": "Talent density and 9-box placements."},
        {"id": "surveys", "title": "Alignment Survey Results", "target": "/surveys", "body": "Cultural alignment and trend data."},
        {"id": "envelope", "title": "People Cost Envelope", "target": "/budget", "body": "Total people cost vs GP envelope."},
    ],
    "board": [
        {"id": "overview", "title": "Organisation Overview", "target": "/dashboard", "body": "Board-only view of MD/ED and consolidated KPIs."},
        {"id": "md-kpis", "title": "MD KPIs", "target": "/performance", "body": "Eight Board-tracked MD KPIs."},
        {"id": "envelope", "title": "People Cost Envelope", "target": "/budget", "body": "Total people cost vs GP envelope."},
    ],
    "it_admin": [
        {"id": "users", "title": "User Management", "target": "/employees", "body": "Manage user accounts and access."},
        {"id": "masters", "title": "General Masters Settings", "target": "/masters", "body": "Edit every system variable."},
        {"id": "email-templates", "title": "Email Templates", "target": "/masters", "body": "Edit subject lines and bodies for every outbound email."},
        {"id": "email-delivery", "title": "Email Delivery", "target": "/settings", "body": "Switch between Mailtrap (Testing) and Office 365 (Production)."},
        {"id": "data-import", "title": "Data Import", "target": "/data-import", "body": "Bulk import & history."},
        {"id": "audit", "title": "Audit Log", "target": "/masters", "body": "Every settings & document change is logged here."},
    ],
}


async def _get_tour_config(db):
    cfg = await db.onboarding_tour_config.find_one({"tenant_id": "solvit"})
    if not cfg:
        cfg = {
            "tenant_id": "solvit",
            "enabled": True,
            "headline_template": DEFAULT_HEADLINE_PREFIX + " — {{first_name}}",
            "body_text": DEFAULT_BODY,
        }
        await db.onboarding_tour_config.insert_one(cfg)
    cfg.pop("_id", None)
    return cfg


@router.get("/me")
async def my_tour_state(request: Request):
    user = await get_current_user(request)
    db = get_db()
    cfg = await _get_tour_config(db)
    role = user.get("role")
    first_name = (user.get("full_name") or user.get("email") or "").split(" ")[0]
    headline = (cfg.get("headline_template") or "").replace("{{first_name}}", first_name)
    return {
        "completed": bool(user.get("first_login_tour_completed")),
        "enabled": bool(cfg.get("enabled", True)),
        "headline": headline,
        "body_text": cfg.get("body_text"),
        "steps": ROLE_STEPS.get(role, []),
    }


@router.post("/complete")
async def mark_complete(request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json() if (await request.body()) else {}
    skipped = bool(body.get("skipped"))
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"first_login_tour_completed": True,
                  "first_login_tour_completed_at": datetime.now(timezone.utc).isoformat(),
                  "first_login_tour_skipped": skipped}}
    )
    return {"completed": True, "skipped": skipped}


@router.post("/replay")
async def replay_tour(request: Request):
    """Voluntary re-trigger from user's own profile."""
    user = await get_current_user(request)
    db = get_db()
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"first_login_tour_completed": False}}
    )
    return {"reset": True}


# ----- IT Admin controls -----

def _ensure_it(user):
    if user.get("role") != "it_admin":
        raise HTTPException(status_code=403, detail="IT Admin only")


@router.get("/config")
async def get_config(request: Request):
    user = await get_current_user(request)
    _ensure_it(user)
    db = get_db()
    cfg = await _get_tour_config(db)
    return cfg


@router.put("/config")
async def update_config(request: Request):
    user = await get_current_user(request)
    _ensure_it(user)
    body = await request.json()
    db = get_db()
    update = {k: v for k, v in body.items() if k in ("enabled", "headline_template", "body_text")}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = user["id"]
    await db.onboarding_tour_config.update_one({"tenant_id": "solvit"}, {"$set": update}, upsert=True)
    return await _get_tour_config(db)


@router.post("/reset/{user_id}")
async def reset_for_user(user_id: str, request: Request):
    user = await get_current_user(request)
    _ensure_it(user)
    db = get_db()
    result = await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"first_login_tour_completed": False}}
    )
    return {"reset": True, "modified": result.modified_count}


@router.get("/report")
async def tour_completion_report(request: Request):
    user = await get_current_user(request)
    _ensure_it(user)
    db = get_db()
    rows = await db.users.find({}, {"role": 1, "first_login_tour_completed": 1, "first_login_tour_skipped": 1}).to_list(2000)
    by_role = {}
    for r in rows:
        role = r.get("role") or "unknown"
        b = by_role.setdefault(role, {"total": 0, "completed": 0, "skipped": 0, "pending": 0})
        b["total"] += 1
        if r.get("first_login_tour_completed"):
            if r.get("first_login_tour_skipped"):
                b["skipped"] += 1
            else:
                b["completed"] += 1
        else:
            b["pending"] += 1
    return {"by_role": by_role, "total_users": sum(v["total"] for v in by_role.values())}
