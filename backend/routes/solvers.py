from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db
from utils.auth import get_current_user
import uuid
import re
import math
from utils.employee_integrity import tenant_query, tenant_of, integrity_write
from utils.solver_access import (solver_access, authorize_solver, find_solver, own_solver, solver_view,
                                 solver_key, solver_aliases, manager_fields, solver_identity_write)
from utils.solver_access import audit_solver, HR_ROLES
from utils.solver_access import validate_directory_identities
from utils import solver_workflows as workflow

router = APIRouter(prefix="/solvers", tags=["solvers"])

SOLVER_STATES = ["Registering", "Active", "Suspended", "Inactive", "Deactivated"]
VEHICLE_CATEGORIES = ["Saloon", "SUV", "Pick-Up", "Van", "Truck", "Motorcycle"]
NAIROBI_ZONES = ["Zone 1: CBD", "Zone 2: Westlands-Kileleshwa", "Zone 3: Karen-Langata",
                  "Zone 4: Eastlands", "Zone 5: Thika Rd Corridor", "Zone 6: South B-South C"]


class SolverCreate(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    region: Optional[str] = None
    area_covered: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    nssf_number: Optional[str] = None
    sha_number: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mpesa_number: Optional[str] = None
    payment_method: str = "MPesa"
    vehicle_categories: Optional[List[str]] = []
    zones_covered: Optional[List[str]] = []
    driving_licence_type: Optional[str] = None
    driving_licence_number: Optional[str] = None
    driving_licence_expiry: Optional[str] = None


class SolverUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    region: Optional[str] = None
    area_covered: Optional[str] = None
    national_id_number: Optional[str] = None
    kra_pin: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mpesa_number: Optional[str] = None
    payment_method: Optional[str] = None
    vehicle_categories: Optional[List[str]] = None
    zones_covered: Optional[List[str]] = None
    lifecycle_state: Optional[str] = None
    accuracy_score: Optional[float] = None
    reliability_score: Optional[float] = None
    timeliness_score: Optional[float] = None
    client_rating_average: Optional[float] = None
    performance_tier: Optional[str] = None


async def directory_records(db, user):
    entry = await workflow.directory_access(db, user)
    if entry.get("scope") == "aggregate":
        return entry, []
    query = tenant_query(tenant_of(user))
    if entry.get("scope") == "own_record":
        own = await own_solver(db, user)
        # own_solver already checks canonical ambiguity and account ownership
        # against the entire tenant, including records outside this scope.
        return entry, [own]
    records = await db.solvers.find(query).sort("full_name", 1).to_list(None)
    validate_directory_identities(records)
    return entry, records


@router.get("")
async def list_solvers(request: Request, lifecycle_state: Optional[str] = None, search: Optional[str] = None,
                       region: Optional[str] = None, category: Optional[str] = None):
    user = await get_current_user(request)
    db = get_db()
    entry, records = await directory_records(db, user)
    if search and len(search) > 200:
        raise HTTPException(422, "Search must be within 200 characters")
    rows = []
    for record in records:
        row = workflow.view(record)
        if lifecycle_state and str(row['lifecycle_state']).casefold() != lifecycle_state.casefold(): continue
        if region and str(row.get('region') or '').strip().casefold() != region.strip().casefold(): continue
        if category and category not in row['vehicle_categories']: continue
        if search and search.strip().casefold() not in ' '.join(str(row.get(k) or '') for k in ('full_name','phone_number','email','region','area_covered')).casefold(): continue
        rows.append(workflow.directory_view(record) if entry.get('scope') == 'directory_only' else solver_view(record, user))
    if user.get("role") in HR_ROLES:
        await audit_solver(db, user, "solver.private_list.view", records)
    return rows


@router.get('/me')
async def my_solver(request: Request):
    user = await get_current_user(request)
    db = get_db()
    await solver_access(db, user)
    record = await own_solver(db, user)
    return solver_view(record, user)


@router.get('/directory-options')
async def directory_options(request: Request):
    user = await get_current_user(request)
    entry, records = await directory_records(get_db(), user)
    rows = [workflow.view(record) for record in records]
    return {'regions': sorted({str(r['region']) for r in rows if r.get('region')}),
            'categories': sorted({v for r in rows for v in r['vehicle_categories']}),
            'states': sorted({str(r['lifecycle_state']) for r in rows})}


@router.get("/stats")
async def get_solver_stats(request: Request):
    user = await get_current_user(request)
    db = get_db()
    entry = await workflow.directory_access(db, user)
    query = tenant_query(tenant_of(user))
    if entry.get("scope") == "own_record":
        own = await own_solver(db, user)
        query = {"$and": [query, {"_id": own["_id"]}]}
    records = await db.solvers.find(query).to_list(None)
    stats = {}
    for record in records:
        state = workflow.view(record)["lifecycle_state"]
        stats[state] = stats.get(state, 0) + 1
    return {"by_state": stats, "total": sum(stats.values()), "active": stats.get("Active", 0),
            "can_manage": entry.get("level") in ("Full", "Manage") and entry.get("scope") not in ("own_record", "aggregate", "directory_only"),
            "directory_only": entry.get("scope") == "directory_only"}


@router.post("")
async def create_solver(solver: SolverCreate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    await solver_access(db, user, write=True)
    supplied = solver.model_dump(exclude_none=True)
    manager_fields(user, supplied)
    solver_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        **supplied,
        "lifecycle_state": "Registering",
        "accuracy_score": None,
        "reliability_score": None,
        "timeliness_score": None,
        "client_rating_average": None,
        "performance_tier": None,
        "solver_agreement_signed": False,
        "solver_agreement_date": None,
        "activation_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    async with integrity_write(db):
        changes = await solver_identity_write(db, supplied, user)
        solver_doc.update(changes)
        result = await db.solvers.insert_one(solver_doc)
        solver_doc["_id"] = result.inserted_id
        await audit_solver(db, user, "solver.created", [solver_doc], supplied)
    from automation.engine import automation_engine
    await automation_engine.fire_event("solver_registered", {"solver_id": str(solver_doc["_id"]), "tenant_id": tenant_of(user)})
    return solver_view(solver_doc, user)


@router.get("/{solver_id}")
async def get_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id)
    if user.get("role") in HR_ROLES:
        await audit_solver(db, user, "solver.private_record.view", [record])
    return solver_view(record, user)


@router.put("/{solver_id}")
async def update_solver(solver_id: str, upd: SolverUpdate, request: Request):
    user = await get_current_user(request)
    db = get_db()
    supplied = upd.model_dump(exclude_none=True)
    await solver_access(db, user, write=True)
    manager_fields(user, supplied)
    if "lifecycle_state" in supplied and supplied["lifecycle_state"] not in SOLVER_STATES:
        raise HTTPException(422, "Invalid Solver lifecycle state")
    async with integrity_write(db):
        original = await authorize_solver(db, user, solver_id, write=True)
        readonly_scores = {'accuracy_score','reliability_score','timeliness_score','client_rating_average','performance_tier'}
        if any(key in supplied and supplied[key] != original.get(key) for key in readonly_scores):
            raise HTTPException(409, "Job-derived scores are read-only; use the audited rating workflow")
        if supplied.get('lifecycle_state') == 'Active' and original.get('lifecycle_state') != 'Active':
            raise HTTPException(409, "Use the verified activation action")
        update_data = await solver_identity_write(db, supplied, user, original)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await db.solvers.find_one_and_update(
            {"$and": [tenant_query(tenant_of(user)), {"_id": original["_id"]}]},
            {"$set": update_data}, return_document=True)
        if result:
            await audit_solver(db, user, "solver.updated", [result], update_data)
    if not result:
        raise HTTPException(404, "Solver not found")
    # Email the solver if a meaningful status/tier transition just happened
    try:
        from utils.email_triggers import fire_and_forget
        sol_email = result.get("email") or result.get("work_email")
        if sol_email:
            new_state = update_data.get("lifecycle_state")
            new_tier = update_data.get("performance_tier")
            solver_name = result.get("full_name")
            if new_state == "Suspended":
                await fire_and_forget(db, "solver.suspension", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "reason": update_data.get("suspension_reason") or "Performance review by Solver Manager",
                })
            elif new_state == "Active":
                await fire_and_forget(db, "solver.reactivation", to_override=sol_email, extra={
                    "solver_name": solver_name,
                })
            if new_tier in ("Top", "Premium"):
                await fire_and_forget(db, "solver.tier_upgrade", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "new_tier": new_tier,
                })
            elif new_tier in ("Bottom", "Probation"):
                await fire_and_forget(db, "solver.tier_downgrade", to_override=sol_email, extra={
                    "solver_name": solver_name,
                    "new_tier": new_tier,
                })
    except Exception:
        pass
    return solver_view(result, user)


@router.post("/{solver_id}/activate")
async def activate_solver(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        original = await authorize_solver(db, user, solver_id, write=True)
        if workflow.view(original)['lifecycle_state'] != 'Registering':
            raise HTTPException(409, "Activation is only available for registering Solvers; reactivation requires policy confirmation")
        await workflow.activation_ready(db, user, original)
        result = await db.solvers.find_one_and_update(
            {"$and": [tenant_query(tenant_of(user)), {"_id": original["_id"]}]},
            {"$set": {"lifecycle_state": "Active", "activation_date": datetime.now(timezone.utc).isoformat()[:10],
                      "activation_publication_state": "Pending_Audit",
                      "updated_at": datetime.now(timezone.utc).isoformat()}}, return_document=True)
        if result:
            await audit_solver(db, user, "solver.activated", [result], ["lifecycle_state", "activation_date"])
            await workflow.notify(db, result, "activated", result["activation_date"])
            tasks = await db.onboarding_tasks.find(workflow.task_query(original)).to_list(None)
            for task in tasks:
                if task.get('task_key') == 'S06':
                    await db.onboarding_tasks.update_one({'_id': task['_id']}, {'$set': {'status': 'Completed', 'completed_by': user['id'], 'completed_at': workflow.now()}})
            await db.solvers.update_one({'_id': original['_id']}, {'$set': {'activation_publication_state': 'Ready'}})
            result['activation_publication_state'] = 'Ready'

    if not result:
        raise HTTPException(404, "Solver not found")
    # Email the solver activation confirmation (best-effort)
    try:
        from utils.email_triggers import fire_and_forget
        sol_email = result.get("email") or result.get("work_email")
        if sol_email:
            await fire_and_forget(db, "solver.activation", to_override=sol_email, extra={
                "solver_name": result.get("full_name"),
                "activation_date": result.get("activation_date"),
            })
    except Exception:
        pass
    return solver_view(result, user)



@router.post("/{solver_id}/client-rating")
async def submit_client_rating(solver_id: str, request: Request):
    """Real-time client rating submission for a completed job (Fix 1).
    Body: { job_id, accuracy (0-100), timeliness (0-100), overall (0-100), client_id, comment }
    Writes the rating and recomputes the solver's 30-day / 90-day / all-time averages.
    """
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id, write=True)
    body = await request.json()
    for f in ("accuracy", "timeliness", "overall"):
        try:
            v = float(body.get(f))
        except (TypeError, ValueError):
            raise HTTPException(400, f"{f} must be a number 0-100")
        if not math.isfinite(v) or not (0 <= v <= 100):
            raise HTTPException(status_code=400, detail=f"{f} must be a number 0â€“100")
    rating_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_of(user),
        "solver_id": solver_key(record),
        "job_id": body.get("job_id"),
        "client_id": body.get("client_id"),
        "accuracy": float(body["accuracy"]),
        "timeliness": float(body["timeliness"]),
        "overall": float(body["overall"]),
        "comment": body.get("comment", ""),
        "submitted_by": user["id"],
        "voided": False,
        "void_reason": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    async with integrity_write(db):
        await authorize_solver(db, user, solver_id, write=True)
        job_id = body.get('job_id')
        if job_id is not None:
            if not isinstance(job_id, str) or not job_id.strip() or len(job_id) > 200:
                raise HTTPException(422, 'Invalid job reference')
            rating_doc['job_id'] = job_id.strip()
            if await db.solver_ratings.find_one({'$and': [tenant_query(tenant_of(user)), {'solver_id': {'$in': solver_aliases(record)}, 'job_id': rating_doc['job_id'], 'voided': False}]}):
                raise HTTPException(409, 'A rating is already recorded for this Solver job')
        await db.solver_ratings.insert_one(rating_doc)
        await _recompute_solver_averages(db, solver_key(record), user)
    await audit_solver(db, user, "solver.rating.created", [record], ["accuracy", "timeliness", "overall"])
    return {"submitted": True, "rating_id": rating_doc["id"]}


async def _recompute_solver_averages(db, solver_id: str, user):
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()
    record = await find_solver(db, solver_id, user)
    all_ratings = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)),
        {"solver_id": {"$in": solver_aliases(record)}, "voided": False}]}).to_list(None)

    def _avg(ratings, field):
        if not ratings: return None
        return round(sum(r[field] for r in ratings) / len(ratings), 1)

    r_30 = [r for r in all_ratings if r["created_at"] >= cutoff_30]
    r_90 = [r for r in all_ratings if r["created_at"] >= cutoff_90]
    latest = max(all_ratings, key=lambda r: r["created_at"]) if all_ratings else None
    update = {
        "latest_client_rating": latest["overall"] if latest else None,
        "latest_rating_at": latest["created_at"] if latest else None,
        "client_rating_30d": _avg(r_30, "overall"),
        "client_rating_90d": _avg(r_90, "overall"),
        "accuracy_score": _avg(all_ratings, "accuracy"),
        "timeliness_score": _avg(all_ratings, "timeliness"),
        "client_rating_average": _avg(all_ratings, "overall"),
        "updated_at": now.isoformat(),
    }
    await db.solvers.update_one({"$and": [tenant_query(tenant_of(user)), {"_id": record["_id"]}]}, {"$set": update})


@router.get("/{solver_id}/ratings")
async def list_solver_ratings(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    if user.get("role") == "it_admin":
        record = await find_solver(db, solver_id, user)  # Existing rating-audit exception only.
    else:
        record = await authorize_solver(db, user, solver_id)
    ratings = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)),
        {"solver_id": {"$in": solver_aliases(record)}}]}).sort("created_at", -1).to_list(200)
    return [{"id": str(r["_id"]), "accuracy": r.get("accuracy"), "timeliness": r.get("timeliness"),
             "overall": r.get("overall"), "created_at": r.get("created_at"), "voided": r.get("voided", False)}
            for r in ratings]


