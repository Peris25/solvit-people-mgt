"""Solvit HR AI Assistant — full-platform HR copilot.

Capabilities:
- Live read access across every module (employees, leave, performance, training,
  recruitment, solvers, recognition, disciplinary, budget, onboarding,
  compliance, surveys, projects, retention, policies).
- Status look-ups by employee or team ("status of John's review", "Sarah's leave
  balance", "pending probation reviews", etc).
- Always grounds the LLM with a live platform snapshot + intent-specific deep
  dive context so answers reference current data, not hallucinated numbers.
- ACTIONABLE: detects action intents (approve leave, recognise, send email,
  assign training, mark task complete, reject leave) and emits a
  `proposed_action` payload the frontend renders as a confirmation card. The
  user must click Confirm before any write happens.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from database import get_db
from utils.auth import get_current_user
from routes import ai_actions
import os
import uuid
import re

router = APIRouter(prefix="/ai-agent", tags=["ai_agent"])


class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc.get("_id", ""))
    doc["_id"] = str(doc.get("_id", ""))
    return doc


# -------------------- DATA FETCHERS (tools the LLM is grounded with) --------------------

async def snapshot_headcount(db) -> Dict[str, Any]:
    emps = await db.employees.find({"tenant_id": "solvit"}).to_list(2000)
    active = [e for e in emps if (e.get("lifecycle_state") or "Active") not in ("Terminated", "Exited")]
    by_dept = {}
    by_state = {}
    for e in active:
        by_dept[e.get("department") or "Unassigned"] = by_dept.get(e.get("department") or "Unassigned", 0) + 1
        by_state[e.get("lifecycle_state") or "Active"] = by_state.get(e.get("lifecycle_state") or "Active", 0) + 1
    return {
        "total_active_fte": len(active),
        "total_records": len(emps),
        "by_department": by_dept,
        "by_state": by_state,
    }


async def snapshot_leave(db) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    iso_today = now.date().isoformat()
    pending = await db.leave_requests.count_documents({"tenant_id": "solvit", "status": {"$in": ["Pending_Manager", "Pending_HR"]}})
    approved_this_month = await db.leave_requests.count_documents({
        "tenant_id": "solvit", "status": "Approved",
        "created_at": {"$gte": now.replace(day=1).isoformat()}
    })
    # On leave today
    on_leave = await db.leave_requests.find({
        "tenant_id": "solvit", "status": "Approved",
        "start_date": {"$lte": iso_today}, "end_date": {"$gte": iso_today}
    }).to_list(50)
    on_leave_names = []
    for lr in on_leave[:10]:
        emp = await db.employees.find_one({"id": lr.get("employee_id")})
        on_leave_names.append((emp or {}).get("full_name") or lr.get("employee_id"))
    return {
        "pending_approval": pending,
        "approved_this_month": approved_this_month,
        "on_leave_today_count": len(on_leave),
        "on_leave_today_names": on_leave_names,
    }


async def snapshot_performance(db) -> Dict[str, Any]:
    total = await db.performance_reviews.count_documents({"tenant_id": "solvit"})
    by_status = {}
    cursor = db.performance_reviews.find({"tenant_id": "solvit"}, {"status": 1, "nine_box_placement": 1})
    by_nb = {}
    async for r in cursor:
        s = r.get("status") or "Unknown"
        by_status[s] = by_status.get(s, 0) + 1
        nb = r.get("nine_box_placement")
        if nb:
            by_nb[nb] = by_nb.get(nb, 0) + 1
    return {"total_reviews": total, "by_status": by_status, "nine_box_distribution": by_nb}


async def snapshot_recruitment(db) -> Dict[str, Any]:
    reqs = await db.recruitment_requests.find({"tenant_id": "solvit"}).to_list(500) if "recruitment_requests" in await db.list_collection_names() else []
    cands = await db.candidates.find({"tenant_id": "solvit"}).to_list(500) if "candidates" in await db.list_collection_names() else []
    by_stage = {}
    for c in cands:
        s = c.get("stage") or "New"
        by_stage[s] = by_stage.get(s, 0) + 1
    return {
        "open_requisitions": len([r for r in reqs if (r.get("status") or "Open") not in ("Closed", "Hired", "Cancelled")]),
        "total_requisitions": len(reqs),
        "candidates_total": len(cands),
        "candidates_by_stage": by_stage,
    }


async def snapshot_solvers(db) -> Dict[str, Any]:
    rows = await db.solvers.find({"tenant_id": "solvit"}).to_list(2000)
    by_tier = {}
    by_state = {}
    for s in rows:
        by_tier[s.get("performance_tier") or "—"] = by_tier.get(s.get("performance_tier") or "—", 0) + 1
        by_state[s.get("lifecycle_state") or "Active"] = by_state.get(s.get("lifecycle_state") or "Active", 0) + 1
    return {"total": len(rows), "by_tier": by_tier, "by_state": by_state}


async def snapshot_training(db) -> Dict[str, Any]:
    rows = await db.training_requests.find({"tenant_id": "solvit"}).to_list(500) if "training_requests" in await db.list_collection_names() else []
    by_status = {}
    for r in rows:
        s = r.get("status") or "Pending"
        by_status[s] = by_status.get(s, 0) + 1
    return {"total": len(rows), "by_status": by_status}


async def snapshot_recognition(db) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    first = now.replace(day=1).isoformat()
    return {
        "this_month": await db.recognitions.count_documents({"tenant_id": "solvit", "created_at": {"$gte": first}}),
        "total": await db.recognitions.count_documents({"tenant_id": "solvit"}),
    }


async def snapshot_disciplinary(db) -> Dict[str, Any]:
    rows = await db.disciplinary_cases.find({"tenant_id": "solvit"}).to_list(500) if "disciplinary_cases" in await db.list_collection_names() else []
    by_status = {}
    by_severity = {}
    for r in rows:
        by_status[r.get("status") or "Open"] = by_status.get(r.get("status") or "Open", 0) + 1
        by_severity[r.get("severity") or "—"] = by_severity.get(r.get("severity") or "—", 0) + 1
    return {"total": len(rows), "by_status": by_status, "by_severity": by_severity}


async def snapshot_budget(db) -> Dict[str, Any]:
    alloc = await db.budget_allocations.find({"tenant_id": "solvit"}).sort("year", -1).to_list(5)
    rows = [{"year": a.get("year"), "tier_unlocked": a.get("tier_unlocked"),
             "envelope_kes": a.get("envelope_kes"), "spent_kes": a.get("spent_kes"),
             "remaining_kes": a.get("remaining_kes")} for a in alloc]
    return {"recent": rows}


async def snapshot_onboarding(db) -> Dict[str, Any]:
    emps = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": {"$in": ["Probation", "Onboarding"]}}).to_list(200)
    return {"in_onboarding_or_probation": len(emps),
            "names": [e.get("full_name") for e in emps[:10]]}


async def compliance_status(db) -> List[str]:
    now = datetime.now(timezone.utc)
    day = now.day
    issues: List[str] = []
    # Probation reviews due
    emps = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Probation"}).to_list(50)
    for emp in emps:
        start = emp.get("start_date")
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                d = (now - start_dt.replace(tzinfo=timezone.utc)).days
                if 25 <= d <= 28: issues.append(f"PROBATION: {emp.get('full_name')} — Month-1 review due soon")
                elif 53 <= d <= 56: issues.append(f"PROBATION: {emp.get('full_name')} — Month-2 review due soon")
                elif 81 <= d <= 84: issues.append(f"PROBATION: {emp.get('full_name')} — Month-3 FINAL review due in 3 days")
            except Exception:
                pass
    # Pay bands
    pay_bands = await db.pay_bands.find({"tenant_id": "solvit"}).to_list(20) if "pay_bands" in await db.list_collection_names() else []
    band_map = {pb.get("band"): pb for pb in pay_bands}
    for emp in await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}).to_list(500):
        level = emp.get("role_level") or emp.get("job_level")
        salary = emp.get("current_salary_kes") or emp.get("salary_kes") or 0
        if level in band_map and salary and salary < band_map[level].get("min_kes", 0):
            issues.append(f"PAY BAND: {emp.get('full_name')} at {level} — KES {salary:,.0f} is below minimum")
    # Statutory deadlines
    if 8 <= day < 15: issues.append(f"NSSF/SHA remittance due in {15 - day} day(s) (15th cut-off)")
    if 2 <= day < 9:  issues.append(f"PAYE filing due in {9 - day} day(s) (9th cut-off)")
    return issues or ["All compliance checks passed."]


# -------------------- ENTITY-SPECIFIC LOOK-UPS --------------------

async def lookup_employee_status(db, query: str) -> Optional[Dict[str, Any]]:
    """Resolve a partial name and return a one-page status summary."""
    # Try to extract a likely name from the user's question
    tokens = [t for t in re.findall(r"[A-Z][a-z]+", query)]
    if not tokens:
        return None
    # Search by full_name regex
    pattern = "|".join(re.escape(t) for t in tokens[:3])
    emp = await db.employees.find_one({"tenant_id": "solvit", "full_name": {"$regex": pattern, "$options": "i"}})
    if not emp:
        return None
    emp_id = emp.get("id") or str(emp.get("_id"))
    # Recent leave
    leaves = await db.leave_requests.find({"tenant_id": "solvit", "employee_id": emp_id}).sort("created_at", -1).to_list(3)
    # Recent reviews
    reviews = await db.performance_reviews.find({"tenant_id": "solvit", "employee_id": emp_id}).sort("created_at", -1).to_list(2)
    # Recent training requests
    trainings = await db.training_requests.find({"tenant_id": "solvit", "employee_id": emp_id}).sort("created_at", -1).to_list(2) if "training_requests" in await db.list_collection_names() else []
    # Active disciplinary
    discipline = await db.disciplinary_cases.find({"tenant_id": "solvit", "employee_id": emp_id, "status": {"$ne": "Closed"}}).to_list(5) if "disciplinary_cases" in await db.list_collection_names() else []
    return {
        "id": emp_id,
        "full_name": emp.get("full_name"),
        "role_title": emp.get("role_title") or emp.get("job_title"),
        "department": emp.get("department"),
        "lifecycle_state": emp.get("lifecycle_state"),
        "start_date": emp.get("start_date"),
        "line_manager_id": emp.get("line_manager_id"),
        "recent_leave": [{"type": l.get("leave_type"), "status": l.get("status"),
                          "start": l.get("start_date"), "end": l.get("end_date"),
                          "days": l.get("working_days")} for l in leaves],
        "recent_reviews": [{"cycle": r.get("cycle_type") or r.get("cycle_label"),
                            "year": r.get("cycle_year"), "status": r.get("status"),
                            "overall_score": r.get("overall_score"),
                            "nine_box": r.get("nine_box_placement")} for r in reviews],
        "recent_trainings": [{"name": t.get("title") or t.get("name"), "status": t.get("status")} for t in trainings],
        "open_disciplinary": [{"summary": d.get("summary"), "severity": d.get("severity"), "status": d.get("status")} for d in discipline],
    }


# -------------------- INTENT ROUTER --------------------

INTENT_KEYWORDS = {
    "headcount":   ["headcount", "how many employees", "fte count", "team size", "by department", "department"],
    "leave":       ["leave", "annual leave", "sick", "maternity", "paternity", "off duty", "on holiday", "rollover"],
    "performance": ["performance", "review", "9-box", "nine box", "rating", "score", "kpi"],
    "recruitment": ["recruit", "candidate", "requisition", "hiring", "interview", "offer"],
    "solver":      ["solver", "inspector", "tier", "field team"],
    "training":    ["training", "l&d", "learning", "development", "course", "idp", "skill"],
    "recognition": ["recognition", "kudos", "shout out", "shout-out", "peer recognition"],
    "discipline":  ["discipline", "disciplinary", "warning", "pip", "hearing"],
    "budget":      ["budget", "envelope", "headroom", "salary increase", "bonus pool", "tier 1", "tier 2"],
    "onboarding":  ["onboarding", "probation", "new hire", "induction", "check-in"],
    "compliance":  ["compliance", "nssf", "sha", "paye", "deadline", "statutory", "remittance"],
    "policy":      ["policy", "policies", "handbook", "rules", "procedure", "guideline"],
}


def classify_intents(message: str) -> List[str]:
    m = message.lower()
    hits = []
    for intent, kws in INTENT_KEYWORDS.items():
        if any(k in m for k in kws):
            hits.append(intent)
    return hits


def has_entity_question(message: str) -> bool:
    m = message.lower()
    return any(p in m for p in ["status of", "what about", "where is", "how is", "show me", "check on"]) or bool(re.search(r"[A-Z][a-z]+ '?s\b", message))


async def search_policies(db, query: str) -> str:
    policies = await db.policies.find(
        {"tenant_id": "solvit", "$or": [
            {"title": {"$regex": query, "$options": "i"}},
            {"description": {"$regex": query, "$options": "i"}},
            {"content": {"$regex": query, "$options": "i"}}
        ]}
    ).to_list(5)
    if not policies:
        return "No policies matched that query."
    return "\n\n".join(
        f"**{p.get('title')}** (v{p.get('version','1.0')}, effective {p.get('effective_date','—')}): {p.get('description') or (p.get('content','')[:240])}"
        for p in policies
    )


async def build_context(db, message: str) -> str:
    """Return a markdown brief of relevant live data — kept compact (<3KB)."""
    intents = classify_intents(message)
    parts: List[str] = []
    # Always include a tiny snapshot
    hc = await snapshot_headcount(db)
    parts.append(f"PLATFORM SNAPSHOT:\n- Active FTE: {hc['total_active_fte']}\n- Departments: {', '.join(f'{k}={v}' for k,v in sorted(hc['by_department'].items()))}\n- Lifecycle: {', '.join(f'{k}={v}' for k,v in hc['by_state'].items())}")

    if "leave" in intents:
        lv = await snapshot_leave(db)
        parts.append(f"LEAVE:\n- Pending approval: {lv['pending_approval']}\n- Approved this month: {lv['approved_this_month']}\n- On leave today: {lv['on_leave_today_count']} ({', '.join(lv['on_leave_today_names']) or 'none'})")
    if "performance" in intents:
        pf = await snapshot_performance(db)
        parts.append(f"PERFORMANCE:\n- Total reviews: {pf['total_reviews']}\n- By status: {pf['by_status']}\n- 9-box: {pf['nine_box_distribution']}")
    if "recruitment" in intents:
        rc = await snapshot_recruitment(db)
        parts.append(f"RECRUITMENT:\n- Open requisitions: {rc['open_requisitions']}\n- Candidates: {rc['candidates_total']}\n- By stage: {rc['candidates_by_stage']}")
    if "solver" in intents:
        sv = await snapshot_solvers(db)
        parts.append(f"SOLVERS:\n- Total: {sv['total']}\n- By tier: {sv['by_tier']}\n- By state: {sv['by_state']}")
    if "training" in intents:
        tr = await snapshot_training(db)
        parts.append(f"TRAINING / L&D:\n- Total requests: {tr['total']}\n- By status: {tr['by_status']}")
    if "recognition" in intents:
        rg = await snapshot_recognition(db)
        parts.append(f"RECOGNITION:\n- This month: {rg['this_month']}\n- All-time: {rg['total']}")
    if "discipline" in intents:
        ds = await snapshot_disciplinary(db)
        parts.append(f"DISCIPLINARY:\n- Total cases: {ds['total']}\n- By status: {ds['by_status']}\n- By severity: {ds['by_severity']}")
    if "budget" in intents:
        bg = await snapshot_budget(db)
        parts.append(f"BUDGET:\n{bg['recent']}")
    if "onboarding" in intents:
        ob = await snapshot_onboarding(db)
        parts.append(f"ONBOARDING / PROBATION:\n- In progress: {ob['in_onboarding_or_probation']} ({', '.join(ob['names']) or 'none'})")
    if "compliance" in intents:
        issues = await compliance_status(db)
        parts.append("COMPLIANCE:\n- " + "\n- ".join(issues))
    if "policy" in intents:
        parts.append("RELEVANT POLICIES:\n" + await search_policies(db, message))

    # Entity-specific look-up
    if has_entity_question(message):
        info = await lookup_employee_status(db, message)
        if info:
            parts.append(f"EMPLOYEE DETAIL — {info['full_name']}:\n{info}")
    return "\n\n".join(parts)


SYSTEM_PROMPT = (
    "You are the Solvit HR AI Assistant, the trusted copilot for the HR & Administration "
    "team at Solvit Limited — a Kenyan tech-enabled vehicle inspection company. You assist "
    "the HR Admin (Jessica) and HR Manager across the FULL HR remit: employees, leave, "
    "performance, recruitment, onboarding, L&D, recognition, disciplinary, compensation, "
    "budget, surveys, retention, projects, policies, solvers, and compliance.\n\n"
    "Operating principles:\n"
    "1. Ground every answer in the LIVE platform snapshot provided in the context. Never "
    "   invent numbers, statuses, or names.\n"
    "2. When asked about a person, use the EMPLOYEE DETAIL block if present.\n"
    "3. Confirm the status of any in-flight item by quoting the live status text (e.g. "
    "   'Pending_Manager', 'Approved', 'Pending HR') verbatim.\n"
    "4. Be proactive: surface upcoming deadlines (probation reviews, NSSF/SHA/PAYE, "
    "   contract anniversaries) without being asked when they're relevant.\n"
    "5. Use KES for money, DD/MM/YYYY for dates, EAT for times, and reference the Kenyan "
    "   Employment Act 2007 where appropriate.\n"
    "6. Suggest the EXACT screen / button HR should click to complete the task (e.g. "
    "   'open /leave → Team Leave tab → Approve').\n"
    "7. If the user asks you to take an action that requires a click (approve, reject, "
    "   send), explain the steps; you can fetch data, not yet perform write operations. "
    "   Be transparent about this boundary.\n"
    "8. Keep answers concise (≤ 8 lines) unless the user asks for detail. Use bullet "
    "   points, no emojis."
)


# -------------------- ROUTES --------------------

@router.post("/chat")
async def chat_with_agent(msg: ChatMessage, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR Admin/Manager can use the AI Assistant")
    db = get_db()
    settings = await db.platform_settings.find_one({"tenant_id": "solvit"})
    conversation_id = msg.conversation_id or str(uuid.uuid4())

    await db.ai_conversations.insert_one({
        "tenant_id": "solvit", "conversation_id": conversation_id, "role": "user",
        "content": msg.message, "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # ----- Actionable intents short-circuit the LLM -----
    intent = ai_actions.detect_intent(msg.message)
    if intent and intent in ai_actions.INTENT_PROPOSERS:
        if not ai_actions.can_execute(intent, user["role"]):
            return {"conversation_id": conversation_id,
                    "response": f"Your role does not permit the `{intent}` action.",
                    "provider": "fallback"}
        proposer = ai_actions.INTENT_PROPOSERS[intent]
        proposed = await proposer(db, msg.message, user)
        if proposed.get("error"):
            await db.ai_conversations.insert_one({
                "tenant_id": "solvit", "conversation_id": conversation_id, "role": "assistant",
                "content": proposed["error"], "created_at": datetime.now(timezone.utc).isoformat()})
            return {"conversation_id": conversation_id, "response": proposed["error"], "provider": "live"}
        # Persist pending action so /execute can run it later
        await db.ai_pending_actions.insert_one({
            **proposed, "tenant_id": "solvit", "user_id": user["id"],
            "conversation_id": conversation_id, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        preface = f"Got it — I can do this for you. Please review and confirm:"
        await db.ai_conversations.insert_one({
            "tenant_id": "solvit", "conversation_id": conversation_id, "role": "assistant",
            "content": preface + "\n\n" + proposed["summary"],
            "created_at": datetime.now(timezone.utc).isoformat()})
        return {"conversation_id": conversation_id, "response": preface,
                "provider": "live", "proposed_action": proposed}

    # ----- Read-only Q&A flow (existing) -----
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    provider = (settings or {}).get("llm_provider") or "openai"
    model = (settings or {}).get("llm_model") or "gpt-5.2"
    api_key = (settings or {}).get("llm_api_key") or emergent_key

    context = await build_context(db, msg.message)
    response_text = ""

    if api_key:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=api_key, session_id=conversation_id, system_message=SYSTEM_PROMPT).with_model(provider, model)
            user_message = f"Live platform context (use this — do not hallucinate):\n{context}\n\nHR question: {msg.message}"
            resp = await chat.send_message(UserMessage(text=user_message))
            response_text = resp if isinstance(resp, str) else (resp.content if hasattr(resp, "content") else str(resp))
        except Exception as e:
            print(f"AI Assistant LLM error: {e}")
            response_text = _fallback_brief(context, msg.message)
    else:
        response_text = _fallback_brief(context, msg.message)

    await db.ai_conversations.insert_one({
        "tenant_id": "solvit", "conversation_id": conversation_id, "role": "assistant",
        "content": response_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {
        "conversation_id": conversation_id,
        "response": response_text,
        "provider": provider if api_key else "fallback",
    }


def _fallback_brief(context: str, message: str) -> str:
    """Used when no LLM key is configured — returns a structured live-data brief."""
    return (
        f"AI Assistant (deterministic mode — no LLM configured).\n\nHere is the live platform "
        f"context most relevant to your question:\n\n{context}\n\n"
        f"_Configure an LLM provider under Masters Settings → AI to unlock conversational answers._"
    )


@router.get("/compliance-check")
async def run_compliance_check(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    issues = await compliance_status(db)
    return {"status": "\n".join(issues), "issues": issues, "checked_at": datetime.now(timezone.utc).isoformat()}


@router.get("/snapshot")
async def daily_brief(request: Request):
    """Single-call daily brief for the HR Admin landing page."""
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    return {
        "headcount": await snapshot_headcount(db),
        "leave": await snapshot_leave(db),
        "performance": await snapshot_performance(db),
        "recruitment": await snapshot_recruitment(db),
        "solvers": await snapshot_solvers(db),
        "training": await snapshot_training(db),
        "recognition": await snapshot_recognition(db),
        "disciplinary": await snapshot_disciplinary(db),
        "budget": await snapshot_budget(db),
        "onboarding": await snapshot_onboarding(db),
        "compliance_issues": await compliance_status(db),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/employee-status")
async def employee_status(request: Request, query: str):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager", "line_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    info = await lookup_employee_status(db, query)
    if not info:
        raise HTTPException(status_code=404, detail="No employee matched that query")
    return info


@router.get("/conversations")
async def get_conversations(request: Request, limit: int = 20):
    user = await get_current_user(request)
    db = get_db()
    messages = await db.ai_conversations.find(
        {"tenant_id": "solvit", "user_id": user["id"]}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return [fmt(m) for m in messages]


# ============================================================
# Actionable AI — confirm / execute / cancel proposed actions
# ============================================================

@router.post("/actions/{action_id}/execute")
async def execute_action(action_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    pending = await db.ai_pending_actions.find_one({"id": action_id, "status": "pending"})
    if not pending:
        raise HTTPException(status_code=404, detail="Action not found or already processed")
    if pending.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the proposer can confirm this action")
    if not ai_actions.can_execute(pending["kind"], user["role"]):
        raise HTTPException(status_code=403, detail="Your role cannot execute this action")
    expires = pending.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                raise HTTPException(status_code=410, detail="This action has expired — please ask again")
        except ValueError:
            pass

    # Allow the UI to PATCH editable params (e.g. reason text, message)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and body.get("params_override"):
        pending["params"].update(body["params_override"])

    executor = ai_actions.EXECUTORS.get(pending["kind"])
    if not executor:
        raise HTTPException(status_code=400, detail=f"No executor registered for {pending['kind']}")
    try:
        result = await executor(db, pending["params"], user)
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    now = datetime.now(timezone.utc).isoformat()
    await db.ai_pending_actions.update_one(
        {"id": action_id},
        {"$set": {"status": "executed" if result.get("ok") else "failed",
                  "executed_at": now, "executed_by": user["id"], "result": result}}
    )
    await db.ai_actions_audit.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "action_id": action_id, "kind": pending["kind"], "risk": pending.get("risk"),
        "summary": pending.get("summary"), "params": pending.get("params"),
        "result": result, "outcome": "executed" if result.get("ok") else "failed",
        "by_user_id": user["id"], "by_user_name": user.get("full_name") or user.get("email"),
        "by_role": user.get("role"),
        "conversation_id": pending.get("conversation_id"),
        "timestamp": now,
    })
    return {"action_id": action_id, "outcome": "executed" if result.get("ok") else "failed",
            "result": result}


@router.post("/actions/{action_id}/cancel")
async def cancel_action(action_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    pending = await db.ai_pending_actions.find_one({"id": action_id, "status": "pending"})
    if not pending:
        raise HTTPException(status_code=404, detail="Action not found")
    now = datetime.now(timezone.utc).isoformat()
    await db.ai_pending_actions.update_one({"id": action_id},
        {"$set": {"status": "cancelled", "cancelled_at": now, "cancelled_by": user["id"]}})
    await db.ai_actions_audit.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": "solvit",
        "action_id": action_id, "kind": pending["kind"], "risk": pending.get("risk"),
        "summary": pending.get("summary"), "params": pending.get("params"),
        "outcome": "cancelled", "by_user_id": user["id"],
        "by_user_name": user.get("full_name") or user.get("email"),
        "by_role": user.get("role"), "timestamp": now,
    })
    return {"action_id": action_id, "outcome": "cancelled"}


@router.get("/actions/audit")
async def actions_audit(request: Request, limit: int = 50):
    user = await get_current_user(request)
    if user["role"] not in ("hr_admin", "hr_manager", "it_admin"):
        raise HTTPException(status_code=403, detail="HR / IT Admin only")
    db = get_db()
    rows = await db.ai_actions_audit.find({"tenant_id": "solvit"}).sort("timestamp", -1).to_list(min(limit, 200))
    for r in rows:
        r.pop("_id", None)
    return rows
