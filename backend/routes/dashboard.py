"""Role-scoped dashboard endpoints.

Currently implemented:
- GET /api/dashboard/line-manager — direct reports + pending leave approvals,
  flight-risk distribution and open performance review tasks for the caller's
  team. Line Manager (and HR Admin / IT Admin for support) only.
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
from bson import ObjectId

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _resolve_emp_id(db, user) -> str | None:
    emp = await db.employees.find_one({
        "tenant_id": "solvit",
        "work_email": (user.get("email") or "").lower(),
    })
    return (emp.get("id") or str(emp.get("_id"))) if emp else None


@router.get("/line-manager")
async def line_manager_widget(request: Request):
    """Compact 'what needs me today' brief for a line manager.

    Scope: ONLY the caller's own record + their direct reports. Returns:
    - team[]: direct reports with key signals (lifecycle_state, flight_risk_level,
      pending_leave count, days_since_last_review)
    - pending_leave: total count of Pending_Manager leave requests for the team
    - flight_risk_summary: counts by level (Critical / High / Elevated / Healthy)
    - open_reviews: number of in-progress / overdue performance reviews owned by me
    - my_open_tasks: count of tasks assigned to me that are still open
    """
    user = await get_current_user(request)
    if user["role"] not in ("line_manager", "hr_admin", "hr_manager", "it_admin"):
        raise HTTPException(status_code=403, detail="Line Manager widget access only")
    db = get_db()
    my_emp_id = await _resolve_emp_id(db, user)
    if not my_emp_id:
        return {
            "manager_employee_id": None,
            "team": [],
            "pending_leave": 0,
            "flight_risk_summary": {"Critical": 0, "High": 0, "Elevated": 0, "Healthy": 0},
            "open_reviews": 0,
            "my_open_tasks": 0,
            "note": "No employee record found for this account.",
        }

    # Direct reports (exclude Exited)
    reports = await db.employees.find({
        "tenant_id": "solvit",
        "line_manager_id": my_emp_id,
        "lifecycle_state": {"$ne": "Exited"},
    }).sort("full_name", 1).to_list(200)

    report_ids = [(r.get("id") or str(r.get("_id"))) for r in reports]

    # Pending leave approvals for the team
    pending_leave_rows = await db.leave_requests.find({
        "tenant_id": "solvit",
        "employee_id": {"$in": report_ids},
        "status": "Pending_Manager",
    }).to_list(500)
    pending_by_emp = {}
    for lr in pending_leave_rows:
        pending_by_emp[lr["employee_id"]] = pending_by_emp.get(lr["employee_id"], 0) + 1

    # Flight risk distribution
    risk = {"Critical": 0, "High": 0, "Elevated": 0, "Healthy": 0}
    for r in reports:
        level = r.get("flight_risk_level") or "Healthy"
        risk[level] = risk.get(level, 0) + 1

    # Last review per report (most recent)
    today = datetime.now(timezone.utc).date()
    team = []
    open_reviews = 0
    for r in reports:
        emp_id = r.get("id") or str(r.get("_id"))
        last = await db.performance_reviews.find_one(
            {"tenant_id": "solvit", "employee_id": emp_id},
            sort=[("created_at", -1)],
        )
        in_progress = await db.performance_reviews.count_documents({
            "tenant_id": "solvit",
            "employee_id": emp_id,
            "status": {"$in": ["Draft", "In_Progress", "Scoring", "Pending_Review_Meeting"]},
        })
        if in_progress:
            open_reviews += in_progress
        days_since = None
        if last and last.get("created_at"):
            try:
                d = datetime.fromisoformat(last["created_at"].replace("Z", "+00:00")).date()
                days_since = (today - d).days
            except Exception:
                days_since = None
        team.append({
            "id": emp_id,
            "full_name": r.get("full_name"),
            "role_title": r.get("role_title"),
            "department": r.get("department"),
            "lifecycle_state": r.get("lifecycle_state"),
            "flight_risk_level": r.get("flight_risk_level") or "Healthy",
            "pending_leave": pending_by_emp.get(emp_id, 0),
            "open_reviews": in_progress,
            "days_since_last_review": days_since,
            "last_performance_score": r.get("last_performance_score"),
        })

    # My open tasks
    my_tasks = await db.tasks.count_documents({
        "tenant_id": "solvit",
        "assigned_to": my_emp_id,
        "status": {"$in": ["Pending", "In_Progress"]},
    })

    return {
        "manager_employee_id": my_emp_id,
        "team": team,
        "team_size": len(team),
        "pending_leave": len(pending_leave_rows),
        "flight_risk_summary": risk,
        "open_reviews": open_reviews,
        "my_open_tasks": my_tasks,
    }
