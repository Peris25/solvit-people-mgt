from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    title: str
    event_type: str  # onboarding, review, survey, recognition, stay_interview, holiday, leave
    start_date: str
    end_date: Optional[str] = None
    all_day: bool = True
    description: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    color: Optional[str] = None
    module: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


EVENT_COLORS = {
    "onboarding": "#3B82F6",
    "probation": "#F59E0B",
    "review": "#8B5CF6",
    "survey": "#06B6D4",
    "recognition": "#F97316",
    "stay_interview": "#EC4899",
    "holiday": "#6B7280",
    "leave": "#22C55E",
    "disciplinary": "#EF4444",
    "compliance": "#FF353F"
}


@router.get("")
async def get_calendar_events(request: Request, days_ahead: int = 90):
    user = await get_current_user(request)
    db = get_db()
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    end_date = (now + timedelta(days=days_ahead)).isoformat()[:10]
    start_date = now.isoformat()[:10]

    all_events = []

    # Get public holidays
    holidays = await db.public_holidays.find({"tenant_id": "solvit", "date": {"$gte": start_date, "$lte": end_date}}).to_list(50)
    for h in holidays:
        all_events.append({
            "id": str(h.get("id", str(h.get("_id", "")))),
            "title": h["name"],
            "event_type": "holiday",
            "start_date": h["date"],
            "end_date": h["date"],
            "all_day": True,
            "color": EVENT_COLORS["holiday"],
            "module": "HR Calendar",
            "description": h.get("type", "Public Holiday")
        })

    # Get leave requests
    approved_leaves = await db.leave_requests.find({
        "tenant_id": "solvit",
        "status": "Approved",
        "start_date": {"$gte": start_date, "$lte": end_date}
    }).to_list(100)
    for lr in approved_leaves:
        all_events.append({
            "id": str(lr.get("id", str(lr.get("_id", "")))),
            "title": f"{lr.get('leave_type', 'Leave')} — Employee",
            "event_type": "leave",
            "start_date": lr.get("start_date"),
            "end_date": lr.get("end_date"),
            "all_day": True,
            "color": EVENT_COLORS["leave"],
            "module": "Leave Management",
            "employee_id": lr.get("employee_id")
        })

    # Get onboarding milestones
    onboarding_emps = await db.employees.find({
        "tenant_id": "solvit",
        "lifecycle_state": {"$in": ["Onboarding", "Probation"]}
    }).to_list(50)
    for emp in onboarding_emps:
        start = emp.get("start_date", "")
        if start:
            all_events.append({
                "id": f"onb-{str(emp.get('id', str(emp['_id'])))}",
                "title": f"Onboarding: {emp.get('full_name', '')}",
                "event_type": "onboarding",
                "start_date": start,
                "end_date": start,
                "all_day": True,
                "color": EVENT_COLORS["onboarding"],
                "module": "Onboarding",
                "employee_id": str(emp.get("id", str(emp["_id"]))),
                "employee_name": emp.get("full_name")
            })

    # Get survey windows
    surveys = await db.survey_windows.find({
        "tenant_id": "solvit",
        "status": "Open",
        "open_date": {"$lte": end_date}
    }).to_list(10)
    for s in surveys:
        all_events.append({
            "id": str(s.get("id", str(s.get("_id", "")))),
            "title": s.get("title", "Survey"),
            "event_type": "survey",
            "start_date": s.get("open_date"),
            "end_date": s.get("close_date"),
            "all_day": True,
            "color": EVENT_COLORS["survey"],
            "module": "Surveys"
        })

    # Get manual events
    manual = await db.calendar_events.find({
        "tenant_id": "solvit",
        "start_date": {"$gte": start_date, "$lte": end_date}
    }).to_list(100)
    for e in manual:
        e_fmt = fmt(e)
        e_fmt["color"] = EVENT_COLORS.get(e.get("event_type", ""), "#6B7280")
        all_events.append(e_fmt)

    return sorted(all_events, key=lambda x: x.get("start_date", ""))


@router.post("")
async def create_event(event: CalendarEvent, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **event.model_dump(),
        "color": event.color or EVENT_COLORS.get(event.event_type, "#6B7280"),
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.calendar_events.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc
