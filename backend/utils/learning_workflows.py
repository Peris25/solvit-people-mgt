"""Training catalogue, approvals and verified learning over existing request records."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import math
import uuid
import logging
from bson import ObjectId
from fastapi import HTTPException
from utils.employee_access import authorize_employee, find_linked_record, personal_grant, reference_ids, reject_identity_changes
from utils.employee_integrity import employee_key, find_employee, is_direct_report, tenant_of, tenant_query, validate_manager
from utils.staff_directory import employment_type, normalized
from utils.staff_views import restricted

HR = {"hr_admin", "hr_manager"}
PENDING = {"Pending_Manager_Approval", "Pending_HR_Approval"}


def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone(timedelta(hours=3))).date().isoformat()
def fail(message, status=422): raise HTTPException(status, message)


def text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        fail(f"A valid {label} is required")
    return value.strip()


def day(value, label, optional=False):
    if optional and value in (None, ""): return None
    try: return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError): fail(f"A valid {label} is required")


def numeric(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        fail(f"Invalid {label}")
    return value


def require_hr(user):
    if user.get("role") not in HR: fail("HR authorization required", 403)
    personal_grant(user, "M08", write=True)


def native_query(value):
    if not isinstance(value, dict): return value
    result={}
    for key,item in value.items():
        if key=="$in" and isinstance(item,list):
            result[key]=item+[ObjectId(ref) for ref in item if isinstance(ref,str) and ObjectId.is_valid(ref)]
        elif isinstance(item,list): result[key]=[native_query(entry) for entry in item]
        else: result[key]=native_query(item)
    return result


async def employee_access(db, user, reference, write=False, active=False):
    employee = await authorize_employee(db, user, reference, "M08", write=write)
    if restricted(employee.get("board_only")): fail("Restricted employee record", 403)
    if active and normalized(employee.get("lifecycle_state") or employee.get("status")) not in {
            "active", "onboarding", "probation", "onleave", "pip", "realignment"}:
        fail("Employee is not eligible for a new learning action", 409)
    return employee


async def audit(db, user, event, row, **metadata):
    await db.audit_logs.insert_one({"tenant_id": tenant_of(user), "event": event,
        "entity_id": str(row.get("id") or row.get("_id")), "actor_id": user["id"], "timestamp": now(), "metadata": metadata})


async def notify(db, row, event):
    employee = await find_employee(db, row.get("employee_id"), tenant_of(row))
    if not employee: fail("Training employee needs an integrity review", 409)
    recipients = [("employee", employee_key(employee)), ("role", "hr_admin"), ("role", "hr_manager")]
    manager = await find_employee(db, employee.get("line_manager_id"), tenant_of(row))
    if manager: recipients.append(("employee", employee_key(manager)))
    for kind, recipient in recipients:
        key = f"learning:{tenant_of(row)}:{row['id']}:{event}:{kind}:{recipient}"
        await db.notifications.update_one({"_id": key}, {"$setOnInsert": {"id": key,
            "tenant_id": tenant_of(row), "category": "Training", "created_at": now(), "is_read": False,
            **({"recipient_role": recipient} if kind == "role" else {"recipient_type": "employee", "recipient_id": recipient}),
            "data": {"employee_id": employee_key(employee), "training_request_id": row["id"]}}}, upsert=True)


CATALOGUE_FIELDS = {"title", "kind", "parent_id", "description", "provider", "delivery_method", "location",
    "starts_on", "ends_on", "due_on", "departments", "employment_types", "completion_requirements", "evidence_required", "cost_kes", "duration_days", "status"}


async def catalogue_record(db, user, reference):
    reference=text(reference,"programme identifier",200)
    return await find_linked_record(db.training_programmes, reference, user)


async def eligible(db, user, programme, employee):
    seen = set()
    current = programme
    while current:
        key = str(current.get("id") or current["_id"])
        if key in seen or len(seen) >= 8: fail("Training catalogue hierarchy needs HR review", 409)
        seen.add(key)
        if current.get("status") != "Published": fail("Training is not open for assignment", 409)
        if current.get("departments") and normalized(employee.get("department")) not in {normalized(v) for v in current["departments"]}:
            fail("Employee does not meet department eligibility", 403)
        if current.get("employment_types") and employment_type(employee.get("employment_type")) not in {employment_type(v) for v in current["employment_types"]}:
            fail("Employee does not meet employment-type eligibility", 403)
        current = await catalogue_record(db, user, current["parent_id"]) if current.get("parent_id") else None


async def save_programme(db, user, body, reference=None):
    require_hr(user)
    if not isinstance(body, dict) or set(body) - CATALOGUE_FIELDS: fail("Unknown training catalogue fields")
    current = await catalogue_record(db, user, reference) if reference else None
    if current and any(key in body and body[key] != current.get(key) for key in ("kind", "parent_id")):
        fail("Programme identity and hierarchy are immutable", 409)
    row = {**(current or {}), **body}
    if row.get("location") is not None and (not isinstance(row["location"],str) or len(row["location"])>500): fail("Invalid training location")
    kind = row.get("kind")
    if not isinstance(kind, str) or kind not in {"Programme", "Course", "Session"}: fail("Choose Programme, Course or Session")
    status = row.get("status", "Draft")
    if not isinstance(status, str) or status not in {"Draft", "Published", "Archived"}: fail("Invalid programme status")
    row.update(title=text(row.get("title"), "training title", 300), kind=kind, status=status,
        description=text(row.get("description"), "description"), provider=text(row.get("provider"), "provider", 300),
        delivery_method=text(row.get("delivery_method"), "delivery method", 100),
        completion_requirements=text(row.get("completion_requirements"), "completion requirements"))
    parent = await catalogue_record(db, user, row["parent_id"]) if row.get("parent_id") else None
    if (kind == "Programme" and parent) or (kind == "Session" and not parent) or (parent and parent.get("kind") != {"Course":"Programme", "Session":"Course"}.get(kind)):
        fail("Sessions belong to courses; courses may belong to a programme")
    if parent: row["parent_id"] = parent["id"]
    for key in ("starts_on", "ends_on", "due_on"):
        row[key] = day(row.get(key), key, optional=kind == "Programme")
    if any(row.get(key) for key in ("starts_on","ends_on","due_on")) and not all(row.get(key) for key in ("starts_on","ends_on","due_on")):
        fail("Provide the complete schedule or leave the programme container unscheduled")
    if parent and row.get("starts_on") and parent.get("starts_on") and (row["starts_on"] < parent["starts_on"] or row["ends_on"] > parent["ends_on"]):
        fail("Session/course schedule must fit its parent schedule")
    if row.get("starts_on") and row.get("ends_on") < row["starts_on"]: fail("Training end precedes its start")
    if row.get("ends_on") and row.get("due_on") < row["ends_on"]: fail("Completion deadline precedes the training end")
    for key in ("departments", "employment_types"):
        values = row.get(key, [])
        if not isinstance(values, list) or len(values) > 100 or any(not isinstance(v, str) or not v.strip() or len(v)>200 for v in values):
            fail("Eligibility must contain explicit department/employment-type names")
        row[key] = list(dict.fromkeys(value.strip() for value in values))
    if not isinstance(row.get("evidence_required", False), bool): fail("Evidence requirement must be boolean")
    row["evidence_required"] = row.get("evidence_required", False)
    row["cost_kes"] = numeric(row.get("cost_kes", 0), "training cost")
    row["duration_days"] = numeric(row.get("duration_days", 1), "training duration", 1)
    if not isinstance(row["duration_days"], int): fail("Training duration must be whole days")
    row.update(id=(current or {}).get("id") or str(uuid.uuid4()), tenant_id=tenant_of(user), updated_at=now(),
               version=(current or {}).get("version",0)+1)
    if not current: row["created_at"] = now()
    await audit(db,user,"learning.programme.updated" if current else "learning.programme.created",row,
                before={key: deepcopy(current.get(key)) for key in CATALOGUE_FIELDS} if current else None,
                after={key: deepcopy(row.get(key)) for key in CATALOGUE_FIELDS})
    if current:
        await db.training_programmes.update_one({"_id":current["_id"]},{"$set":{key:value for key,value in row.items() if key!="_id"}})
    else: await db.training_programmes.insert_one(row)
    return {key:value for key,value in row.items() if key not in {"_id","tenant_id"}}


async def prepare_request(db, user, body):
    employee = await employee_access(db,user,body.get("employee_id"),write=True,active=True)
    manager = await validate_manager(db,employee.get("line_manager_id"),employee,tenant_of(user))
    programme = await catalogue_record(db,user,body["programme_id"]) if body.get("programme_id") else None
    if programme:
        await eligible(db,user,programme,employee)
        if programme.get("kind") == "Programme": fail("Assign a scheduled course or session, not a programme container")
        data = {"training_name":programme["title"],"provider":programme["provider"],"delivery_method":programme["delivery_method"],
            "cost_kes":programme["cost_kes"],"duration_days":programme["duration_days"],"proposed_start_date":programme["starts_on"],
            "proposed_end_date":programme["ends_on"],"due_on":programme["due_on"],"programme_id":programme["id"],
            "programme_version":programme["version"],"completion_requirements":programme["completion_requirements"],
            "evidence_required":programme["evidence_required"],"description":programme["description"],"location":programme.get("location")}
    else:
        data = {key:body.get(key) for key in ("training_name","provider","delivery_method","link_to_idp_goal")}
        for key in ("training_name","provider","delivery_method"): data[key]=text(data[key],key,300)
        data["cost_kes"] = numeric(body.get("cost_kes",0),"training cost")
        data["duration_days"] = numeric(body.get("duration_days",1),"training duration",1)
        if not isinstance(data["duration_days"],int): fail("Duration must be whole days")
        data["proposed_start_date"] = day(body.get("proposed_start_date"),"start date",True)
        data["proposed_end_date"] = day(body.get("proposed_end_date"),"end date",True)
        if data["proposed_end_date"] and not data["proposed_start_date"]: fail("Training start date is required with an end date")
        if data["proposed_start_date"] and data["proposed_end_date"] and data["proposed_end_date"] < data["proposed_start_date"]: fail("Training end precedes start")
        data["due_on"] = data["proposed_end_date"]
        data.update(completion_requirements="Employee completion declaration and HR verification",evidence_required=False)
    aliases = reference_ids(employee)+[employee["_id"]]
    prior = await db.training_requests.find({"$and":[tenant_query(tenant_of(user)),{"employee_id":{"$in":aliases},"status":{"$nin":["Rejected","Cancelled"]}}]}).to_list(None)
    for row in prior:
        duplicate = row.get("programme_id")==data.get("programme_id") if programme else (
            normalized(row.get("training_name") or row.get("title") or row.get("name"))==normalized(data["training_name"]) and
            row.get("proposed_start_date")==data.get("proposed_start_date"))
        if duplicate: fail("This learning assignment/request already exists",409)
    return {"id":str(uuid.uuid4()),"tenant_id":tenant_of(user),"employee_id":employee_key(employee),"line_manager_id":manager,
        **data,"business_justification":text(body.get("business_justification"),"business justification"),
        "status":"Pending_Manager_Approval","requires_hr_approval":data["cost_kes"]>5000 or data["duration_days"]>2,
        "submitted_by":user["id"],"learning_version":1,"created_at":now()}


async def persist_request(db,user,row):
    await audit(db,user,"learning.request.created",row,employee_id=row["employee_id"],programme_id=row.get("programme_id"))
    await db.training_requests.insert_one(row)
    await notify(db,row,"created")
    try:
        from utils.email_triggers import fire_and_forget
        await fire_and_forget(db,"lnd.training_assigned",employee_id=row["employee_id"],extra={
            "training_name":row["training_name"],"provider":row.get("provider"),"start_date":row.get("proposed_start_date"),"end_date":row.get("proposed_end_date")})
    except Exception: pass
    return row


async def record(db,user,reference,write=False):
    row=await find_linked_record(db.training_requests,reference,user)
    row.setdefault("id",str(row["_id"]))
    employee=await employee_access(db,user,row.get("employee_id"),write=write)
    return row,employee


async def save(db,user,row,update,event):
    await audit(db,user,event,row,before={key:deepcopy(row.get(key)) for key in update},after=deepcopy(update))
    await db.training_requests.update_one({"_id":row["_id"]},{"$set":{**update,"updated_at":now()}})
    row.update(update)
    fingerprint=hashlib.sha256(json.dumps(update,sort_keys=True,default=str).encode()).hexdigest()[:24]
    await notify(db,row,event+":"+fingerprint)
    return row


async def decide(db,user,reference,body):
    if body.get("decision") not in ("Approve","Reject"): fail("Invalid training decision")
    row,employee=await record(db,user,reference,write=True)
    reject_identity_changes(body,row)
    if employee_key(employee)==user.get("employee_id"): fail("Employees cannot approve their own training",403)
    status=row.get("status")
    if status not in PENDING: fail("Training is not awaiting this decision",409)
    decision=body["decision"]
    update={}
    if decision=="Reject" and user.get("role") in HR:
        require_hr(user)
        update={"status":"Rejected","hr_decision":"Reject","hr_reason":text(body.get("reason"),"rejection reason")}
    elif status=="Pending_Manager_Approval":
        if not is_direct_report(employee,user): fail("Only the employee's current manager can decide this stage",403)
        manager=await validate_manager(db,employee.get("line_manager_id"),employee,tenant_of(user))
        if row.get("line_manager_id"):
            saved=await find_employee(db,row["line_manager_id"],tenant_of(user))
            if not saved or employee_key(saved)!=manager: fail("Manager assignment changed; HR reconciliation required",409)
        requires_hr=bool(row.get("requires_hr_approval")) or numeric(row.get("cost_kes",0),"training cost")>5000 or numeric(row.get("duration_days",1),"duration",1)>2
        update={"manager_decision":decision,"manager_decided_by":user["id"],"manager_decided_at":now(),
            "status":("Pending_HR_Approval" if requires_hr else "Approved") if decision=="Approve" else "Rejected"}
        if decision=="Reject": update["manager_reason"]=text(body.get("reason"),"rejection reason")
    else:
        require_hr(user)
        if row.get("manager_decision")!="Approve": fail("Recorded manager approval is required",409)
        update={"hr_decision":decision,"hr_decided_by":user["id"],"hr_decided_at":now(),"status":"Approved"}
    await save(db,user,row,update,"learning.request.decided")
    return row,employee


async def document(db,user,employee,reference):
    from routes.documents import _visible, _restricted
    await authorize_employee(db,user,employee_key(employee),"M01")
    reference=text(reference,"evidence document identifier",200)
    doc=await find_linked_record(db.employee_documents,reference,user)
    if doc.get("employee_id") not in reference_ids(employee)+[employee["_id"]] or doc.get("deleted_at") or doc.get("publication_state") not in (None,"Ready"):
        fail("Evidence document does not belong to this employee or is unavailable",403)
    if _restricted(doc) or not _visible(doc,employee,user): fail("This document is not authorized as learning evidence",403)
    return doc


async def complete(db,user,reference,body):
    row,employee=await record(db,user,reference,write=True)
    action=body.get("action")
    if not isinstance(action,str) or action not in {"submit","verify","return","record"}: fail("Invalid completion action")
    if set(body)-{"action","completed_on","evidence","document_id","requirements_met","reason"}: fail("Completion cannot change employee, approval or programme fields")
    own=employee_key(employee)==user.get("employee_id")
    if action=="submit":
        await employee_access(db,user,employee_key(employee),write=True,active=True)
        if not own: fail("Only the employee may declare their completion",403)
        if row.get("status")!="Approved": fail("Approved training is required before completion",409)
    else:
        require_hr(user)
        if own: fail("HR cannot verify their own learning completion",403)
        if row.get("status")!=("Approved" if action=="record" else "Completion_Submitted"): fail("Training is not at this completion stage",409)
    if action=="return":
        update={"status":"Approved","completion_return_reason":text(body.get("reason"),"return reason")}
    elif action in {"submit","record"}:
        completed=day(body.get("completed_on"),"completion date")
        if completed>today() or (row.get("proposed_start_date") and completed<row["proposed_start_date"]): fail("Completion date must reflect actual attendance")
        doc_id=body.get("document_id")
        if row.get("evidence_required") or action=="record":
            if not doc_id: fail("An authorized Document Centre record is required")
        if doc_id: await document(db,user,employee,doc_id)
        evidence={"completed_on":completed,"evidence":text(body.get("evidence"),"completion evidence"),"document_id":doc_id,"submitted_by":user["id"],"submitted_at":now()}
        update={"status":"Completion_Submitted" if action=="submit" else "Completed","completion_submission":evidence,
                "completion_submissions":[*(row.get("completion_submissions") or []),evidence],"completion_return_reason":None}
        if action=="record":
            if body.get("requirements_met") is not True: fail("HR must verify the completion requirements")
            update.update(completed_on=completed,completion_verified_by=user["id"],completion_verified_at=now())
    else:
        submission=row.get("completion_submission") or {}
        if not submission.get("submitted_by") or body.get("requirements_met") is not True: fail("HR must verify the recorded completion evidence")
        if submission.get("document_id"): await document(db,user,employee,submission["document_id"])
        if row.get("evidence_required") and not submission.get("document_id"): fail("Required evidence is missing",409)
        update={"status":"Completed","completed_on":submission["completed_on"],"completion_verified_by":user["id"],"completion_verified_at":now()}
    await save(db,user,row,update,"learning.completion."+action)
    return row,employee


async def projection(db,user,row,employee):
    fields=("training_name","provider","delivery_method","cost_kes","duration_days","proposed_start_date","proposed_end_date","due_on",
        "programme_id","programme_version","description","location","completion_requirements","evidence_required","business_justification",
        "status","created_at","completed_on","learning_version","completion_return_reason")
    result={key:deepcopy(row[key]) for key in fields if key in row}
    result.update(id=str(row.get("id") or row["_id"]),employee_id=employee_key(employee),employee_name=employee.get("full_name"))
    result["training_name"]=row.get("training_name") or row.get("title") or row.get("name") or "Training"
    own=employee_key(employee)==user.get("employee_id")
    writable=True
    try: personal_grant(user,"M08",write=True)
    except HTTPException: writable=False
    result["can_decide"]=writable and not own and ((row.get("status")=="Pending_Manager_Approval" and is_direct_report(employee,user)) or
        (row.get("status")=="Pending_HR_Approval" and user.get("role") in HR))
    result["can_submit_completion"]=writable and own and row.get("status")=="Approved"
    result["can_verify_completion"]=writable and not own and user.get("role") in HR and row.get("status")=="Completion_Submitted"
    result["can_record_certificate"]=writable and not own and user.get("role") in HR and row.get("status")=="Approved"
    submission=deepcopy(row.get("completion_submission"))
    if submission:
        submission.pop("submitted_by",None)
        ref=submission.get("document_id")
        if ref:
            try: await document(db,user,employee,ref)
            except HTTPException: submission.pop("document_id",None)
        result["completion_submission"]=submission
    return result


async def remind_due(db):
    current_day=today()
    rows=await db.training_requests.find({"learning_version":1,"status":{"$in":[*PENDING,"Approved"]}}).to_list(None)
    for row in rows:
        due=row.get("due_on")
        if isinstance(due,str) and due<=current_day:
            try: await notify(db,row,"deadline:"+due+(":due" if due==current_day else ":overdue"))
            except HTTPException:
                logging.getLogger(__name__).warning("Learning deadline reminder requires an employee integrity review")
