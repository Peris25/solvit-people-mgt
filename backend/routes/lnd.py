from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.employee_integrity import user_employee_aliases, employee_key, integrity_write, tenant_of, tenant_query, resolve_user_employee
from utils import learning_workflows as learning
from utils.employee_access import authorize_employee, scoped_employee_query, reference_ids, find_linked_record, saved_manager, reject_identity_changes
from utils.auth import get_current_user
import uuid

router = APIRouter(prefix="/lnd", tags=["lnd"])


async def object_body(request):
    body = await request.json()
    if not isinstance(body, dict): raise HTTPException(422, "An object body is required")
    return body


@router.get("/programmes")
async def list_programmes(request: Request):
    user = await get_current_user(request)
    from utils.employee_access import personal_grant
    personal_grant(user,"M08")
    db=get_db()
    employee=await resolve_user_employee(db,user)
    hr=user.get("role") in learning.HR
    if not hr:
        if not employee: raise HTTPException(409,"An employee account link is required")
        await learning.employee_access(db,user,employee_key(employee),active=True)
    rows=await db.training_programmes.find(tenant_query(tenant_of(user))).sort("starts_on",1).to_list(None)
    result=[]
    for row in rows:
        if not hr:
            try: await learning.eligible(db,user,row,employee)
            except HTTPException as error:
                if error.status_code in (403,404,409): continue
                raise
        result.append({key:value for key,value in row.items() if key in learning.CATALOGUE_FIELDS|{"id","version","updated_at"}})
    return result


@router.post("/programmes")
async def create_programme(request: Request):
    user=await get_current_user(request)
    body=await object_body(request)
    db=get_db()
    async with integrity_write(db): return await learning.save_programme(db,user,body)


@router.put("/programmes/{programme_id}")
async def update_programme(programme_id: str, request: Request):
    user=await get_current_user(request)
    body=await object_body(request)
    db=get_db()
    async with integrity_write(db): return await learning.save_programme(db,user,body,programme_id)


@router.post("/programmes/{programme_id}/assign")
async def assign_programme(programme_id: str, request: Request):
    user=await get_current_user(request)
    learning.require_hr(user)
    body=await object_body(request)
    if set(body)-{"employee_ids","business_justification"}: raise HTTPException(422,"Unknown assignment fields")
    ids=body.get("employee_ids")
    if not isinstance(ids,list) or not ids or len(ids)>250 or any(not isinstance(ref,str) for ref in ids):
        raise HTTPException(422,"Select one to 250 employees")
    db=get_db()
    async with integrity_write(db):
        rows=[]; selected=set()
        for ref in ids:
            employee=await learning.employee_access(db,user,ref,write=True,active=True)
            if employee_key(employee) in selected: continue
            selected.add(employee_key(employee))
            rows.append(await learning.prepare_request(db,user,{"employee_id":employee_key(employee),"programme_id":programme_id,
                "business_justification":body.get("business_justification") or "HR training assignment"}))
        for row in rows: await learning.persist_request(db,user,row)
    return {"created":len(rows),"ids":[row["id"] for row in rows]}


@router.put("/training/{request_id}/completion")
async def complete_training(request_id: str, request: Request):
    user=await get_current_user(request)
    body=await object_body(request)
    db=get_db()
    async with integrity_write(db):
        row,employee=await learning.complete(db,user,request_id,body)
        return await learning.projection(db,user,row,employee)


class IDPCreate(BaseModel):
    employee_id: str
    career_aspiration: Optional[str] = None
    next_role_target: Optional[str] = None
    long_term_goal: Optional[str] = None
    skills_to_develop: Optional[List[str]] = []
    actions: Optional[List[dict]] = []  # [{action, owner, due_date, status}]
    training_required: Optional[str] = None
    mentor_request: Optional[str] = None
    stretch_assignments: Optional[str] = None
    goals: Optional[List[dict]] = []  # legacy


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    programme_id: Optional[str] = None
    training_name: Optional[str] = None
    provider: Optional[str] = None
    delivery_method: Optional[str] = None
    cost_kes: float = Field(default=0, ge=0, allow_inf_nan=False)
    duration_days: int = Field(default=1, ge=1, strict=True)
    link_to_idp_goal: Optional[str] = None
    business_justification: str
    proposed_start_date: Optional[str] = None
    proposed_end_date: Optional[str] = None

    @field_validator("cost_kes", mode="before")
    @classmethod
    def reject_boolean_cost(cls, value):
        if isinstance(value, bool): raise ValueError("Training cost must be numeric")
        return value


def fmt(doc):
    if not doc:
        return None
    doc["id"] = str(doc.get("id") or doc["_id"])
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("/idp/{employee_id}")
async def get_idp(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await learning.employee_access(db, user, employee_id)
    idp = await db.idps.find_one({"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": reference_ids(employee)+[employee["_id"]]}}]})
    if not idp:
        return {"employee_id": employee_id, "goals": [], "career_aspiration": None}
    return fmt(idp)


@router.post("/idp")
async def create_or_update_idp(idp: IDPCreate, request: Request):
    user=await get_current_user(request)
    db=get_db()
    async with integrity_write(db):
        employee=await learning.employee_access(db,user,idp.employee_id,write=True)
        query={"$and":[tenant_query(tenant_of(user)),{"employee_id":{"$in":reference_ids(employee)+[employee["_id"]]}}]}
        matches=await db.idps.find(query).to_list(2)
        if len(matches)>1: raise HTTPException(409,"IDP records need an integrity review")
        current=matches[0] if matches else None
        data=idp.model_dump(exclude_unset=bool(current))
        data.update(employee_id=employee_key(employee),updated_at=datetime.now(timezone.utc).isoformat())
        await learning.audit(db,user,"learning.idp.updated",current or {"id":employee_key(employee)},before=current,after=data)
        if current:
            await db.idps.update_one({"_id":current["_id"]},{"$set":data})
            return fmt({**current,**data})
        doc={"id":str(uuid.uuid4()),"tenant_id":tenant_of(user),**data,"created_at":datetime.now(timezone.utc).isoformat()}
        await db.idps.insert_one(doc)
        return {key:value for key,value in doc.items() if key!="_id"}


@router.post("/training/bulk-assign")
async def bulk_assign_training(request: Request):
    """Assign the same training to multiple employees at once. HR Admin / Manager only."""
    user = await get_current_user(request)
    if user.get("role") not in ("hr_admin", "hr_manager", "line_manager"):
        raise HTTPException(403, "Insufficient permissions")
    body = await object_body(request)
    ids = body.get("employee_ids")
    if not isinstance(ids,list) or not ids or len(ids)>250 or any(not isinstance(ref,str) for ref in ids):
        raise HTTPException(422,"Select one to 250 employees")
    db = get_db()
    async with integrity_write(db):
        rows=[]; selected=set()
        for ref in dict.fromkeys(ids):
            employee=await learning.employee_access(db,user,ref,write=True,active=True)
            if employee_key(employee) in selected: continue
            selected.add(employee_key(employee))
            data={**body,"employee_id":employee_key(employee),"provider":body.get("provider","Internal"),
                "delivery_method":body.get("delivery_method","Internal"),
                "business_justification":body.get("business_justification") or "Mandatory training nomination"}
            rows.append(await learning.prepare_request(db,user,data))
        for row in rows: await learning.persist_request(db,user,row)
    return {"status":"success","created":len(rows),"training_name":rows[0]["training_name"]}


@router.get("/training")
async def list_training_requests(request: Request, employee_id: Optional[str] = None, status: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    query = await scoped_employee_query(db, user, "M08", employee_id)
    if status:
        query = {"$and": [query, {"status": status}]}
    requests = await db.training_requests.find(learning.native_query(query)).sort("created_at", -1).to_list(None)
    result=[]
    for row in requests:
        try: employee=await learning.employee_access(db,user,row.get("employee_id"))
        except HTTPException as error:
            if error.status_code in (403,404): continue
            raise
        result.append(await learning.projection(db,user,row,employee))
    return result


@router.post("/training")
async def create_training_request(tr: TrainingRequest, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        row=await learning.prepare_request(db,user,tr.model_dump(exclude_none=True))
        await learning.persist_request(db,user,row)
        employee=await learning.employee_access(db,user,row["employee_id"])
        return await learning.projection(db,user,row,employee)


@router.put("/training/{request_id}/decision")
async def training_decision(request_id: str, request: Request):
    user=await get_current_user(request)
    body=await object_body(request)
    db=get_db()
    async with integrity_write(db):
        row,employee=await learning.decide(db,user,request_id,body)
        return await learning.projection(db,user,row,employee)


@router.get("/skills-matrix/{employee_id}")
async def get_skills_matrix(employee_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    employee = await learning.employee_access(db, user, employee_id)
    matrix = await db.skills_matrix.find_one({"$and": [tenant_query(tenant_of(user)), {"employee_id": {"$in": reference_ids(employee)+[employee["_id"]]}}]})
    if not matrix:
        return {"employee_id": employee_id, "skills": []}
    return fmt(matrix)


@router.post("/skills-matrix/{employee_id}")
async def update_skills_matrix(employee_id: str, request: Request):
    user=await get_current_user(request)
    body=await object_body(request)
    skills=body.get("skills")
    if not isinstance(skills,list) or len(skills)>200 or any(not isinstance(item,dict) or not isinstance(item.get("name"),str) or not item["name"].strip() or not isinstance(item.get("level"),str) for item in skills):
        raise HTTPException(422,"Provide a valid skills list")
    db=get_db()
    async with integrity_write(db):
        employee=await learning.employee_access(db,user,employee_id,write=True)
        matches=await db.skills_matrix.find({"$and":[tenant_query(tenant_of(user)),{"employee_id":{"$in":reference_ids(employee)+[employee["_id"]]}}]}).to_list(2)
        if len(matches)>1: raise HTTPException(409,"Skills records need an integrity review")
        current=matches[0] if matches else None
        data={"skills":skills,"updated_at":datetime.now(timezone.utc).isoformat()}
        await learning.audit(db,user,"learning.skills.updated",current or {"id":employee_key(employee)},before=current,after=data)
        if current:
            await db.skills_matrix.update_one({"_id":current["_id"]},{"$set":data})
            return fmt({**current,**data})
        doc={"id":str(uuid.uuid4()),"employee_id":employee_key(employee),"tenant_id":tenant_of(user),**data}
        await db.skills_matrix.insert_one(doc)
        return {key:value for key,value in doc.items() if key!="_id"}
