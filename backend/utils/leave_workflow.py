"""Serialized leave lifecycle. Historical records and balance snapshots are retained."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import uuid
import math

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from utils.employee_integrity import (employee_key, find_employee, integrity_write, tenant_of,
                                      tenant_query, validate_manager)
from utils.employee_access import authorize_employee, find_linked_record, saved_manager, reject_identity_changes
from utils.leave_policy import preview, day, today, own_requests, department_cover, VERSION

PENDING = {"Pending_Manager", "Pending_HR", "Discussion_Requested", "Pending", "Submitted"}
HR = {"hr_admin", "hr_manager"}


def stamp(): return datetime.now(timezone.utc).isoformat()


def own(employee, user): return employee_key(employee) == user.get("employee_id")


async def stage_for(db, user, record):
    if record.get("status") not in {"Pending_Manager", "Pending_HR"}:
        return None
    try:
        employee = await authorize_employee(db, user, record.get("employee_id"), "M18", approve=True)
        if own(employee, user):
            return None
        if record["status"] == "Pending_HR":
            await saved_manager(db, user, employee, record.get("line_manager_id"))
            if user.get("employee_id") and user.get("role") in HR and record.get("manager_decision") == "Approve" and record.get("manager_decided_by") and record.get("manager_decided_by") != user["id"]:
                return "hr"
            return None
        manager_id = await saved_manager(db, user, employee, record.get("line_manager_id"))
        await validate_manager(db, manager_id, employee, tenant_of(user))
        if manager_id == user.get("employee_id"):
            return "manager"
    except HTTPException:
        pass
    return None


async def view(db, user, record):
    employee = await authorize_employee(db, user, record.get("employee_id"), "M18")
    result = deepcopy(record)
    result["id"] = str(record.get("id") or record["_id"])
    result["storage_id"] = str(record["_id"])
    result.pop("_id", None)
    result["employee_id"] = employee_key(employee)
    result["employee_name"] = employee.get("full_name") if isinstance(employee.get("full_name"), str) else None
    permitted_private = own(employee, user) or user.get("role") in HR
    if not permitted_private:
        for field in ("supporting_document_id", "birth_date", "expected_delivery_date", "family_relationship", "sick_pay", "document_verified"):
            result.pop(field, None)
        if record.get("leave_type") == "Sick":
            result.pop("notes", None)
            result.pop("manager_reason", None)
            result.pop("hr_reason", None)
            for entry in result.get("approval_history", []):
                entry.pop("reason", None)
    # Never send paths or arbitrary historical private fields as part of lists.
    fields = {"id", "storage_id", "employee_id", "employee_name", "tenant_id", "leave_type", "start_date", "end_date", "working_days",
              "status", "handover_contact", "handover_contact_id", "notes", "line_manager_id", "created_at", "updated_at",
              "manager_decision", "manager_reason", "manager_decided_at", "manager_decided_by", "hr_decision", "hr_reason",
              "hr_decided_at", "approval_history", "policy_version", "supporting_document_id", "supporting_document_present",
              "document_verified", "expected_delivery_date", "birth_date", "family_relationship", "sick_pay", "emergency_sick",
              "extended_sick_followup_required", "compassionate_paid_days", "compassionate_unpaid_days", "flag_hr_attention"}
    result = {key: value for key, value in result.items() if key in fields}
    result["approval_history"] = [{key: value for key, value in entry.items()
                                   if key in {"stage", "actor_id", "actor_role", "at", "decision", "reason", "handover_reviewed", "policy_review_confirmed", "document_verified"}
                                   and isinstance(value, (str, bool, int, float))}
                                  for entry in result.get("approval_history", []) if isinstance(entry, dict)]
    result["approval_stage"] = await stage_for(db, user, record)
    result["can_reject"] = result["approval_stage"] is not None or (user.get("role") in HR and not own(employee, user) and record.get("status") in PENDING)
    result["can_cancel"] = own(employee, user) and record.get("status") in PENDING and isinstance(record.get("start_date"), str) and record["start_date"] > today().isoformat()
    return result


async def availability(db, employee, balance, exclude=None):
    if balance.get("source") == "stored_snapshot" and balance.get("year") is None:
        raise HTTPException(409, "An undated balance snapshot requires approved HR reconciliation")
    value = (balance.get("Annual") or {}).get("remaining")
    if value is None:
        value = balance.get("annual_days_remaining")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise HTTPException(409, "HR must reconcile the recorded annual leave balance")
    reserved = 0
    for row in await own_requests(db, employee):
        if row.get("_id") == exclude or row.get("leave_type") != "Annual" or row.get("policy_version") != VERSION:
            continue
        if balance.get("year") and str(row.get("start_date", ""))[:4] != str(balance["year"]):
            continue
        if row.get("status") in PENDING or (balance.get("source") == "stored_snapshot" and row.get("status") == "Approved"):
            # Snapshot figures remain untouched. New workflow commitments are
            # separately reserved rather than rewriting historical balances.
            value_days = row.get("working_days")
            if not isinstance(value_days, (int, float)) or isinstance(value_days, bool) or not math.isfinite(value_days) or value_days < 0:
                raise HTTPException(409, "HR must reconcile a leave commitment")
            reserved += value_days
    return max(0, value - reserved)


async def email_existing(db, employee, record, event):
    """Keep existing best-effort templates; no medical/rejection text in email."""
    try:
        from utils.email_service import send_email
        if employee.get("work_email"):
            await send_email(db, to=employee["work_email"], template_key="leave.received" if event == "submitted" else "leave.approved" if record["status"] == "Approved" else "leave.rejected",
                             context={"employee_name": employee.get("full_name", ""), "leave_type": record["leave_type"], "start_date": record["start_date"],
                                      "end_date": record["end_date"], "days": record.get("working_days"), "reason": "Please review the authorized leave record for the decision."})
        if event == "submitted":
            manager = await find_employee(db, record.get("line_manager_id"), tenant_of(record))
            if manager and manager.get("work_email"):
                await send_email(db, to=manager["work_email"], template_key="leave.pending_lm", context={"employee_name": employee.get("full_name", ""), "start_date": record["start_date"], "end_date": record["end_date"], "leave_type": record["leave_type"], "days": record["working_days"]})
    except Exception:
        pass  # Existing mail failures do not undo a saved leave transaction.


async def notify(db, record, event):
    recipients = [("employee", record["employee_id"])]
    if record["status"] == "Pending_Manager":
        recipients.append(("employee", record["line_manager_id"]))
    if record["status"] == "Pending_HR" or record.get("extended_sick_followup_required") or record.get("flag_hr_attention") or (record.get("sick_pay") or {}).get("unpaid_days", 0) > 0:
        from utils.employee_integrity import resolve_user_employee
        covered = {reference for kind, reference in recipients if kind == "employee"}
        for role in ("hr_admin", "hr_manager"):
            accounts = await db.users.find({"$and": [tenant_query(tenant_of(record)), {"role": role, "is_active": {"$ne": False}}]}).to_list(None)
            if not accounts:
                recipients.append(("role", role))
            for account in accounts:
                identity = {**account, "id": str(account["_id"])}
                linked = await resolve_user_employee(db, identity)
                if not linked or employee_key(linked) not in covered:
                    recipients.append(("account", identity["id"]))
    for kind, reference in recipients:
        key = json.dumps([tenant_of(record), record["id"], len(record.get("approval_history", [])), event, kind, reference])
        row = {"_id": ObjectId(hashlib.sha256(key.encode()).hexdigest()[:24]), "id": str(uuid.uuid4()),
               "tenant_id": tenant_of(record), "category": "Leave", "title": "Leave update",
               "message": "A leave request has a workflow update. Open the authorized record for details.",
               "data": {"employee_id": record["employee_id"], "leave_request_id": record["id"]},
               "is_read": False, "created_at": stamp()}
        if kind == "role":
            row["recipient_role"] = reference
        else:
            row.update(recipient_id=reference, recipient_type=kind)
        try:
            await db.notifications.insert_one(row)
        except DuplicateKeyError:
            previous = await db.notifications.find_one({"_id": row["_id"]})
            if not previous or previous.get("data") != row["data"]:
                raise HTTPException(409, "Leave notification identity needs review")
        except Exception:
            raise HTTPException(503, {"code": "leave_saved_notification_failed", "request_id": record["id"],
                                      "message": "Leave was saved. Refresh the record before retrying; notification delivery needs review."})


async def audit(db, user, record, action):
    try:
        await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "actor_id": user["id"],
                                        "action": action, "entity_type": "leave", "entity_id": record["id"], "created_at": stamp()})
    except Exception:
        raise HTTPException(503, {"code": "leave_saved_audit_failed", "request_id": record["id"],
                                  "message": "Leave was saved. Operator audit review is required before retrying."})


async def create(db, user, payload, balance_loader):
    employee = await authorize_employee(db, user, payload["employee_id"], "M18", write=True)
    if not own(employee, user) and user.get("role") not in HR:
        raise HTTPException(403, "Only HR may submit leave for another employee")
    canonical = employee_key(employee)
    async with integrity_write(db):
        employee = await authorize_employee(db, user, canonical, "M18", write=True)
        manager = await saved_manager(db, user, employee, payload.get("line_manager_id"))
        await validate_manager(db, manager, employee, tenant_of(user))
        previous = None
        if payload.get("request_token"):
            previous = await db.leave_requests.find_one({"$and": [tenant_query(tenant_of(user)), {
                "employee_id": canonical, "submitted_by": user["id"], "request_token": payload["request_token"]}]})
        fingerprint_fields = ("leave_type", "start_date", "end_date", "notes", "handover_contact_id", "supporting_document_id", "birth_date", "expected_delivery_date", "family_relationship", "emergency_sick", "early_maternity_advice")
        fingerprint = hashlib.sha256(json.dumps({key: payload.get(key) for key in fingerprint_fields}, sort_keys=True).encode()).hexdigest()
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "This submission token already belongs to a different leave request")
            record = previous
        else:
            quote = await preview(db, employee, payload)
            balance = await balance_loader(canonical)
            if payload["leave_type"] == "Annual" and str(balance.get("year", today().year)) != str(day(payload["start_date"]).year):
                raise HTTPException(409, "HR must confirm the balance for the requested leave year")
            if payload["leave_type"] == "Annual" and quote["working_days"] > await availability(db, employee, balance):
                raise HTTPException(422, "Requested annual leave exceeds the recorded available balance after pending commitments")
            if payload["leave_type"] == "Unpaid" and await availability(db, employee, balance) > 0:
                raise HTTPException(422, "Annual leave must be exhausted before leave without pay")
            covering = await find_employee(db, payload.get("handover_contact_id"), tenant_of(user)) if payload.get("handover_contact_id") else None
            record = {**payload, "id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "employee_id": canonical,
                      "line_manager_id": manager, "handover_contact": covering.get("full_name") if covering else None,
                      "working_days": quote["working_days"], "status": "Pending_Manager", "policy_version": VERSION,
                      "policy_snapshot": quote, "supporting_document_present": quote["supporting_document_present"],
                      "extended_sick_followup_required": quote["extended_sick_followup_required"], "sick_pay": quote["sick_pay"],
                      "compassionate_paid_days": quote["compassionate_paid_days"], "compassionate_unpaid_days": quote["compassionate_unpaid_days"],
                      "flag_hr_attention": quote["high_activity"] or quote["working_days"] > 5,
                      "submitted_by": user["id"], "created_at": stamp(), "request_fingerprint": fingerprint,
                      "approval_history": [{"stage": "submitted", "actor_id": user["id"], "actor_role": user["role"], "at": stamp()}]}
            inserted = await db.leave_requests.insert_one(record)
            record["_id"] = inserted.inserted_id
            await audit(db, user, record, "leave.submitted")
    await notify(db, record, "submitted")
    if previous is None:
        await email_existing(db, employee, record, "submitted")
        from automation.engine import automation_engine
        await automation_engine.fire_event("leave_request_submitted", {"employee_id": canonical, "leave_request_id": record["id"], "notifications_already_created": True})
    return await view(db, user, record)


async def decide(db, user, reference, body, balance_loader):
    decision = body.get("decision")
    if decision not in {"Approve", "Reject", "Discussion"}:
        raise HTTPException(422, "Invalid leave decision")
    async with integrity_write(db):
        current = await find_linked_record(db.leave_requests, reference, user)
        employee = await authorize_employee(db, user, current.get("employee_id"), "M18", approve=True)
        if own(employee, user):
            raise HTTPException(403, "Employees cannot approve or reject their own requests")
        reject_identity_changes(body, current)
        history = list(current.get("approval_history", []))
        last = history[-1] if history else {}
        stage = body.get("stage") or await stage_for(db, user, current)
        replay = last.get("actor_id") == user["id"] and last.get("decision") == decision and last.get("reason", "") == body.get("reason", "") and last.get("stage") in {"manager", "hr"} and (not body.get("stage") or body["stage"] == last.get("stage"))
        if replay:
            result = current
        else:
            if current.get("status") not in PENDING:
                raise HTTPException(409, "This leave request is no longer awaiting a decision")
            if decision == "Reject" and user.get("role") in HR:
                stage = "hr"
            elif stage != await stage_for(db, user, current) or stage is None:
                raise HTTPException(403, "This approval stage is assigned to a different reviewer")
            if decision == "Approve":
                if current.get("policy_version") != VERSION:
                    raise HTTPException(409, "HR must supplement this legacy pending request before policy approval; historical records are unchanged")
                submitted = day(current["created_at"][:10])
                quote = await preview(db, employee, current, exclude=current["_id"], submitted_on=submitted)
                if quote["planned_handover_required"] and body.get("handover_reviewed") is not True:
                    raise HTTPException(422, "Written handover must be reviewed and signed off")
                if quote["planned_handover_required"]:
                    from utils.leave_policy import working_units
                    holidays = await db.public_holidays.find(tenant_query(tenant_of(user))).to_list(None)
                    dates = {row.get("date") for row in holidays}
                    deadline = day(current["start_date"]) - timedelta(days=1)
                    for _ in range(367):
                        if working_units(deadline.isoformat(), deadline.isoformat(), dates,
                                         quote["policy"]["saturday_weight"], quote["policy"].get("workday_weights")) > 0:
                            break
                        deadline -= timedelta(days=1)
                    else:
                        raise HTTPException(409, "The working calendar requires HR review")
                    reviewed = today() if stage == "manager" else day(current["manager_decided_at"][:10])
                    if reviewed > deadline:
                        raise HTTPException(422, "Manager handover sign-off must be completed by the last working day before leave")
                if stage == "hr":
                    if body.get("policy_review_confirmed") is not True:
                        raise HTTPException(422, "HR must confirm contract, holiday calendar, balance and eligibility review")
                    if quote["supporting_document_required"] and body.get("document_verified") is not True:
                        raise HTTPException(422, "HR must verify the supporting document")
                    if quote.get("compassionate_unpaid_days", 0) and not str(body.get("reason") or "").strip():
                        raise HTTPException(422, "Additional unpaid compassionate leave requires a documented HR exception")
                    if current["leave_type"] == "Annual":
                        await department_cover(db, employee, current)
                        if current["working_days"] > await availability(db, employee, await balance_loader(employee_key(employee)), exclude=current["_id"]):
                            raise HTTPException(422, "The recorded annual balance is no longer sufficient")
                    if current["leave_type"] == "Unpaid" and await availability(db, employee, await balance_loader(employee_key(employee)), exclude=current["_id"]) > 0:
                        raise HTTPException(422, "Annual leave must be exhausted before unpaid leave")
            now = stamp()
            status = "Rejected" if decision == "Reject" else "Discussion_Requested" if decision == "Discussion" else "Pending_HR" if stage == "manager" else "Approved"
            history.append({"stage": stage, "actor_id": user["id"], "actor_role": user["role"], "at": now, "decision": decision,
                            "reason": body.get("reason", ""), "handover_reviewed": body.get("handover_reviewed") is True,
                            "policy_review_confirmed": body.get("policy_review_confirmed") is True, "document_verified": body.get("document_verified") is True})
            update = {"status": status, "approval_history": history, "updated_at": now,
                      f"{stage}_decision": decision, f"{stage}_reason": body.get("reason", ""),
                      f"{stage}_decided_at": now, f"{stage}_decided_by": user["id"]}
            if status == "Approved":
                update.update(approved_at=now, hr_confirmed=True, document_verified=body.get("document_verified") is True)
                update.update(sick_pay=quote["sick_pay"], compassionate_paid_days=quote["compassionate_paid_days"],
                              compassionate_unpaid_days=quote["compassionate_unpaid_days"])
            result = await db.leave_requests.find_one_and_update({"_id": current["_id"]}, {"$set": update}, return_document=True)
            await audit(db, user, result, f"leave.{stage}.{decision.lower()}")
            if status == "Approved" and current.get("extended_sick_followup_required"):
                task_id = ObjectId(hashlib.sha256(f"leave-wellbeing:{tenant_of(current)}:{current['id']}".encode()).hexdigest()[:24])
                try:
                    await db.tasks.insert_one({"_id": task_id, "id": str(task_id), "tenant_id": tenant_of(current), "employee_id": current["employee_id"],
                                               "assigned_role": "hr_admin", "title": "Arrange extended-absence HR check-in", "status": "Pending", "created_at": stamp()})
                except DuplicateKeyError:
                    pass
    await notify(db, result, "decision")
    if not replay and result["status"] in {"Approved", "Rejected"}:
        await email_existing(db, employee, result, "decision")
    return await view(db, user, result)


async def supplement(db, user, reference, body):
    allowed = {"notes", "handover_contact_id", "supporting_document_id", "birth_date", "expected_delivery_date", "family_relationship", "emergency_sick", "early_maternity_advice"}
    if set(body) - allowed:
        raise HTTPException(403, "Dates, employee identity and approval fields cannot be changed through supporting information")
    async with integrity_write(db):
        current = await find_linked_record(db.leave_requests, reference, user)
        employee = await authorize_employee(db, user, current.get("employee_id"), "M18", write=True)
        if not own(employee, user) and user.get("role") not in HR:
            raise HTTPException(403, "Only the employee or HR may supplement this request")
        if current.get("status") not in PENDING:
            raise HTTPException(409, "Only pending requests may be supplemented")
        candidate = {**current, **body}
        submitted = day(str(current.get("created_at") or today().isoformat())[:10])
        quote = await preview(db, employee, candidate, exclude=current["_id"], submitted_on=submitted)
        if current.get("working_days") != quote["working_days"]:
            raise HTTPException(409, "Saved leave units differ from current policy. HR reconciliation or a replacement request is required; existing units were not changed")
        history = list(current.get("approval_history", []))
        for legacy_stage in ("manager", "hr"):
            if current.get(f"{legacy_stage}_decision") and not any(entry.get("stage") == legacy_stage for entry in history):
                history.append({"stage": legacy_stage, "decision": current[f"{legacy_stage}_decision"],
                                "actor_id": current.get(f"{legacy_stage}_decided_by", ""),
                                "at": current.get(f"{legacy_stage}_decided_at", ""), "reason": current.get(f"{legacy_stage}_reason", "")})
        history.append({"stage": "supplemented", "actor_id": user["id"], "actor_role": user["role"], "at": stamp()})
        covering = await find_employee(db, candidate.get("handover_contact_id"), tenant_of(user)) if candidate.get("handover_contact_id") else None
        update = {**body, "policy_version": VERSION, "policy_snapshot": quote, "status": "Pending_Manager",
                  "approval_history": history, "manager_decision": None, "manager_decided_by": None, "hr_decision": None,
                  "hr_decided_by": None, "document_verified": False, "supporting_document_present": quote["supporting_document_present"], "updated_at": stamp()}
        update["handover_contact"] = covering.get("full_name") if covering else None
        result = await db.leave_requests.find_one_and_update({"_id": current["_id"]}, {"$set": update}, return_document=True)
        await audit(db, user, result, "leave.supplemented")
    await notify(db, result, "supplemented")
    return await view(db, user, result)


async def cancel(db, user, reference, reason):
    async with integrity_write(db):
        current = await find_linked_record(db.leave_requests, reference, user)
        employee = await authorize_employee(db, user, current.get("employee_id"), "M18", write=True)
        if not own(employee, user):
            raise HTTPException(403, "Only the employee may withdraw their pending request")
        if current.get("status") == "Cancelled":
            return await view(db, user, current)
        if current.get("status") not in PENDING or day(current["start_date"]) <= today():
            raise HTTPException(409, "Only future pending leave can be withdrawn; contact HR for approved or started leave")
        history = list(current.get("approval_history", [])) + [{"stage": "cancelled", "actor_id": user["id"], "actor_role": user["role"], "at": stamp(), "reason": reason}]
        result = await db.leave_requests.find_one_and_update({"_id": current["_id"]}, {"$set": {"status": "Cancelled", "updated_at": stamp(), "approval_history": history}}, return_document=True)
        await audit(db, user, result, "leave.withdrawn")
    await notify(db, result, "withdrawn")
    return await view(db, user, result)
