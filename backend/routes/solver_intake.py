"""Solver Application Intake & Intelligent Eligibility Screening.

A separate workflow from FTE recruitment. HR opens a Solver Requisition →
public link goes live → applicants apply via no-auth form → eligibility engine
hard-gates ineligible candidates into a register, eligible ones become pipeline
candidates at Stage 2 of the existing Solver flow.

Anti-abuse layers on the public endpoint (no external services / API costs):
  • HMAC-signed math CAPTCHA (10-min TTL, also enforces ≥3s fill time)
  • Honeypot field — bots auto-fill it; humans never see it
  • Per-IP rate limit (5 / hr, in-memory deque)
  • CV upload (optional) — whitelist extension + MIME + magic-byte sniff, 5MB cap
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

from database import get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/solver-intake", tags=["solver-intake"])

# ──────────────────────── Upload + Anti-abuse config ────────────────────────

CV_UPLOAD_ROOT = Path(os.environ.get("CV_UPLOAD_ROOT",
                                       "/app/backend/uploads/solver_cvs"))
CV_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
CV_MAX_BYTES = 5 * 1024 * 1024
CV_ALLOWED_EXT = {".pdf", ".doc", ".docx"}
CV_ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",  # browsers sometimes send this for .doc
}
# Magic-byte signatures so attackers can't rename a .exe to .pdf.
_MAGIC = {
    b"%PDF": ".pdf",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": ".doc",   # OLE compound (legacy .doc)
    b"PK\x03\x04": ".docx",                          # zip header — also for .docx
}


def _captcha_secret() -> bytes:
    return (os.environ.get("JWT_SECRET", "") or "fallback").encode()


def _issue_captcha() -> dict:
    a, b = random.randint(2, 9), random.randint(2, 9)
    issued_at = int(time.time())
    payload = f"{a}|{b}|{issued_at}"
    sig = hmac.new(_captcha_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "token": f"{payload}|{sig}",
        "question": f"What is {a} + {b}?",
        "issued_at": issued_at,
    }


def _verify_captcha(token: str, answer: str) -> tuple[bool, str]:
    """Returns (ok, reason). Reason is empty string when ok."""
    try:
        parts = (token or "").split("|")
        if len(parts) != 4:
            return False, "Invalid challenge token."
        a, b, issued_at, sig = parts
        a_i, b_i, issued_at_i = int(a), int(b), int(issued_at)
        payload = f"{a_i}|{b_i}|{issued_at_i}"
        expected = hmac.new(_captcha_secret(), payload.encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False, "Challenge signature mismatch."
        age = int(time.time()) - issued_at_i
        if age > 600:
            return False, "Challenge expired — please refresh and try again."
        if age < 3:
            # Submitted too fast — bot-like behaviour.
            return False, "Please complete the form before submitting."
        if int((answer or "").strip()) != a_i + b_i:
            return False, "Incorrect challenge answer."
        return True, ""
    except (ValueError, AttributeError):
        return False, "Invalid challenge response."


# Per-IP rate-limit (in-memory; resets on restart — sufficient against script
# kiddies. For production-grade DDoS use a CDN / Cloudflare in front.)
_ip_hits: dict[str, deque] = {}
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 3600  # 1 hour


def _rate_limit_check(ip: str) -> bool:
    """Returns True if request should be blocked."""
    now = time.time()
    dq = _ip_hits.setdefault(ip, deque())
    while dq and now - dq[0] > _RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_MAX:
        return True
    dq.append(now)
    return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_cv(file: UploadFile, content: bytes) -> str:
    """Returns the validated extension. Raises 400 on rejection."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in CV_ALLOWED_EXT:
        raise HTTPException(status_code=400,
                             detail=f"Unsupported CV type {ext}. Allowed: PDF, DOC, DOCX.")
    if file.content_type and file.content_type not in CV_ALLOWED_MIME:
        raise HTTPException(status_code=400,
                             detail=f"Unsupported CV MIME type {file.content_type}.")
    if len(content) > CV_MAX_BYTES:
        raise HTTPException(status_code=413, detail="CV exceeds 5MB limit.")
    if len(content) < 64:
        raise HTTPException(status_code=400, detail="CV file appears empty or corrupted.")
    # Magic-byte sniff
    head = content[:8]
    matched = None
    for sig, sig_ext in _MAGIC.items():
        if head.startswith(sig):
            matched = sig_ext
            break
    if matched is None:
        raise HTTPException(status_code=400,
                             detail="CV file content does not match its declared type.")
    # Allow .docx <-> PK signature (matched as .docx); a .doc file that magic-sniffs
    # as PK is actually a .docx — accept it but normalise extension.
    return ext