@router.post("/ratings/{rating_id}/void")
async def void_rating(rating_id: str, request: Request):
    """IT Admin only â€” void a rating with a mandatory reason (Fix 1)."""
    user = await get_current_user(request)
    if user["role"] != "it_admin":
        raise HTTPException(status_code=403, detail="Only IT Admin can void ratings")
    body = await request.json()
    reason = (body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="A void reason of â‰¥5 characters is required")
    db = get_db()
    clauses = [{"id": rating_id}, {"_id": rating_id}]
    if ObjectId.is_valid(rating_id):
        clauses.append({"_id": ObjectId(rating_id)})
    async with integrity_write(db):
        found = await db.solver_ratings.find({"$and": [tenant_query(tenant_of(user)), {"$or": clauses}]}).to_list(2)
        if len(found) != 1:
            raise HTTPException(409 if found else 404, "Rating not found or ambiguous")
        rating = found[0]
        await find_solver(db, rating.get("solver_id"), user)
        await db.solver_ratings.update_one({"$and": [tenant_query(tenant_of(user)), {"_id": rating["_id"]}]},
            {"$set": {"voided": True, "void_reason": reason, "voided_by": user["id"],
                      "voided_at": datetime.now(timezone.utc).isoformat()}})
        await _recompute_solver_averages(db, rating["solver_id"], user)
    await audit_solver(db, user, "solver.rating.voided", [await find_solver(db, rating["solver_id"], user)], ["voided"])
    return {"voided": True}


