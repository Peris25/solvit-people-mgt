"""Explicit initiation and assigned checklist operations over existing records."""
from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict
from database import get_db
from utils.auth import get_current_user
from utils.employee_access import find_linked_record, authorize_employee
from utils.employee_integrity import employee_key, find_employee, tenant_of, tenant_query, integrity_write
from utils import lifecycle_workflows as service

router = APIRouter(prefix="/lifecycle", tags=["employee lifecycle"])


class Initiate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    kind: Literal["onboarding", "offboarding"]
    last_working_day: Optional[date] = None
    authorization_reference: Optional[str] = None


class ChecklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["Pending", "In_Progress", "Completed"]
    document_id: Optional[str] = None


@router.post("/initiate")
async def initiate(body: Initiate, request: Request):
    user = await get_current_user(request)
    service.require_hr(user)
    db = get_db()
    async with integrity_write(db):
        employee = await authorize_employee(db, user, body.employee_id, "M04", write=True)
        await service.task_access(db, user, {"entity_id": employee_key(employee),
            "task_type": "exit_workflow" if body.kind == "offboarding" else "onboarding"}, write=True)
        if employee_key(employee) == user.get("employee_id"):
            raise HTTPException(403, "HR cannot initiate their own lifecycle approval")
        if body.kind == "onboarding":
            if employee.get("lifecycle_state") not in {"Onboarding", "Probation"}:
                raise HTTPException(409, "Employee must already be eligible for onboarding")
            from routes.onboarding import _create_onboarding_tasks
            existing = await db.onboarding_tasks.find(service.query(employee, entity_type="employee")).to_list(None)
            try:
                date.fromisoformat(employee.get("start_date", "")[:10])
            except (TypeError, ValueError):
                raise HTTPException(409, "HR must confirm an employment start date")
            if not existing:
                await service.audit(db, user, "onboarding.initiated", employee)
            await _create_onboarding_tasks(db, employee_key(employee), "employee", employee)
        else:
            if employee.get("lifecycle_state") in {"Exited", "Candidate"}:
                raise HTTPException(409, "Employee is not eligible for offboarding")
            if not body.last_working_day or not (body.authorization_reference or "").strip():
                raise HTTPException(422, "Confirmed last working day and HR authorization reference required")
            if employee.get("offboarding_started_at") and employee.get("last_working_day") != body.last_working_day.isoformat():
                raise HTTPException(409, "Existing exit date requires a separately approved amendment")
            if not employee.get("offboarding_started_at"):
                await service.audit(db, user, "offboarding.initiated", employee,
                                    authorization_reference=body.authorization_reference.strip(),
                                    last_working_day=body.last_working_day.isoformat())
                update = {"lifecycle_state": "Exiting", "last_working_day": body.last_working_day.isoformat(),
                          "offboarding_started_at": service.now()}
                await db.employees.update_one({"_id": employee["_id"]}, {"$set": update})
                employee.update(update)
            await service.create_exit_tasks(db, employee)
        await service.notify(db, employee, body.kind + ":initiated")
    return {"employee_id": employee_key(employee), "kind": body.kind}


@router.get("/checklists")
async def checklists(request: Request):
    user = await get_current_user(request)
    db = get_db()
    groups = {}
    for kind, collection, extra in (("onboarding", db.onboarding_tasks, {"entity_type": "employee"}),
                                     ("offboarding", db.tasks, {"task_type": "exit_workflow"})):
        rows = await collection.find({"$and": [tenant_query(tenant_of(user)), extra]}).to_list(None)
        for row in rows:
            try:
                employee = await service.task_access(db, user, row)
            except HTTPException as error:
                if error.status_code in (403, 404):
                    continue
                raise
            writable = True
            try:
                await service.task_access(db, user, row, write=True)
            except HTTPException:
                writable = False
            key = kind + ":" + str(employee["_id"])
            group = groups.setdefault(key, {"employee_id": employee_key(employee),
                "name": employee.get("full_name"), "kind": kind, "tasks": [],
                "last_working_day": employee.get("last_working_day"),
                "completed_at": employee.get("offboarding_completed_at")})
            group["tasks"].append(service.project(row, writable))
    for group in groups.values():
        tasks = group["tasks"]
        group["progress_pct"] = round(100 * sum(t["status"] == "Completed" for t in tasks) / len(tasks))
    return list(groups.values())


@router.put("/{kind}/tasks/{task_id}")
async def update_task(kind: Literal["onboarding", "offboarding"], task_id: str, body: ChecklistUpdate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        collection = db.onboarding_tasks if kind == "onboarding" else db.tasks
        current = await find_linked_record(collection, task_id, user)
        if (kind == "onboarding" and current.get("entity_type") != "employee") or (
                kind == "offboarding" and current.get("task_type") != "exit_workflow"):
            raise HTTPException(404, "Checklist item not found")
        return await service.update_checklist(db, user, collection, current, body.status, document_id=body.document_id)


@router.post("/offboarding/{employee_id}/complete")
async def complete(employee_id: str, request: Request):
    user = await get_current_user(request)
    service.require_hr(user)
    db = get_db()
    async with integrity_write(db):
        employee = await find_employee(db, employee_id, tenant_of(user))
        if not employee:
            raise HTTPException(404, "Employee not found")
        await service.task_access(db, user, {"entity_id": employee_key(employee), "task_type": "exit_workflow"}, write=True)
        await service.finalize_exit(db, user, employee)
    return {"status": "Completed"}


@router.post("/offboarding/{employee_id}/authorize-deactivation")
async def authorize_deactivation(employee_id: str, request: Request):
    user = await get_current_user(request)
    service.require_hr(user)
    db = get_db()
    async with integrity_write(db):
        employee = await find_employee(db, employee_id, tenant_of(user))
        if not employee or not employee.get("offboarding_started_at") or employee.get("lifecycle_state") != "Exiting":
            raise HTTPException(409, "HR-initiated offboarding is required")
        await service.task_access(db, user, {"entity_id": employee_key(employee), "task_type": "exit_workflow"}, write=True)
        if employee_key(employee) == user.get("employee_id"):
            raise HTTPException(403, "Employees cannot authorize their own deactivation")
        await service.audit(db, user, "offboarding.deactivation.scheduled", employee,
                            last_working_day=employee["last_working_day"])
        await db.employees.update_one({"_id": employee["_id"]}, {"$set": {
            "offboarding_deactivation_approved_by": user["id"],
            "offboarding_deactivation_approved_at": service.now()}})
    return {"status": "Authorized", "last_working_day": employee["last_working_day"]}