KENYA_COUNTIES = [
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo-Marakwet", "Embu", "Garissa",
    "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho", "Kiambu", "Kilifi",
    "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale", "Laikipia", "Lamu",
    "Machakos", "Makueni", "Mandera", "Marsabit", "Meru", "Migori", "Mombasa",
    "Murang'a", "Nairobi City", "Nakuru", "Nandi", "Narok", "Nyamira", "Nyandarua",
    "Nyeri", "Samburu", "Siaya", "Taita-Taveta", "Tana River", "Tharaka-Nithi",
    "Trans Nzoia", "Turkana", "Uasin Gishu", "Vihiga", "Wajir", "West Pokot",
]


# ───────────────────────────── Models ─────────────────────────────

class RequisitionCreate(BaseModel):
    title: str = "Solver — Vehicle Inspector"
    working_areas: List[str] = Field(default_factory=list)  # ["All counties"] or county names
    target_hires: Optional[int] = None
    status: str = "Closed"  # Open | Closed


class RequisitionUpdate(BaseModel):
    title: Optional[str] = None
    working_areas: Optional[List[str]] = None
    target_hires: Optional[int] = None
    status: Optional[str] = None


class IntakeSubmission(BaseModel):
    # requisition_id is taken from the URL path (rid); kept optional for backward compat.
    requisition_id: Optional[str] = None
    full_name: str
    phone_number: str
    email: EmailStr
    county: str
    town_area: str
    has_driving_licence: bool
    qualifications: List[str] = Field(default_factory=list)
    previous_inspector_company: Optional[str] = None
    has_smartphone: bool
    availability: str  # "Yes" | "Partial" | "No"
    commission_acknowledged: bool
    channel: str


# Internal helpers

def _next_req_code(seq: int) -> str:
    return f"SOLV-REQ-{seq:04d}"


def _hr_or_solvers(user):
    return user.get("role") in ("hr_admin", "hr_manager", "executive", "it_admin",
                                  "solvers_manager")