@router.get('/{solver_id}/workflow')
async def solver_workflow(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    record = await authorize_solver(db, user, solver_id)
    tasks = await db.onboarding_tasks.find(workflow.task_query(record)).to_list(None)
    gates = await workflow.verification(db, user, record)
    assessments = await db.form_submissions.find({'$and': [tenant_query(tenant_of(user)),
        {'$or': [{'subject_solver_id': {'$in': solver_aliases(record)}},
                 {'data.solver_id': {'$in': solver_aliases(record)}}]},
        {'form_id': {'$in': ['form-02', 'form-03', 'form-25']}, 'workflow_kind': {'$ne': 'solver_assessment_v1'}}]}).to_list(None)
    private = user.get('role') in HR_ROLES or (await solver_access(db, user)).get('scope') == 'solvers_manager'
    reviews = await db.solver_assessment_reviews.find({'$and': [tenant_query(tenant_of(user)),
        {'solver_id': {'$in': solver_aliases(record)}}]}).to_list(None)
    return {'solver_id': solver_key(record), 'can_manage': private,
        'can_upload': user.get('role') in HR_ROLES,
        'tasks': [{key: row.get(key) for key in ('id','task_key','title','status','due_date','completed_at')} for row in tasks],
        'verification': [{ 'gate': gate, 'verified': bool(row.get('verified')), 'created_at': row.get('created_at'),
                          **({'document_id': row.get('document_id'), 'reference': row.get('reference'),
                              'score': row.get('score'), 'maximum': row.get('maximum'), 'outcome': row.get('outcome')} if private else {})} for gate,row in gates.items()],
        'assessments': [{**{key: row.get(key) for key in ('id','form_id','form_title','status','score','passed','pass_mark','submitted_at')},
                         'reviewed': any(review.get('assessment_id') == str(row.get('id') or row['_id']) and review.get('publication_state') == 'Ready' for review in reviews)} for row in assessments],
        'assessment_notice': 'Historical results are preserved. Post-interview Parts A/B require the approved question/case bank and Masters scoring configuration.'}


@router.post('/{solver_id}/induction')
async def initiate_induction(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        record = await authorize_solver(db, user, solver_id, write=True)
        if workflow.view(record)['lifecycle_state'] != 'Registering':
            raise HTTPException(409, 'Induction initiation requires a registering Solver')
        from routes.onboarding import _create_solver_induction
        await _create_solver_induction(db, solver_key(record), record)
        await audit_solver(db, user, 'solver.induction.initiated', [record])
        await workflow.notify(db, record, 'initiated', 'initial')
    return {'initiated': True}


@router.post('/{solver_id}/verification')
async def verify_induction(solver_id: str, request: Request):
    user = await get_current_user(request)
    db = get_db()
    body = await request.json()
    async with integrity_write(db):
        record = await authorize_solver(db, user, solver_id, write=True)
        if workflow.view(record)['lifecycle_state'] != 'Registering':
            raise HTTPException(409, 'Verification requires a registering Solver')
        return await workflow.verify_gate(db, user, record, body)


@router.post('/{solver_id}/assessments/{assessment_id}/review')
async def review_solver_assessment(solver_id: str, assessment_id: str, request: Request):
    from utils.employee_access import find_linked_record
    user = await get_current_user(request)
    db = get_db()
    async with integrity_write(db):
        record = await authorize_solver(db, user, solver_id, write=True)
        assessment = await find_linked_record(db.form_submissions, assessment_id, user)
        subject = assessment.get('subject_solver_id') or (assessment.get('data') or {}).get('solver_id')
        if subject not in solver_aliases(record) or assessment.get('form_id') not in {'form-02', 'form-03', 'form-25'}:
            raise HTTPException(403, 'Assessment does not belong to this Solver')
        if assessment.get('status') not in {'Submitted', 'Completed'}:
            raise HTTPException(409, 'Assessment is not ready for review')
        query = {'tenant_id': tenant_of(user), 'solver_id': solver_key(record), 'assessment_id': str(assessment.get('id') or assessment['_id'])}
        existing = await db.solver_assessment_reviews.find_one(query)
        if existing and existing.get('publication_state') != 'Ready':
            raise HTTPException(409, 'This review requires administrator recovery before retrying')
        if not existing:
            await db.solver_assessment_reviews.insert_one({**query, 'id': str(uuid.uuid4()),
                'reviewed_by': user['id'], 'created_at': workflow.now(),
                'publication_state': 'Pending_Audit',
                'recorded_outcome': 'Pass' if assessment.get('passed') is True else 'Fail' if assessment.get('passed') is False else 'Not recorded'})
            await audit_solver(db, user, 'solver.assessment.reviewed', [record], ['assessment_id'])
            await workflow.notify(db, record, 'assessment_reviewed', query['assessment_id'])
            await db.solver_assessment_reviews.update_one(query, {'$set': {'publication_state': 'Ready'}})
    return {'reviewed': True, 'scores_changed': False}


@router.get('/{solver_id}/documents')
async def solver_documents(solver_id: str, request: Request):
    from utils import solver_documents as service
    user = await get_current_user(request)
    return await service.listing(get_db(), user, solver_id)


@router.post('/{solver_id}/documents')
async def upload_solver_document(solver_id: str, request: Request, file: UploadFile = File(...),
                                 category: str = Form(...), visibility: str = Form('hr_only'), confidential: bool = Form(True)):
    from utils import solver_documents as service
    user = await get_current_user(request)
    return await service.upload(get_db(), user, solver_id, file, category, visibility, confidential)


@router.get('/{solver_id}/documents/{document_id}/download')
async def download_solver_document(solver_id: str, document_id: str, request: Request):
    from utils import solver_documents as service
    user = await get_current_user(request)
    return await service.download(get_db(), user, solver_id, document_id)
