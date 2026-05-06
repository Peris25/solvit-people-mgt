from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/surveys", tags=["surveys"])

FTE_ALIGNMENT_QUESTIONS = [
    {"id": "q1", "pillar": 1, "text": "I feel challenged and engaged in my current role."},
    {"id": "q2", "pillar": 1, "text": "I have the tools and resources I need to do my job effectively."},
    {"id": "q3", "pillar": 1, "text": "My line manager provides me with clear direction and support."},
    {"id": "q4", "pillar": 1, "text": "I feel my contributions are recognised at Solvit."},
    {"id": "q5", "pillar": 2, "text": "I understand and live the Solvit values in my work."},
    {"id": "q6", "pillar": 2, "text": "Solvit is a fair and consistent place to work."},
    {"id": "q7", "pillar": 2, "text": "I trust the leadership of Solvit."},
    {"id": "q8", "pillar": 2, "text": "I am proud to work at Solvit."},
    {"id": "q9", "pillar": 3, "text": "My compensation is fair for the work I do."},
    {"id": "q10", "pillar": 3, "text": "I see clear opportunities for career growth at Solvit."},
    {"id": "q11", "pillar": 3, "text": "I would recommend Solvit as a great place to work."},
    {"id": "q12", "pillar": 3, "text": "I see myself still working at Solvit in 12 months."},
]

SOLVER_ALIGNMENT_QUESTIONS = [
    {"id": "q1", "pillar": 1, "text": "The work I do as a Solvit Solver challenges me to use my skills fully."},
    {"id": "q2", "pillar": 1, "text": "I feel trusted by Solvit to do my job well without being micromanaged."},
    {"id": "q3", "pillar": 1, "text": "When I do great work, I feel that Solvit notices and appreciates it."},
    {"id": "q4", "pillar": 1, "text": "Being part of the Solvit Solver network helps me grow professionally."},
    {"id": "q5", "pillar": 2, "text": "I try to live the Solvit values in every inspection I do."},
    {"id": "q6", "pillar": 2, "text": "Solvit treats all Solvers fairly and consistently."},
    {"id": "q7", "pillar": 2, "text": "When I raise a concern with Solvit support, it is handled professionally."},
    {"id": "q8", "pillar": 2, "text": "Solvit enforces its standards consistently."},
    {"id": "q9", "pillar": 3, "text": "The payment I receive for each completed inspection feels fair."},
    {"id": "q10", "pillar": 3, "text": "I know how my performance is scored and what I need to do to earn recognition."},
    {"id": "q11", "pillar": 3, "text": "The recognition Solvit gives to top-performing Solvers motivates me."},
    {"id": "q12", "pillar": 3, "text": "If I perform consistently well, I believe Solvit will reward me appropriately."},
]


class SurveyWindowCreate(BaseModel):
    survey_type: str  # alignment_fte, alignment_solver, engagement_fte, satisfaction_solver
    title: str
    open_date: str
    close_date: str


class SurveyResponse(BaseModel):
    survey_window_id: str
    respondent_type: str  # FTE or Solver
    responses: Dict[str, int]  # question_id: score (1-5)


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


def calc_pillar_score(responses: dict, questions: list, pillar: int) -> float:
    pillar_qs = [q["id"] for q in questions if q["pillar"] == pillar]
    scores = [responses.get(qid, 0) for qid in pillar_qs if responses.get(qid)]
    if not scores:
        return 0.0
    return round((sum(scores) / (len(scores) * 5)) * 100, 1)


@router.get("/windows")
async def list_survey_windows(request: Request):
    user = await get_current_user(request)
    db = get_db()
    windows = await db.survey_windows.find({"tenant_id": "solvit"}).sort("open_date", -1).to_list(50)
    return [fmt(w) for w in windows]


