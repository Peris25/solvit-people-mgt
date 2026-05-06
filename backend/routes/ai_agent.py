from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

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


async def get_llm_settings(db):
    """Get configured LLM settings"""
    settings = await db.platform_settings.find_one({"tenant_id": "solvit"})
    if not settings:
        return None
    return settings


async def search_policies(db, query: str) -> str:
    """Simple policy search for RAG"""
    policies = await db.policies.find(
        {"tenant_id": "solvit", "$or": [
            {"title": {"$regex": query, "$options": "i"}},
            {"description": {"$regex": query, "$options": "i"}},
            {"content": {"$regex": query, "$options": "i"}}
        ]}
    ).to_list(5)
    if not policies:
        return "No relevant policies found."
    result = []
    for p in policies:
        result.append(f"**{p.get('title')}** (v{p.get('version', '1.0')}, effective {p.get('effective_date', 'N/A')}): {p.get('description', '')}")
    return "\n\n".join(result)


async def get_compliance_status(db) -> str:
    """Get compliance guardian status"""
    now = datetime.now(timezone.utc)
    month = now.month
    day = now.day

    issues = []

    # Check probation reviews due
    from dateutil.relativedelta import relativedelta
    emps = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Probation"}).to_list(50)
    for emp in emps:
        start = emp.get("start_date")
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                days_in_probation = (now - start_dt.replace(tzinfo=timezone.utc)).days
                if 25 <= days_in_probation <= 28:
                    issues.append(f"PROBATION REVIEW DUE: {emp.get('full_name')} — Month 1 review due soon")
                elif 53 <= days_in_probation <= 56:
                    issues.append(f"PROBATION REVIEW DUE: {emp.get('full_name')} — Month 2 review due soon")
                elif 81 <= days_in_probation <= 84:
                    issues.append(f"PROBATION REVIEW DUE: {emp.get('full_name')} — Month 3 FINAL review due in 3 days")
            except Exception:
                pass

    # Check pay band compliance
    pay_bands = await db.pay_bands.find({"tenant_id": "solvit"}).to_list(10)
    band_map = {pb["band"]: pb for pb in pay_bands}
    all_emps = await db.employees.find({"tenant_id": "solvit", "lifecycle_state": "Active"}).to_list(200)
    for emp in all_emps:
        level = emp.get("role_level")
        salary = emp.get("current_salary_kes", 0) or 0
        if level in band_map and salary < band_map[level]["min_kes"]:
            issues.append(f"PAY BAND ALERT: {emp.get('full_name')} at {level} — salary KES {salary:,} is below minimum KES {band_map[level]['min_kes']:,}")

    # Check NSSF/SHA remittance
    if day >= 8 and day < 15:
        days_remaining = 15 - day
        issues.append(f"NSSF/SHA DEADLINE: {days_remaining} days remaining (15th of month)")

    if day >= 2 and day < 9:
        days_remaining = 9 - day
        issues.append(f"PAYE FILING DEADLINE: {days_remaining} days remaining (9th of month)")

    if not issues:
        return "All compliance checks passed. No urgent issues found."
    return "\n".join(f"⚠️ {issue}" for issue in issues)


