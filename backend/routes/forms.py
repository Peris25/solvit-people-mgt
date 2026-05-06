"""Intelligent Forms Engine — all 32 form schemas"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from database import get_db
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/forms", tags=["forms"])

# All 32 form schemas
FORM_SCHEMAS = {
    "form-01": {
        "id": "form-01",
        "title": "Solver Contact and Statutory Information",
        "description": "Solver registration and statutory details",
        "target_role": "solver",
        "sections": [
            {
                "id": "s1",
                "title": "Personal Information",
                "fields": [
                    {"id": "full_name", "label": "Full Name", "type": "text", "required": True, "min_length": 2},
                    {"id": "phone_number", "label": "Phone Number", "type": "phone", "required": True, "format": "+254XXXXXXXXX"},
                    {"id": "national_id_number", "label": "National ID Number", "type": "text", "required": True, "format": "8-digit Kenya National ID"},
                    {"id": "kra_pin", "label": "KRA PIN", "type": "text", "required": True, "format": "A000000000X"},
                    {"id": "nssf_number", "label": "NSSF Number", "type": "text", "required": False},
                    {"id": "sha_number", "label": "SHA Number", "type": "text", "required": False},
                ]
            },
            {
                "id": "s2",
                "title": "Payment Details",
                "fields": [
                    {"id": "bank_name", "label": "Bank Name", "type": "dropdown", "required": False, "options": ["Equity", "KCB", "Co-op", "NCBA", "Absa", "I&M", "DTB", "Family Bank", "Other"]},
                    {"id": "bank_account_number", "label": "Bank Account Number", "type": "text", "required": False, "depends_on": {"field": "bank_name", "not_empty": True}},
                    {"id": "mpesa_number", "label": "M-Pesa Number", "type": "phone", "required": True},
                    {"id": "preferred_payment_method", "label": "Preferred Payment Method", "type": "radio", "required": True, "options": ["Bank Transfer", "M-Pesa"]},
                ]
            },
            {
                "id": "s3",
                "title": "Service Coverage",
                "fields": [
                    {"id": "vehicle_categories", "label": "Vehicle Categories (self-declared)", "type": "multi_checkbox", "required": True, "options": ["Saloon", "SUV", "Pick-Up", "Van", "Truck", "Motorcycle"]},
                    {"id": "nairobi_zones", "label": "Nairobi Zones Covered", "type": "multi_checkbox", "required": True, "options": ["Zone 1: CBD", "Zone 2: Westlands-Kileleshwa", "Zone 3: Karen-Langata", "Zone 4: Eastlands", "Zone 5: Thika Rd Corridor", "Zone 6: South B-South C"]},
                ]
            }
        ]
    },
    "form-02": {
        "id": "form-02",
        "title": "Motor Vehicle Solver Assessment",
        "description": "25-question technical assessment for Solvers",
        "target_role": "solver",
        "pass_mark": 20,
        "total_marks": 25,
        "sections": [
            {
                "id": "s1",
                "title": "Technical Vehicle Assessment",
                "fields": [
                    {"id": "q1", "label": "What does a VIN (Vehicle Identification Number) consist of?", "type": "radio", "required": True, "options": ["12-character numeric code", "17-character alphanumeric code", "10-character code with country prefix", "VIN is not standardized"], "correct_answer": "17-character alphanumeric code"},
                    {"id": "q2", "label": "When inspecting engine oil, which indicates contamination?", "type": "radio", "required": True, "options": ["Dark brown colour", "Milky or foamy appearance", "Low level on dipstick", "Strong petroleum smell"], "correct_answer": "Milky or foamy appearance"},
                    {"id": "q3", "label": "Correct method for checking tyre tread depth without a gauge?", "type": "radio", "required": True, "options": ["Press thumb into tread", "Insert a coin to the tread groove and check visible depth", "Visual inspection only", "Measure with ruler"], "correct_answer": "Insert a coin to the tread groove and check visible depth"},
                    {"id": "q4", "label": "A vehicle fails brake test if measured force is below what % of vehicle weight?", "type": "radio", "required": True, "options": ["25%", "35%", "50%", "65%"], "correct_answer": "50%"},
                    {"id": "q5", "label": "What does OBD-II stand for?", "type": "radio", "required": True, "options": ["Optimal Battery Diagnostics 2", "On-Board Diagnostics version 2", "Operational Body Data Index 2", "Official Bureau of Diagnostics"], "correct_answer": "On-Board Diagnostics version 2"},
                ]
            }
        ]
    },
    "form-03": {
        "id": "form-03",
        "title": "Solvers Code Comprehension Quiz",
        "description": "10-question quiz on Solvit values and Solver code",
        "target_role": "solver",
        "pass_mark": 8,
        "total_marks": 10,
        "sections": [
            {
                "id": "s1",
                "title": "Solvit Values and Code",
                "fields": [
                    {"id": "q1", "label": "What is the most important value at Solvit?", "type": "radio", "required": True, "options": ["Customer Service", "Integrity", "Speed", "Profitability"], "correct_answer": "Integrity — all five non-negotiables are equally important, but Integrity is listed first"},
                    {"id": "q2", "label": "You are running 20 minutes late to an inspection. What is the correct action?", "type": "radio", "required": True, "options": ["Proceed and apologise on arrival", "Notify the client immediately via the app and contact Solvit support", "Cancel the appointment", "Ask a colleague to cover"], "correct_answer": "Notify the client immediately via the app and contact the Solvit support line"},
                    {"id": "q3", "label": "If a client offers you a personal tip for a 'better' report, you should:", "type": "radio", "required": True, "options": ["Accept it politely", "Decline politely — accepting personal payments violates Integrity", "Report to manager later", "Check Solvit policy first"], "correct_answer": "Decline politely — accepting personal payments from clients is a violation of Integrity"},
                    {"id": "q8", "label": "How often is your performance as a Solver formally reviewed?", "type": "radio", "required": True, "options": ["Monthly", "Bi-annually", "Quarterly", "Annually"], "correct_answer": "Quarterly"},
                    {"id": "q9", "label": "Minimum pass mark for this Comprehension Quiz?", "type": "radio", "required": True, "options": ["6 out of 10", "7 out of 10", "8 out of 10", "9 out of 10"], "correct_answer": "8 out of 10"},
                ]
            }
        ]
    },
    "form-05": {
        "id": "form-05",
        "title": "Solvit Alignment Survey (Solver)",
        "description": "Quarterly alignment survey for Solvers — mobile optimised",
        "target_role": "solver",
        "mobile_optimised": True,
        "sections": [
            {
                "id": "pillar1",
                "title": "Pillar 1: Environment",
                "fields": [
                    {"id": "q1", "label": "The work I do as a Solvit Solver challenges me to use my skills fully.", "type": "likert_5", "required": True},
                    {"id": "q2", "label": "I feel trusted by Solvit to do my job well without being micromanaged.", "type": "likert_5", "required": True},
                    {"id": "q3", "label": "When I do great work, I feel that Solvit notices and appreciates it.", "type": "likert_5", "required": True},
                    {"id": "q4", "label": "Being part of the Solvit Solver network helps me grow professionally.", "type": "likert_5", "required": True},
                ]
            },
            {
                "id": "pillar2",
                "title": "Pillar 2: Values",
                "fields": [
                    {"id": "q5", "label": "I try to live the Solvit values in every inspection I do.", "type": "likert_5", "required": True},
                    {"id": "q6", "label": "Solvit treats all Solvers fairly and consistently.", "type": "likert_5", "required": True},
                    {"id": "q7", "label": "When I raise a concern with Solvit support, it is handled professionally.", "type": "likert_5", "required": True},
                    {"id": "q8", "label": "Solvit enforces its standards consistently.", "type": "likert_5", "required": True},
                ]
            },
            {
                "id": "pillar3",
                "title": "Pillar 3: Rewards",
                "fields": [
                    {"id": "q9", "label": "The payment I receive for each completed inspection feels fair.", "type": "likert_5", "required": True},
                    {"id": "q10", "label": "I know how my performance is scored and what I need to earn recognition.", "type": "likert_5", "required": True},
                    {"id": "q11", "label": "The recognition Solvit gives to top-performing Solvers motivates me.", "type": "likert_5", "required": True},
                    {"id": "q12", "label": "If I perform consistently well, I believe Solvit will reward me appropriately.", "type": "likert_5", "required": True},
                ]
            }
        ]
    },
    "form-06": {
        "id": "form-06",
        "title": "FTE Performance Review Form",
        "description": "Bi-annual performance review with Sections A, B, C",
        "target_role": "line_manager",
        "requires_signatures": ["employee", "line_manager", "hr_admin"],
        "sections": [
            {
                "id": "header",
                "title": "Review Header",
                "fields": [
                    {"id": "employee_name", "label": "Employee Name", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "role", "label": "Role", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "department", "label": "Department", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "review_cycle", "label": "Review Cycle", "type": "text", "readonly": True, "auto_populated": True},
                ]
            },
            {
                "id": "section_a",
                "title": "Section A: KPI Objectives (50% weight)",
                "fields": [
                    {"id": "kpi_1_score", "label": "KPI Objective 1 Score", "type": "radio", "required": True, "options": ["1 - Exceeded", "2 - Met", "3 - Below"]},
                    {"id": "kpi_1_evidence", "label": "KPI 1 Evidence / Comment", "type": "textarea", "required": True},
                    {"id": "kpi_2_score", "label": "KPI Objective 2 Score", "type": "radio", "required": True, "options": ["1 - Exceeded", "2 - Met", "3 - Below"]},
                    {"id": "kpi_2_evidence", "label": "KPI 2 Evidence / Comment", "type": "textarea", "required": True},
                    {"id": "kpi_3_score", "label": "KPI Objective 3 Score", "type": "radio", "required": True, "options": ["1 - Exceeded", "2 - Met", "3 - Below"]},
                    {"id": "kpi_3_evidence", "label": "KPI 3 Evidence / Comment", "type": "textarea", "required": True},
                    {"id": "section_a_score", "label": "Section A Score (auto-calculated)", "type": "number", "readonly": True, "auto_calculated": True},
                ]
            },
            {
                "id": "section_b",
                "title": "Section B: 360 Peer Review (30% weight)",
                "fields": [
                    {"id": "peer_integrity_score", "label": "Integrity Score", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "peer_hard_work_score", "label": "Hard Work & Ownership Score", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "peer_teamwork_score", "label": "Teamwork & Decency Score", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "peer_solution_score", "label": "Solution Orientation Score", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "peer_timeliness_score", "label": "Timeliness Score", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "section_b_score", "label": "Section B Score (auto-calculated)", "type": "number", "readonly": True, "auto_calculated": True},
                ]
            },
            {
                "id": "section_c",
                "title": "Section C: Client Data (20% weight)",
                "fields": [
                    {"id": "nps_score", "label": "NPS Score (-100 to +100)", "type": "number", "required": True, "min": -100, "max": 100},
                    {"id": "csat_score", "label": "CSAT Score (1.0 to 5.0)", "type": "number", "required": True, "min": 1.0, "max": 5.0},
                    {"id": "section_c_score", "label": "Section C Score (auto-mapped)", "type": "number", "readonly": True, "auto_calculated": True},
                ]
            },
            {
                "id": "overall",
                "title": "Overall Result",
                "fields": [
                    {"id": "overall_score", "label": "Overall Weighted Score", "type": "number", "readonly": True, "auto_calculated": True, "formula": "A*50% + B*30% + C*20%"},
                    {"id": "overall_rating", "label": "Overall Rating", "type": "text", "readonly": True, "auto_calculated": True},
                    {"id": "nine_box_placement", "label": "9-Box Placement", "type": "dropdown", "required": True, "options": ["Stars", "Core Contributor", "Culture Risk", "Realignment Needed", "Exit Track"]},
                    {"id": "development_priority", "label": "Development Priority for Next Cycle", "type": "textarea", "required": True},
                ]
            }
        ]
    },
    "form-15": {
        "id": "form-15",
        "title": "Leave Request and Approval",
        "description": "Employee leave application form",
        "target_role": "employee",
        "requires_signatures": ["employee", "line_manager"],
        "sections": [
            {
                "id": "s1",
                "title": "Leave Details",
                "fields": [
                    {"id": "employee_name", "label": "Employee Name", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "leave_type", "label": "Leave Type", "type": "dropdown", "required": True, "options": ["Annual", "Sick", "Maternity", "Paternity", "Compassionate"]},
                    {"id": "start_date", "label": "Leave Start Date", "type": "date", "required": True},
                    {"id": "end_date", "label": "Leave End Date", "type": "date", "required": True},
                    {"id": "working_days", "label": "Number of Working Days", "type": "number", "readonly": True, "auto_calculated": True},
                    {"id": "leave_balance", "label": "Current Leave Balance", "type": "number", "readonly": True, "auto_populated": True},
                    {"id": "handover_contact", "label": "Handover Contact", "type": "employee_lookup", "required": True},
                    {"id": "handover_notes", "label": "Brief Handover Note", "type": "textarea", "required": False},
                ]
            }
        ]
    },
    "form-21": {
        "id": "form-21",
        "title": "Exit Interview",
        "description": "Comprehensive exit interview form",
        "target_role": "employee",
        "sections": [
            {
                "id": "s1",
                "title": "Departure Details",
                "fields": [
                    {"id": "reason_for_leaving", "label": "Primary Reason for Leaving", "type": "dropdown", "required": True, "options": ["R1 - Personal/Family reasons", "R2 - Health reasons", "R3 - Compensation", "R4 - Career development", "R5 - Role/Manager issues", "R6 - Company culture", "R7 - Relocation", "R8 - Other"]},
                    {"id": "secondary_reason", "label": "Secondary Reason (if applicable)", "type": "dropdown", "required": False, "options": ["R1 - Personal/Family reasons", "R2 - Health reasons", "R3 - Compensation", "R4 - Career development", "R5 - Role/Manager issues", "R6 - Company culture", "R7 - Relocation", "R8 - Other"]},
                    {"id": "recommend_solvit", "label": "Would you recommend Solvit as a place to work?", "type": "radio", "required": True, "options": ["Yes", "No", "Maybe"]},
                    {"id": "net_promoter_score", "label": "How likely to recommend Solvit to a friend? (0-10)", "type": "number", "required": True, "min": 0, "max": 10},
                    {"id": "what_worked_well", "label": "What worked well at Solvit?", "type": "textarea", "required": True},
                    {"id": "what_to_improve", "label": "What could Solvit improve?", "type": "textarea", "required": True},
                ]
            }
        ]
    },
    "form-31": {
        "id": "form-31",
        "title": "Notice of Resignation",
        "description": "Employee-submitted resignation notice",
        "target_role": "employee",
        "requires_signatures": ["employee"],
        "sections": [
            {
                "id": "s1",
                "title": "Resignation Details",
                "fields": [
                    {"id": "employee_name", "label": "Employee Name", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "role", "label": "Role", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "proposed_last_day", "label": "Proposed Last Day", "type": "date", "required": True},
                    {"id": "notice_period", "label": "Notice Period Acknowledgement", "type": "text", "readonly": True, "auto_populated": True},
                    {"id": "reason_for_resignation", "label": "Reason for Resignation", "type": "dropdown", "required": True, "options": ["R1 - Personal/Family", "R2 - Health", "R3 - Compensation", "R4 - Career development", "R5 - Role/Manager", "R6 - Culture", "R7 - Relocation", "R8 - Other"]},
                    {"id": "personal_note", "label": "Brief Personal Note (optional)", "type": "textarea", "required": False},
                ]
            }
        ]
    }
}

# Merge in 24 fully-populated schemas (FRD §7)
from routes.forms_data import EXTRA_SCHEMAS, FORM_03_FULL_QUESTIONS

# Add 5 missing questions to form-03 (was 5, target 10)
existing_q_ids = {f["id"] for f in FORM_SCHEMAS["form-03"]["sections"][0]["fields"]}
for q in FORM_03_FULL_QUESTIONS:
    if q["id"] not in existing_q_ids:
        FORM_SCHEMAS["form-03"]["sections"][0]["fields"].append(q)

# Add the 24 extra schemas
for fid, schema in EXTRA_SCHEMAS.items():
    FORM_SCHEMAS[fid] = schema

# Stub any remaining form ids just in case (form-25 etc are now in EXTRA_SCHEMAS)
for form_num in ["form-04", "form-07", "form-08", "form-09", "form-10", "form-11", "form-12", "form-13",
                 "form-14", "form-16", "form-17", "form-18", "form-19", "form-20", "form-22", "form-23",
                 "form-24", "form-25", "form-26", "form-27", "form-28", "form-29", "form-30", "form-32"]:
    if form_num not in FORM_SCHEMAS:
        FORM_SCHEMAS[form_num] = {
            "id": form_num,
            "title": f"Form {form_num.split('-')[1].zfill(2)}",
            "description": "Form schema",
            "sections": [{"id": "s1", "title": "Details", "fields": []}]
        }


# Tag form sections with accessible_by_role for sequential workflows.
# When a form has multi-step routing, each section can specify which roles can fill it.
# Frontend uses this to show only the relevant section to the current user.
SECTION_ROLE_ASSIGNMENTS = {
    "form-06": {  # Performance Review: Employee → Line Manager → HR Admin
        # Apply role to schema sections — handled in get_form_schema
    },
    "form-08": {},
    "form-13": {},
    "form-15": {},
    "form-23": {},  # Exit Clearance: 4 sections each with own role
}

# Apply role tagging to known multi-step forms
if "form-23" in FORM_SCHEMAS and FORM_SCHEMAS["form-23"].get("sections"):
    role_for_section = {"it": "employee", "admin": "line_manager", "finance": "finance", "hr": "hr_admin"}
    for sec in FORM_SCHEMAS["form-23"]["sections"]:
        sec["accessible_by_role"] = role_for_section.get(sec["id"], "hr_admin")

if "form-06" in FORM_SCHEMAS and FORM_SCHEMAS["form-06"].get("sections"):
    # Self section → employee, manager scoring → line_manager, calibration → hr_admin
    role_map = {"section_a": "line_manager", "section_b": "line_manager", "section_c": "line_manager",
                "self_review": "employee", "calibration": "hr_admin", "consequence": "hr_admin"}
    for sec in FORM_SCHEMAS["form-06"].get("sections", []):
        sec["accessible_by_role"] = role_map.get(sec.get("id", ""), "line_manager")


def fmt(doc):
    if not doc:
        return None
    # Preserve UUID id if present; only fall back to _id when no id field exists
    if not doc.get("id"):
        doc["id"] = str(doc.get("_id", ""))
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_forms(request: Request):
    user = await get_current_user(request)
    from routes.forms_workflow import FORM_WORKFLOW_MATRIX
    return [{
        "id": k,
        "title": v["title"],
        "description": v.get("description", ""),
        "target_role": v.get("target_role"),
        "module": FORM_WORKFLOW_MATRIX.get(k, {}).get("module"),
        "module_name": FORM_WORKFLOW_MATRIX.get(k, {}).get("module_name"),
        "workflow_trigger": FORM_WORKFLOW_MATRIX.get(k, {}).get("workflow_trigger"),
        "completing_users_sequence": FORM_WORKFLOW_MATRIX.get(k, {}).get("completing_users_sequence", []),
        "required_signatures": FORM_WORKFLOW_MATRIX.get(k, {}).get("required_signatures", []),
        "outcome_rule": FORM_WORKFLOW_MATRIX.get(k, {}).get("outcome_rule"),
    } for k, v in FORM_SCHEMAS.items()]


@router.get("/my-tasks")
async def my_form_tasks(request: Request):
    """Return form submissions currently routed to the calling user."""
    user = await get_current_user(request)
    db = get_db()
    role = user.get("role")
    user_id = user.get("id")
    # Submissions where current_step expects this role and not yet signed by them
    query = {
        "tenant_id": "solvit",
        "status": "InProgress",
        "next_required_role": role,
    }
    subs = await db.form_submissions.find(query).sort("created_at", -1).to_list(100)
    return [fmt(s) for s in subs]


@router.post("/{form_id}/start")
async def start_form_submission(form_id: str, request: Request):
    """Initialize a multi-step form submission. Routes to the first user in the sequence."""
    user = await get_current_user(request)
    from routes.forms_workflow import FORM_WORKFLOW_MATRIX
    if form_id not in FORM_SCHEMAS:
        raise HTTPException(status_code=404, detail=f"Form {form_id} not found")
    matrix = FORM_WORKFLOW_MATRIX.get(form_id, {})
    sequence = matrix.get("completing_users_sequence", [])
    if not sequence:
        raise HTTPException(status_code=400, detail="No workflow defined for this form")

    body = await request.json()
    db = get_db()
    schema = FORM_SCHEMAS[form_id]
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "form_id": form_id,
        "form_title": schema["title"],
        "subject_employee_id": body.get("employee_id"),
        "subject_employee_name": body.get("employee_name"),
        "data": body.get("data", {}) or {},
        "signatures": {},
        "completed_steps": [],
        "current_step_index": 0,
        "next_required_role": sequence[0],
        "completing_users_sequence": sequence,
        "required_signatures": matrix.get("required_signatures", []),
        "outcome_rule": matrix.get("outcome_rule"),
        "status": "InProgress",
        "started_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.form_submissions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/submissions/{submission_id}/sign")
async def sign_form_step(submission_id: str, request: Request):
    """Current user signs their step. Form advances to next user or completes."""
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    sub = await db.form_submissions.find_one({"id": submission_id, "tenant_id": "solvit"})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.get("status") != "InProgress":
        raise HTTPException(status_code=400, detail=f"Submission is {sub.get('status')}, not in progress")

    expected_role = sub.get("next_required_role")
    user_role = user.get("role")
    # Allow hr_admin to act on any role except where the role is the subject employee themselves
    role_match = (expected_role == user_role) or (expected_role == "employee" and sub.get("subject_employee_id") == user.get("employee_id"))
    if not role_match and user_role != "hr_admin":
        raise HTTPException(status_code=403, detail=f"This step requires role: {expected_role}, you are: {user_role}")

    signature = body.get("signature") or user.get("full_name") or user.get("email")
    if not signature:
        raise HTTPException(status_code=400, detail="Signature required")

    # Merge new data
    new_data = {**sub.get("data", {}), **(body.get("data") or {})}
    new_sigs = {**sub.get("signatures", {}), expected_role: {"name": signature, "signed_by": user["id"], "signed_at": datetime.now(timezone.utc).isoformat()}}
    completed = sub.get("completed_steps", []) + [{"role": expected_role, "user_id": user["id"], "at": datetime.now(timezone.utc).isoformat()}]
    seq = sub.get("completing_users_sequence", [])
    next_idx = sub.get("current_step_index", 0) + 1

    update = {"data": new_data, "signatures": new_sigs, "completed_steps": completed, "current_step_index": next_idx, "updated_at": datetime.now(timezone.utc).isoformat()}

    if next_idx >= len(seq):
        # Workflow complete — verify all required signatures present
        required_sigs = sub.get("required_signatures", [])
        missing = [r for r in required_sigs if r not in new_sigs]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing required signatures: {missing}")
        update["status"] = "Completed"
        update["next_required_role"] = None
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
        # Fire outcome rule
        if sub.get("outcome_rule"):
            try:
                from automation.engine import automation_engine
                await automation_engine.fire_event(sub["outcome_rule"], {
                    "form_id": sub["form_id"],
                    "submission_id": submission_id,
                    "subject_employee_id": sub.get("subject_employee_id"),
                    "data": new_data
                })
            except Exception as ex:
                print(f"Outcome rule fire failed: {ex}")
    else:
        update["next_required_role"] = seq[next_idx]
        # Notify next user
        try:
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "recipient_role": seq[next_idx],
                "category": "Form",
                "title": f"[{sub['form_id']}] {sub['form_title']} awaits your sign-off",
                "message": f"Step {next_idx + 1} of {len(seq)} ready for your input.",
                "data": {"submission_id": submission_id, "form_id": sub["form_id"]},
                "is_read": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            pass

    await db.form_submissions.update_one({"id": submission_id}, {"$set": update})
    sub.update(update)
    sub.pop("_id", None)
    return sub


@router.get("/{form_id}")
async def get_form_schema(form_id: str, request: Request):
    user = await get_current_user(request)
    schema = FORM_SCHEMAS.get(form_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Form {form_id} not found")
    from routes.forms_workflow import FORM_WORKFLOW_MATRIX
    matrix = FORM_WORKFLOW_MATRIX.get(form_id, {})
    enriched = {**schema, **matrix}
    return enriched


@router.post("/{form_id}/submit")
async def submit_form(form_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()

    schema = FORM_SCHEMAS.get(form_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Form {form_id} not found")

    # Enforce required signatures for single-step forms
    from routes.forms_workflow import FORM_WORKFLOW_MATRIX
    matrix = FORM_WORKFLOW_MATRIX.get(form_id, {})
    required_sigs = matrix.get("required_signatures", [])
    sigs = body.get("signatures", {}) or {}
    missing = [r for r in required_sigs if r not in sigs]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required signatures: {missing}")

    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "solvit",
        "form_id": form_id,
        "form_title": schema["title"],
        "submitted_by": user["id"],
        "data": body.get("data", {}),
        "signatures": sigs,
        "status": "Submitted",
        "outcome_rule": matrix.get("outcome_rule"),
        "submitted_at": datetime.now(timezone.utc).isoformat()
    }

    # Auto-score quizzes
    if form_id in ["form-02", "form-03"]:
        score = _calculate_quiz_score(schema, body.get("data", {}))
        pass_mark = schema.get("pass_mark", 0)
        doc["score"] = score
        doc["passed"] = score >= pass_mark
        doc["pass_mark"] = pass_mark

    # Resignation form triggers exit workflow
    if form_id == "form-31" and body.get("data"):
        emp_id = body.get("employee_id") or user.get("employee_id")
        if emp_id:
            from automation.engine import automation_engine
            await automation_engine.fire_event("employee_exiting", {"employee_id": emp_id})

    # Fire outcome rule generically (best-effort)
    if matrix.get("outcome_rule"):
        try:
            from automation.engine import automation_engine
            await automation_engine.fire_event(matrix["outcome_rule"], {
                "form_id": form_id,
                "submitted_by": user["id"],
                "data": body.get("data", {})
            })
        except Exception:
            pass

    result = await db.form_submissions.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def _calculate_quiz_score(schema: dict, responses: dict) -> int:
    score = 0
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            if field.get("type") == "radio" and field.get("correct_answer"):
                user_answer = responses.get(field["id"])
                if user_answer == field["correct_answer"]:
                    score += 1
    return score


@router.get("/submissions/{entity_id}")
async def get_submissions(entity_id: str, request: Request, form_id: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = {"tenant_id": "solvit", "$or": [{"submitted_by": entity_id}, {"data.employee_id": entity_id}]}
    if form_id:
        query["form_id"] = form_id
    subs = await db.form_submissions.find(query).sort("submitted_at", -1).to_list(50)
    return [fmt(s) for s in subs]