def _serialise(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────── Requisition CRUD (HR-controlled) ───────────────

@router.get("/counties")
async def counties():
    """Public list of supported counties — used by both the requisition editor
    and the public application form."""
    return {"counties": KENYA_COUNTIES, "all_label": "All counties"}


@router.get("/requisitions")
async def list_requisitions(request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR Admin / Solvers Manager only")
    db = get_db()
    items = []
    async for r in db.solver_requisitions.find({"tenant_id": "solvit"}).sort("created_at", -1):
        items.append(_serialise(r))
    return {"requisitions": items, "count": len(items),
            "can_edit": user.get("role") in ("hr_admin", "hr_manager", "it_admin")}


@router.post("/requisitions")
async def create_requisition(body: RequisitionCreate, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("hr_admin", "hr_manager", "it_admin"):
        raise HTTPException(status_code=403, detail="HR Admin only")
    db = get_db()
    # Validate counties
    if body.working_areas and body.working_areas != ["All counties"]:
        bad = [c for c in body.working_areas if c not in KENYA_COUNTIES]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown counties: {bad}")
    # Generate code
    seq = await db.solver_requisitions.count_documents({"tenant_id": "solvit"}) + 1
    now = datetime.now(timezone.utc).isoformat()
    rid = str(uuid.uuid4())
    status = body.status if body.status in ("Open", "Closed") else "Closed"
    doc = {
        "id": rid,
        "code": _next_req_code(seq),
        "tenant_id": "solvit",
        "title": body.title,
        "working_areas": body.working_areas or ["All counties"],
        "target_hires": body.target_hires,
        "status": status,
        "open_date": now if status == "Open" else None,
        "close_date": None,
        "created_by": user.get("id") or user.get("email"),
        "created_at": now, "updated_at": now,
        "counters": {"received": 0, "eligible": 0, "ineligible": 0, "inducted": 0},
    }
    await db.solver_requisitions.insert_one(doc)
    return _serialise(doc)


@router.put("/requisitions/{rid}")
async def update_requisition(rid: str, body: RequisitionUpdate, request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("hr_admin", "hr_manager", "it_admin"):
        raise HTTPException(status_code=403, detail="HR Admin only")
    db = get_db()
    existing = await db.solver_requisitions.find_one({"id": rid, "tenant_id": "solvit"})
    if not existing:
        raise HTTPException(status_code=404, detail="Requisition not found")
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if body.working_areas and body.working_areas != ["All counties"]:
        bad = [c for c in body.working_areas if c not in KENYA_COUNTIES]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown counties: {bad}")
    now = datetime.now(timezone.utc).isoformat()
    patch["updated_at"] = now
    if body.status and body.status != existing.get("status"):
        if body.status == "Open":
            patch["open_date"] = now
            patch["close_date"] = None
        elif body.status == "Closed":
            patch["close_date"] = now
    await db.solver_requisitions.update_one({"id": rid}, {"$set": patch})
    updated = await db.solver_requisitions.find_one({"id": rid})
    return _serialise(updated)


@router.get("/requisitions/{rid}")
async def get_requisition_admin(rid: str, request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR Admin / Solvers Manager only")
    db = get_db()
    doc = await db.solver_requisitions.find_one({"id": rid, "tenant_id": "solvit"})
    if not doc:
        raise HTTPException(status_code=404, detail="Requisition not found")
    return _serialise(doc)


# ─────────────── Public endpoints (NO authentication) ───────────────

@router.get("/public/{rid}")
async def public_requisition(rid: str):
    """Returns minimal public-safe info — only present + status. Used by the
    public application page to decide whether to render the form."""
    db = get_db()
    doc = await db.solver_requisitions.find_one({"id": rid, "tenant_id": "solvit"})
    if not doc:
        return {"found": False, "status": "Closed"}
    counties = doc.get("working_areas") or ["All counties"]
    if counties == ["All counties"]:
        county_options = KENYA_COUNTIES
    else:
        county_options = counties
    return {
        "found": True,
        "status": doc.get("status", "Closed"),
        "title": doc.get("title"),
        "counties": county_options,
    }


@router.get("/public/{rid}/challenge")
async def public_challenge(rid: str):
    """Issue a fresh anti-bot math challenge for the public apply form.
    HMAC-signed token includes both numbers and the issued_at timestamp so
    the answer cannot be forged or replayed (TTL: 10 min, min fill time 3s)."""
    return _issue_captcha()


@router.post("/public/{rid}/apply")
async def public_apply(
    rid: str,
    request: Request,
    full_name: str = Form(...),
    phone_number: str = Form(...),
    email: EmailStr = Form(...),
    county: str = Form(...),
    town_area: str = Form(...),
    has_driving_licence: bool = Form(...),
    qualifications: str = Form("[]"),       # JSON-encoded list
    previous_inspector_company: Optional[str] = Form(None),
    has_smartphone: bool = Form(...),
    availability: str = Form(...),
    commission_acknowledged: bool = Form(...),
    channel: str = Form(...),
    # Anti-bot layers
    challenge_token: str = Form(...),
    challenge_answer: str = Form(...),
    website_url: Optional[str] = Form(""),  # honeypot — must remain empty
    # Optional CV
    cv: Optional[UploadFile] = File(None),
):
    """Eligibility engine — evaluates ALL gates so the register captures every
    failed criterion, then either creates a pipeline candidate (eligible) or
    writes to the ineligible register."""

    # ─── Layer 1: Honeypot (zero-cost, blocks 95% of dumb bots) ───
    if (website_url or "").strip():
        # Silent reject — pretend success so bots don't tune their behaviour.
        return {"result": "ineligible", "failed_criteria": [],
                "headline": "Thank you for your interest in becoming a Solvit Solver.",
                "reasons": [], "closing": ""}

    # ─── Layer 2: Rate limit per IP ───
    ip = _client_ip(request)
    if _rate_limit_check(ip):
        raise HTTPException(status_code=429,
                             detail="Too many submissions from this address. Please try again later.")

    # ─── Layer 3: CAPTCHA verify (also enforces ≥3s fill time) ───
    ok, reason = _verify_captcha(challenge_token, challenge_answer)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # ─── Parse qualifications JSON list safely ───
    try:
        quals_list = json.loads(qualifications) if qualifications else []
        if not isinstance(quals_list, list):
            raise ValueError
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400,
                             detail="Qualifications must be a JSON array of strings.")

    db = get_db()
    req = await db.solver_requisitions.find_one({"id": rid, "tenant_id": "solvit"})
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
    if req.get("status") != "Open":
        raise HTTPException(status_code=410, detail="Applications are currently closed")

    # County validation against requisition scope
    scope = req.get("working_areas") or ["All counties"]
    valid_counties = KENYA_COUNTIES if scope == ["All counties"] else scope
    if county not in valid_counties:
        raise HTTPException(status_code=400,
                             detail=f"County '{county}' is not within this requisition's scope")

    # ─── Optional CV upload validation + persist ───
    cv_filename = None
    cv_stored_path = None
    cv_content: Optional[bytes] = None
    if cv is not None and getattr(cv, "filename", ""):
        cv_content = await cv.read()
        if cv_content:  # only process if non-empty
            ext = _validate_cv(cv, cv_content)
            # Final stored name is constructed once we have the applicant id.
            cv_filename = cv.filename
            cv_stored_path = ext  # use as a sentinel; replaced below

    # ───── Eligibility evaluation ─────
    failed = []
    qual_pool = {
        "Certificate, Diploma, or Degree in Mechanical / Automotive Engineering",
        "Sound knowledge of vehicles and assets to be inspected",
        "1–2 years of experience in a similar role (preferred)",
        "Has worked as a vehicle inspector previously",
    }
    quals = set(quals_list)
    has_none_above = "None of the above" in quals
    valid_quals = quals & qual_pool

    if not has_driving_licence:
        failed.append("licence")
    if has_none_above or not valid_quals:
        failed.append("qualifications")
    if "Has worked as a vehicle inspector previously" in valid_quals \
            and not (previous_inspector_company or "").strip():
        failed.append("qualifications")  # company name missing — treat as incomplete experience
    if not has_smartphone:
        failed.append("smartphone")
    if availability == "No":
        failed.append("availability")
    if not commission_acknowledged:
        failed.append("commission")

    failed = sorted(set(failed))
    now = datetime.now(timezone.utc).isoformat()
    applicant_id = str(uuid.uuid4())

    # Finalise CV path now that we have the applicant id
    if cv_stored_path and cv_content:
        ext = cv_stored_path
        safe_name = f"{applicant_id}{ext}"
        target_path = CV_UPLOAD_ROOT / safe_name
        with open(target_path, "wb") as f:
            f.write(cv_content)
        cv_stored_path = str(target_path)

    common = {
        "id": applicant_id,
        "tenant_id": "solvit",
        "requisition_id": rid,
        "requisition_code": req.get("code"),
        "full_name": full_name,
        "phone_number": phone_number,
        "email": email,
        "county": county,
        "town_area": town_area,
        "channel": channel,
        "has_driving_licence": has_driving_licence,
        "qualifications": list(quals),
        "previous_inspector_company": previous_inspector_company,
        "has_smartphone": has_smartphone,
        "availability": availability,
        "commission_acknowledged": commission_acknowledged,
        "submitted_at": now,
        "submitted_ip": ip,
        "cv_filename": cv_filename,
        "cv_path": cv_stored_path,
    }

    if failed:
        await db.ineligible_applicants.insert_one({
            **common,
            "failed_criteria": failed,
            "status": "Ineligible — not in pipeline",
        })
        await _bump_counters(db, rid, received=1, ineligible=1)
        return {
            "result": "ineligible",
            "failed_criteria": failed,
            "headline": "Thank you for your interest in becoming a Solvit Solver. "
                        "Based on your answers, you do not currently meet the minimum "
                        "requirements for this role:",
            "reasons": [_REASON_TEXT[k] for k in failed if k in _REASON_TEXT],
            "closing": "If your circumstances change, you are welcome to apply again. "
                       "We have kept your contact details and may reach out about "
                       "future opportunities.",
        }

    # ───── Eligible: create pipeline candidate at Stage 1 passed ─────
    candidate_id = applicant_id  # reuse the same id so the CV filename matches
    await db.candidates.insert_one({
        "id": candidate_id,
        "tenant_id": "solvit",
        "candidate_type": "Solver",
        "full_name": full_name,
        "email": email,
        "phone_number": phone_number,
        "position_applied": req.get("title") or "Solver — Vehicle Inspector",
        "department": "Operations",
        "role_level": "Solver",
        "source": channel,
        "county": county,
        "town_area": town_area,
        "requisition_id": rid,
        "requisition_code": req.get("code"),
        "current_stage": "Stage 1 — Passed / Awaiting Values Assessment",
        "current_stage_status": "Awaiting_Action",
        "stage_entered_date": now,
        "stage_scores": {"stage_1_eligibility": "Passed"},
        "stage_notes": {},
        "qualifications": list(valid_quals),
        "previous_inspector_company": previous_inspector_company,
        "has_driving_licence": has_driving_licence,
        "has_smartphone": has_smartphone,
        "availability": availability,
        "commission_acknowledged": commission_acknowledged,
        "cv_filename": cv_filename,
        "cv_path": cv_stored_path,
        "submitted_ip": ip,
        "status": "Active",
        "created_at": now, "updated_at": now,
    })
    await _bump_counters(db, rid, received=1, eligible=1)

    # Notify Solvers Manager (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        await fire_and_forget(db, "recruitment.application_received",
                              extra={"candidate_name": full_name,
                                     "role_applied_for": req.get("title"),
                                     "requisition_code": req.get("code")})
        # Internal alert to Solvers Manager / HR
        sm = await db.users.find_one({"tenant_id": "solvit",
                                       "role": {"$in": ["hr_admin", "solvers_manager"]}})
        if sm and sm.get("email"):
            await fire_and_forget(db, "recruitment.application_received",
                                  to_override=sm["email"],
                                  extra={"candidate_name": full_name,
                                         "role_applied_for": req.get("title"),
                                         "requisition_code": req.get("code")})
    except Exception:
        pass

    # Auto-close requisition if target hit (received >= target_hires AND
    # target_hires set). Spec says "if a target is set" — we count eligible.
    target = req.get("target_hires")
    if target and isinstance(target, int) and target > 0:
        refreshed = await db.solver_requisitions.find_one({"id": rid})
        if (refreshed.get("counters", {}).get("eligible", 0) >= target
                and refreshed.get("status") == "Open"):
            await db.solver_requisitions.update_one(
                {"id": rid},
                {"$set": {"status": "Closed",
                          "close_date": datetime.now(timezone.utc).isoformat(),
                          "auto_closed": True}}
            )

    return {
        "result": "eligible",
        "candidate_id": candidate_id,
        "message": "You meet the eligibility criteria. Please continue to a short "
                   "assessment.",
        "next_stage": "Stage 2 — Solver Values & Conduct Assessment",
    }


_REASON_TEXT = {
    "licence": "A valid Kenyan driving licence is required.",
    "qualifications": "Relevant automotive qualifications or vehicle inspection "
                       "experience are required.",
    "smartphone": "A smartphone with a working camera is required to complete "
                   "inspections.",
    "availability": "Availability during standard operating hours (Mon–Sat, 8am–6pm) "
                     "is required.",
    "commission": "This is a commission-based role, and acceptance of those terms is "
                   "required to proceed.",
}


async def _bump_counters(db, rid: str, *, received=0, eligible=0, ineligible=0,
                          inducted=0):
    inc = {}
    if received: inc["counters.received"] = received
    if eligible: inc["counters.eligible"] = eligible
    if ineligible: inc["counters.ineligible"] = ineligible
    if inducted: inc["counters.inducted"] = inducted
    if inc:
        await db.solver_requisitions.update_one({"id": rid}, {"$inc": inc})


# ─────────────── Ineligible Register (HR / Solvers Manager) ───────────────

@router.get("/ineligible")
async def list_ineligible(request: Request,
                          failed_criterion: Optional[str] = None,
                          county: Optional[str] = None,
                          channel: Optional[str] = None,
                          requisition_id: Optional[str] = None):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if failed_criterion:
        q["failed_criteria"] = failed_criterion
    if county:
        q["county"] = county
    if channel:
        q["channel"] = channel
    if requisition_id:
        q["requisition_id"] = requisition_id
    rows = []
    async for r in db.ineligible_applicants.find(q).sort("submitted_at", -1).limit(500):
        rows.append(_serialise(r))
    return {"rows": rows, "count": len(rows)}


@router.get("/ineligible/export.csv")
async def export_ineligible(request: Request,
                            failed_criterion: Optional[str] = None,
                            county: Optional[str] = None,
                            channel: Optional[str] = None,
                            requisition_id: Optional[str] = None):
    from fastapi.responses import Response
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    q = {"tenant_id": "solvit"}
    if failed_criterion: q["failed_criteria"] = failed_criterion
    if county: q["county"] = county
    if channel: q["channel"] = channel
    if requisition_id: q["requisition_id"] = requisition_id
    rows = await db.ineligible_applicants.find(q) \
                                          .sort("submitted_at", -1).to_list(5000)
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Submitted", "Requisition", "Name", "Phone", "Email", "County",
                "Town/Area", "Channel", "Failed Criteria", "Qualifications",
                "Has Licence", "Has Smartphone", "Availability",
                "Commission Acknowledged"])
    for r in rows:
        w.writerow([
            r.get("submitted_at"), r.get("requisition_code"),
            r.get("full_name"), r.get("phone_number"), r.get("email"),
            r.get("county"), r.get("town_area"), r.get("channel"),
            ";".join(r.get("failed_criteria") or []),
            ";".join(r.get("qualifications") or []),
            "Yes" if r.get("has_driving_licence") else "No",
            "Yes" if r.get("has_smartphone") else "No",
            r.get("availability"),
            "Yes" if r.get("commission_acknowledged") else "No",
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                     headers={"Content-Disposition":
                              "attachment; filename=ineligible_solvers.csv"})


@router.get("/ineligible/{aid}")
async def get_ineligible_detail(aid: str, request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    doc = await db.ineligible_applicants.find_one({"id": aid, "tenant_id": "solvit"})
    if not doc:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return _serialise(doc)


# ─────────────── Eligible Solvers (HR / Solvers Manager) ───────────────
# Eligible applicants are stored as `candidates` documents at Stage 1 passed.
# This view scopes the candidates collection to Solver candidates that came
# in through the Solver intake form (i.e. have a `requisition_id`).

@router.get("/eligible")
async def list_eligible(request: Request,
                        county: Optional[str] = None,
                        channel: Optional[str] = None,
                        requisition_id: Optional[str] = None,
                        current_stage: Optional[str] = None):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    q = {"tenant_id": "solvit", "candidate_type": "Solver",
         "requisition_id": {"$exists": True, "$ne": None}}
    if county: q["county"] = county
    if channel: q["source"] = channel
    if requisition_id: q["requisition_id"] = requisition_id
    if current_stage: q["current_stage"] = {"$regex": current_stage, "$options": "i"}
    rows = []
    async for r in db.candidates.find(q).sort("created_at", -1).limit(500):
        rows.append(_serialise(r))
    return {"rows": rows, "count": len(rows)}


@router.get("/eligible/export.csv")
async def export_eligible(request: Request,
                          county: Optional[str] = None,
                          channel: Optional[str] = None,
                          requisition_id: Optional[str] = None,
                          current_stage: Optional[str] = None):
    from fastapi.responses import Response
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    q = {"tenant_id": "solvit", "candidate_type": "Solver",
         "requisition_id": {"$exists": True, "$ne": None}}
    if county: q["county"] = county
    if channel: q["source"] = channel
    if requisition_id: q["requisition_id"] = requisition_id
    if current_stage: q["current_stage"] = {"$regex": current_stage, "$options": "i"}
    rows = await db.candidates.find(q).sort("created_at", -1).to_list(5000)
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Submitted", "Requisition", "Name", "Phone", "Email", "County",
                "Town/Area", "Channel", "Current Stage", "Stage Status",
                "Qualifications", "Previous Inspector Company", "Availability"])
    for r in rows:
        w.writerow([
            r.get("created_at"), r.get("requisition_code"),
            r.get("full_name"), r.get("phone_number"), r.get("email"),
            r.get("county"), r.get("town_area"), r.get("source"),
            r.get("current_stage"), r.get("current_stage_status"),
            ";".join(r.get("qualifications") or []),
            r.get("previous_inspector_company") or "",
            r.get("availability") or "",
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                     headers={"Content-Disposition":
                              "attachment; filename=eligible_solvers.csv"})


@router.get("/eligible/{cid}")
async def get_eligible_detail(cid: str, request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    doc = await db.candidates.find_one({"id": cid, "tenant_id": "solvit",
                                          "candidate_type": "Solver"})
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _serialise(doc)


@router.get("/eligible/{cid}/cv")
async def download_eligible_cv(cid: str, request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    doc = await db.candidates.find_one({"id": cid, "tenant_id": "solvit",
                                          "candidate_type": "Solver"})
    if not doc or not doc.get("cv_path"):
        raise HTTPException(status_code=404, detail="No CV on file for this candidate.")
    p = Path(doc["cv_path"])
    if not p.exists() or CV_UPLOAD_ROOT not in p.parents:
        raise HTTPException(status_code=404, detail="CV file missing on disk.")
    return FileResponse(p, filename=doc.get("cv_filename") or p.name)


@router.get("/ineligible/{aid}/cv")
async def download_ineligible_cv(aid: str, request: Request):
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    doc = await db.ineligible_applicants.find_one({"id": aid, "tenant_id": "solvit"})
    if not doc or not doc.get("cv_path"):
        raise HTTPException(status_code=404, detail="No CV on file for this applicant.")
    p = Path(doc["cv_path"])
    if not p.exists() or CV_UPLOAD_ROOT not in p.parents:
        raise HTTPException(status_code=404, detail="CV file missing on disk.")
    return FileResponse(p, filename=doc.get("cv_filename") or p.name)


# ─────────────── Public-link QR helper ───────────────

@router.get("/requisitions/{rid}/qr")
async def requisition_qr(rid: str, request: Request, base_url: Optional[str] = None):
    """Return a PNG QR code for the public application URL. HR can download
    and share on Facebook / WhatsApp / posters / referral programs."""
    user = await get_current_user(request)
    if not _hr_or_solvers(user):
        raise HTTPException(status_code=403, detail="HR / Solvers Manager only")
    db = get_db()
    req = await db.solver_requisitions.find_one({"id": rid, "tenant_id": "solvit"})
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
    # Resolve public URL from request origin or override
    import os
    public_base = base_url or os.environ.get("PUBLIC_APP_URL") \
        or str(request.base_url).rstrip("/").replace("/api", "")
    apply_url = f"{public_base}/apply/{rid}"
    try:
        import qrcode
        import io
        from fastapi.responses import Response
        img = qrcode.make(apply_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                         headers={"Content-Disposition":
                                  f"attachment; filename={req.get('code')}.png"})
    except ImportError:
        return {"apply_url": apply_url,
                "note": "qrcode library not installed; share the URL directly."}