@router.post("/chat")
async def chat_with_agent(msg: ChatMessage, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Only HR Admin can use AI Agent")
    db = get_db()
    settings = await get_llm_settings(db)
    conversation_id = msg.conversation_id or str(uuid.uuid4())

    # Save user message
    await db.ai_conversations.insert_one({
        "tenant_id": "solvit",
        "conversation_id": conversation_id,
        "role": "user",
        "content": msg.message,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Determine intent
    message_lower = msg.message.lower()
    is_policy_query = any(word in message_lower for word in ["policy", "leave", "conduct", "rules", "handbook", "procedure", "guideline"])
    is_compliance_check = any(word in message_lower for word in ["compliance", "nssf", "sha", "paye", "probation", "overdue", "deadline", "check"])

    response_text = ""

    # Try to use configured LLM
    if settings and settings.get("llm_provider") and settings.get("llm_api_key"):
        try:
            provider = settings["llm_provider"]
            api_key = settings["llm_api_key"]

            # Build context
            context_parts = []
            if is_policy_query:
                policy_context = await search_policies(db, msg.message)
                context_parts.append(f"RELEVANT POLICIES:\n{policy_context}")
            if is_compliance_check:
                compliance_context = await get_compliance_status(db)
                context_parts.append(f"COMPLIANCE STATUS:\n{compliance_context}")

            system_prompt = """You are the Solvit HR AI Agent, an intelligent assistant for the HR & Administration team at Solvit Limited, a Kenyan vehicle inspection company. 

You help HR with:
1. Policy Q&A — answering questions about company policies using the policy library
2. Compliance Guardian — proactive alerts about probation deadlines, pay band compliance, NSSF/SHA/PAYE deadlines
3. Employee lifecycle guidance
4. Performance and retention insights

Always be concise, professional, and Kenya-specific (use KES, DD/MM/YYYY dates, reference Kenyan Employment Act 2007 where relevant).
For compliance alerts, be proactive and specific. For policy queries, cite the relevant policy."""

            user_message = msg.message
            if context_parts:
                user_message = f"Context:\n{chr(10).join(context_parts)}\n\nUser question: {msg.message}"

            from emergentintegrations.llm.chat import LlmChat, UserMessage

            if provider == "openai":
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                chat = LlmChat(api_key=api_key, session_id=conversation_id, system_message=system_prompt)
                response = await chat.send_message(UserMessage(content=user_message))
                response_text = response.content if hasattr(response, 'content') else str(response)
            elif provider == "anthropic":
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                chat = LlmChat(api_key=api_key, session_id=conversation_id, system_message=system_prompt, provider="anthropic")
                response = await chat.send_message(UserMessage(content=user_message))
                response_text = response.content if hasattr(response, 'content') else str(response)
            elif provider == "gemini":
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                chat = LlmChat(api_key=api_key, session_id=conversation_id, system_message=system_prompt, provider="gemini")
                response = await chat.send_message(UserMessage(content=user_message))
                response_text = response.content if hasattr(response, 'content') else str(response)
            else:
                response_text = await _fallback_response(db, msg.message, is_policy_query, is_compliance_check)
        except Exception as e:
            print(f"AI Agent LLM error: {e}")
            response_text = await _fallback_response(db, msg.message, is_policy_query, is_compliance_check)
    else:
        response_text = await _fallback_response(db, msg.message, is_policy_query, is_compliance_check)

    # Save assistant response
    await db.ai_conversations.insert_one({
        "tenant_id": "solvit",
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": response_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {
        "conversation_id": conversation_id,
        "response": response_text,
        "provider": settings.get("llm_provider", "fallback") if settings else "fallback"
    }


async def _fallback_response(db, message: str, is_policy_query: bool, is_compliance_check: bool) -> str:
    """Deterministic fallback when LLM not configured"""
    if is_compliance_check:
        return await get_compliance_status(db)
    if is_policy_query:
        policy_context = await search_policies(db, message)
        return f"Here is what I found in the Policy Library:\n\n{policy_context}\n\nTo get more detailed AI-powered responses, configure your LLM provider in Settings."
    # General helpful response
    compliance = await get_compliance_status(db)
    return f"""I'm the Solvit HR AI Agent. I can help you with:

1. **Policy Q&A** — Ask me about any company policy
2. **Compliance Checks** — Ask me about upcoming deadlines

**Current Compliance Status:**
{compliance}

_Note: Configure your LLM provider (OpenAI/Anthropic/Gemini) in Settings for full AI capabilities._"""


@router.get("/compliance-check")
async def run_compliance_check(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["hr_admin", "hr_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    db = get_db()
    status = await get_compliance_status(db)
    return {"status": status, "checked_at": datetime.now(timezone.utc).isoformat()}


@router.get("/conversations")
async def get_conversations(request: Request, limit: int = 20):
    user = await get_current_user(request)
    db = get_db()
    messages = await db.ai_conversations.find(
        {"tenant_id": "solvit", "user_id": user["id"]}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return [fmt(m) for m in messages]
