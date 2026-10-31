"""HR transcription of historical source records, separate from live approvals."""
from datetime import date
from hashlib import sha256
import json
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.employee_access import authorize_employee, find_linked_record, reference_ids
from utils.employee_integrity import employee_key, integrity_write, tenant_of, tenant_query
from utils.leave_workflow import stamp, view


class HistoricalFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leave_type: str
    start_date: date
    end_date: date
    resumption_date: date | None = None
    working_days: float = Field(gt=0, le=366, allow_inf_nan=False, strict=True)
    status: str
    day_basis: str = "Recorded units"

    @field_validator("leave_type")
    @classmethod
    def category(cls, value):
        if value not in {"Annual", "Sick", "Paternity", "Maternity", "Compassionate", "Unpaid"}:
            raise ValueError("Unrecognized historical leave category")
        return value

    @field_validator("status")
    @classmethod
    def state(cls, value):
        if value not in {"Approved", "Pending", "Recorded", "Rejected", "Cancelled"}:
            raise ValueError("Invalid historical status")
        return value

    @field_validator("day_basis")
    @classmethod
    def basis(cls, value):
        if value not in {"Recorded units", "Calendar days"}:
            raise ValueError("Invalid day basis")
        return value

    @model_validator(mode="after")
    def period(self):
        if self.end_date < self.start_date or self.end_date > date.today():
            raise ValueError("Historical dates must be ordered and not in the future")
        if self.start_date.year != self.end_date.year:
            raise ValueError("Split historical leave spanning calendar years")
        if self.working_days > (self.end_date - self.start_date).days + 1:
            raise ValueError("Recorded units exceed the calendar period")
        return self


class HistoricalRow(HistoricalFields):
    work_email: str = Field(min_length=3, max_length=254)
    source_key: str = Field(min_length=8, max_length=200)
    source_reference: str = Field(min_length=8, max_length=300)


class HistoricalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[HistoricalRow] = Field(min_length=1, max_length=100)
    preview_digest: str | None = Field(None, max_length=64)


class HistoricalCorrection(HistoricalFields):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=1000)


def require_hr(user):
    if user.get("role") not in {"hr_admin", "hr_manager"}:
        raise HTTPException(403, "Historical leave is managed by HR only")


async def prepare(db, user, batch):
    require_hr(user)
    employees = await db.employees.find(tenant_query(tenant_of(user))).to_list(None)
    proposed, keys = [], set()
    for item in batch.rows:
        email = item.work_email.strip().casefold()
        matches = [employee for employee in employees if str(employee.get("work_email") or "").strip().casefold() == email]
        if len(matches) != 1:
            raise HTTPException(409, "A source work email has no unique employee match; no records imported")
        employee = await authorize_employee(db, user, employee_key(matches[0]), "M18", write=True)
        key = sha256(f"{tenant_of(user)}:{item.source_key}".encode()).hexdigest()
        if key in keys:
            raise HTTPException(409, "Duplicate source rows in import")
        keys.add(key)
        existing = await db.leave_requests.find_one({"_id": f"history:{key}"})
        fields = item.model_dump(mode="json", exclude={"work_email", "source_key", "source_reference"})
        if not existing:
            for other in await db.leave_requests.find({"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": reference_ids(employee)}}]}).to_list(None):
                if other.get("status") not in {"Cancelled", "Rejected"} and other.get("start_date", "") <= fields["end_date"] and other.get("end_date", "") >= fields["start_date"]:
                    raise HTTPException(409, "An existing leave period overlaps a source row; review it before importing")
            for other in proposed:
                if other["employee_id"] == employee_key(employee) and other["start_date"] <= fields["end_date"] and other["end_date"] >= fields["start_date"]:
                    raise HTTPException(409, "Source leave periods overlap")
        elif existing.get("employee_id") != employee_key(employee):
            raise HTTPException(409, "Source identity is already assigned to another employee")
        proposed.append({**fields, "_id": f"history:{key}", "employee_id": employee_key(employee),
                         "employee_name": employee.get("full_name"), "source_reference": item.source_reference,
                         "source_key": item.source_key, "already_imported": bool(existing)})
    digest = sha256(json.dumps(proposed, sort_keys=True).encode()).hexdigest()
    return proposed, digest


async def import_rows(db, user, batch):
    require_hr(user)
    async with integrity_write(db):
        rows, digest = await prepare(db, user, batch)
        if batch.preview_digest != digest:
            raise HTTPException(409, "Preview the current import again before saving")
        created = skipped = 0
        for row in rows:
            if row["already_imported"]:
                skipped += 1
                continue
            record = {key: value for key, value in row.items() if key not in {"already_imported", "employee_name"}}
            record.update(id=str(uuid.uuid4()), tenant_id=tenant_of(user), historical_import=True, revision=1,
                          created_at=stamp(), updated_at=stamp(), approval_history=[])
            # Write intent first; audit failure must prevent the record write. A
            # write failure leaves an auditable intent, never a fabricated success.
            await history_audit(db, user, record, "leave.history.import", None)
            await db.leave_requests.insert_one(record)
            created += 1
        return {"created": created, "skipped": skipped}


async def history_audit(db, user, record, action, before, reason=None):
    await db.audit_logs.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_of(user), "actor_id": user["id"],
        "action": action, "entity_type": "leave", "entity_id": record["id"], "created_at": stamp(),
        "write_intent": True, "reason": reason,
        "before": before, "after": {key: record.get(key) for key in HistoricalFields.model_fields},
        "revision": record["revision"], "source_reference": record["source_reference"]})


async def correct(db, user, reference, body):
    require_hr(user)
    async with integrity_write(db):
        current = await find_linked_record(db.leave_requests, reference, user)
        await authorize_employee(db, user, current.get("employee_id"), "M18", write=True)
        if not current.get("historical_import"):
            raise HTTPException(409, "Live requests must use the existing approval workflow")
        if body.revision != current.get("revision"):
            raise HTTPException(409, "This record changed. Reload before correcting it")
        fields = body.model_dump(mode="json", exclude={"reason", "revision"})
        other_rows = await db.leave_requests.find({"$and": [tenant_query(tenant_of(user)), {"employee_id": current["employee_id"]}]}).to_list(None)
        for other in other_rows:
            if other["_id"] != current["_id"] and other.get("status") not in {"Cancelled", "Rejected"} and fields["status"] not in {"Cancelled", "Rejected"} and other.get("start_date", "") <= fields["end_date"] and other.get("end_date", "") >= fields["start_date"]:
                raise HTTPException(409, "Correction overlaps an existing leave period")
        candidate = {**current, **fields, "revision": body.revision + 1, "updated_at": stamp()}
        await history_audit(db, user, candidate, "leave.history.correct", {key: current.get(key) for key in HistoricalFields.model_fields}, body.reason)
        result = await db.leave_requests.update_one({"_id": current["_id"], "revision": body.revision}, {"$set": {**fields, "revision": candidate["revision"], "updated_at": candidate["updated_at"]}})
        if result.modified_count != 1:
            raise HTTPException(409, "Record changed. Reload before retrying")
        return await view(db, user, candidate)