@router.post("/windows")
async def create_survey_window(sw: SurveyWindowCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        **sw.model_dump(),
        "status": "Open",
        "response_count": 0,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.survey_windows.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.post("/launch-quick")
async def launch_quick_survey(request: Request):
    """One-click survey launch — creates the window, fires notifications + emails to target audience.
    Body: { survey_type: 'alignment_fte' | 'alignment_solver' | 'engagement_fte', period_label?: 'Q3 2026' }
    """
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    body = await request.json()
    survey_type = body.get("survey_type", "alignment_fte")
    period = body.get("period_label") or f"Q{((datetime.now(timezone.utc).month - 1) // 3) + 1} {datetime.now(timezone.utc).year}"

    db = get_db()
    is_solver = survey_type.endswith("solver")
    target_audience = "solver" if is_solver else "FTE"

    today = datetime.now(timezone.utc).date()
    close = today + timedelta(days=14)
    window_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "survey_type": survey_type,
        "title": f"{period} {'Solver' if is_solver else 'FTE'} Alignment Survey",
        "open_date": today.isoformat(),
        "close_date": close.isoformat(),
        "status": "Open",
        "response_count": 0,
        "target_audience": target_audience,
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.survey_windows.insert_one(window_doc)

    # Determine recipients
    if is_solver:
        recipients = await db.solvers.find({"tenant_id": "solvit", "lifecycle_state": "Active"}, {"_id": 0, "id": 1, "full_name": 1, "phone_number": 1}).to_list(500)
        recipient_emails = []
    else:
        active_states = ["Active", "Probation", "Onboarding", "On_Leave"]
        recipients = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": {"$in": active_states}}, {"_id": 0, "id": 1, "full_name": 1, "work_email": 1}).to_list(500)
        recipient_emails = [r.get("work_email") for r in recipients if r.get("work_email")]

    # Fire in-app notifications
    notif_docs = []
    for r in recipients:
        notif_docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "recipient_id": r.get("id"),
            "recipient_role": "employee" if not is_solver else "solver",
            "category": "Survey",
            "title": f"[{period}] {window_doc['title']}",
            "message": f"Your {period} alignment survey is now open. Please respond by {close.strftime('%d %b %Y')}. It takes 5 minutes.",
            "data": {"survey_window_id": window_doc["id"], "survey_type": survey_type},
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    if notif_docs:
        await db.notifications.insert_many(notif_docs)

    # Fire emails (best-effort — silent if provider not configured)
    email_results = {"sent": 0, "skipped": 0, "failed": 0}
    if recipient_emails:
        try:
            from utils.email_service import send_email, EmailDeliveryError
            for email in recipient_emails:
                try:
                    res = await send_email(
                        db, email,
                        subject=f"[Solvit] {period} Alignment Survey is now open",
                        html=f"""
                        <p>Hi,</p>
                        <p>Your <strong>{period}</strong> alignment survey is now open.</p>
                        <p>It takes about 5 minutes and is fully confidential. Please respond by <strong>{close.strftime('%d %b %Y')}</strong>.</p>
                        <p><a href='https://solvit-people-mgmt.preview.emergentagent.com/surveys'>Take the survey →</a></p>
                        <p style='color:#525252;font-size:12px'>Solvit People Platform</p>
                        """
                    )
                    if res.get("status") == "sent":
                        email_results["sent"] += 1
                    else:
                        email_results["skipped"] += 1
                except EmailDeliveryError:
                    email_results["failed"] += 1
        except Exception:
            pass

    return {
        "status": "success",
        "survey_window": {"id": window_doc["id"], "title": window_doc["title"], "open_date": window_doc["open_date"], "close_date": window_doc["close_date"]},
        "recipients": len(recipients),
        "notifications_sent": len(notif_docs),
        "emails": email_results,
        "period": period
    }


@router.get("/questions/{survey_type}")
async def get_survey_questions(survey_type: str, request: Request):
    user = await get_current_user(request)
    if survey_type in ["alignment_solver", "satisfaction_solver"]:
        return {"questions": SOLVER_ALIGNMENT_QUESTIONS, "survey_type": survey_type}
    return {"questions": FTE_ALIGNMENT_QUESTIONS, "survey_type": survey_type}


@router.post("/respond")
async def submit_response(resp: SurveyResponse, request: Request):
    user = await get_current_user(request)
    db = get_db()
    window = await db.survey_windows.find_one({"id": resp.survey_window_id})
    if not window:
        raise HTTPException(status_code=404, detail="Survey window not found")

    questions = SOLVER_ALIGNMENT_QUESTIONS if resp.respondent_type == "Solver" else FTE_ALIGNMENT_QUESTIONS

    p1 = calc_pillar_score(resp.responses, questions, 1)
    p2 = calc_pillar_score(resp.responses, questions, 2)
    p3 = calc_pillar_score(resp.responses, questions, 3)
    overall = round((p1 + p2 + p3) / 3, 1)

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "survey_window_id": resp.survey_window_id,
        "respondent_type": resp.respondent_type,
        "respondent_id": user["id"],
        "responses_json": resp.responses,
        "pillar_1_score": p1,
        "pillar_2_score": p2,
        "pillar_3_score": p3,
        "overall_alignment_score": overall,
        "submitted_at": datetime.now(timezone.utc).isoformat()
    }
    await db.survey_responses.insert_one(doc)
    await db.survey_windows.update_one({"id": resp.survey_window_id}, {"$inc": {"response_count": 1}})
    doc["_id"] = str(doc.get("_id", ""))
    return {"message": "Response submitted", "overall_score": overall}


@router.get("/results/{window_id}")
async def get_survey_results(window_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "executive"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    responses = await db.survey_responses.find({"survey_window_id": window_id}).to_list(500)
    if not responses:
        return {"window_id": window_id, "response_count": 0, "overall": 0, "pillar_1": 0, "pillar_2": 0, "pillar_3": 0}

    avg_p1 = round(sum(r.get("pillar_1_score", 0) for r in responses) / len(responses), 1)
    avg_p2 = round(sum(r.get("pillar_2_score", 0) for r in responses) / len(responses), 1)
    avg_p3 = round(sum(r.get("pillar_3_score", 0) for r in responses) / len(responses), 1)
    avg_overall = round(sum(r.get("overall_alignment_score", 0) for r in responses) / len(responses), 1)

    return {
        "window_id": window_id,
        "response_count": len(responses),
        "overall": avg_overall,
        "pillar_1": avg_p1,
        "pillar_2": avg_p2,
        "pillar_3": avg_p3,
        "pillar_labels": ["Environment", "Values", "Rewards"]
    }
