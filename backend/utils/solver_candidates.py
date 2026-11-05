"""Editable intake applicants with explicit HR-only confirmation into Solvers."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from fastapi import HTTPException
from utils.access_matrix import get_module_access
from utils.employee_integrity import tenant_of, tenant_query, normalize_email, email_matches
from utils.employee_access import find_linked_record
from utils.solver_access import solver_access, solver_identity_write, normalize_phone, HR_ROLES
from utils.solver_cv import available_cv_path

STAGES = ('Eligible', 'Interviewing', 'Awaiting assessment', 'Passed', 'Awaiting confirmation', 'Active', 'On hold', 'Not selected', 'Withdrawn')


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=10, max_length=1500)
    full_name: str | None = Field(None, min_length=2, max_length=200)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, max_length=40)
    county: str | None = Field(None, max_length=100)
    town_area: str | None = Field(None, max_length=200)
    stage: str | None = None
    confirm_active: bool = False


def version(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def stage(row):
    saved = row.get('solver_recruitment_stage')
    if saved in STAGES: return saved
    if row.get('solver_id'): return 'Active'
    old = str(row.get('current_stage') or '')
    if old in STAGES and old != 'Active': return old
    if old == 'Active': return 'Awaiting confirmation'
    if 'Stage 1' in old and 'Passed' in old: return 'Eligible'
    if 'Interview' in old or 'Interview' in old.title(): return 'Interviewing'
    if 'Assessment' in old or 'Competency' in old: return 'Awaiting assessment'
    if old in {'Offer Accepted', 'Offer_Accepted'}: return 'Awaiting confirmation'
    return None


async def permissions(db, user, write=False):
    entry = await solver_access(db, user, write=write)
    assessment = get_module_access('M03', user.get('role'))
    if entry.get('scope') not in (None, 'solvers_manager') or not assessment or (write and assessment.get('level') not in {'Manage', 'Full'}):
        raise HTTPException(403, 'HR / authorized Solvers Manager access required')


async def editable(db, user):
    try: await permissions(db, user, write=True); return True
    except HTTPException as error:
        if error.status_code != 403: raise
        return False


def projection(row, can_edit, can_confirm):
    out = {key: value for key, value in row.items() if key not in {'_id', 'cv_path', 'stored_path', 'password_hash', 'otp_code', 'access_token', 'submitted_ip'}}
    out.update(recruitment_stage=stage(row) or row.get('current_stage') or 'Needs review',
               edit_version=version(row), can_edit=can_edit and not row.get('solver_id') and not row.get('employee_id'),
               can_confirm=can_confirm, has_cv=available_cv_path(row) is not None)
    return out


async def record(db, user, reference):
    row = await find_linked_record(db.candidates, reference, user)
    if row.get('candidate_type') != 'Solver' or not row.get('requisition_id'):
        raise HTTPException(404, 'Eligible Solver applicant not found')
    return row


async def update(db, user, reference, body):
    await permissions(db, user, write=True)
    row = await record(db, user, reference)
    if body.expected_version != version(row): raise HTTPException(409, 'Applicant changed. Close and reopen the record before saving.')
    if row.get('solver_id'): raise HTTPException(409, 'Confirmed Solvers are edited in the Solver directory; applicant history is retained.')
    if row.get('employee_id'): raise HTTPException(409, 'This applicant is already linked to an employee record; review that link before changing recruitment status.')
    reason = body.reason.strip()
    if len(reason) < 10: raise HTTPException(422, 'Record a clear reason for this change')
    values = body.model_dump(exclude_unset=True)
    update = {key: value for key, value in values.items() if key in {'full_name', 'email', 'phone_number', 'county', 'town_area'}}
    update = {key: value for key, value in update.items() if value != row.get(key)}
    for key, value in update.items():
        if key in {'county', 'town_area'} and value in (None, ''):
            update[key] = None
            continue
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value): raise HTTPException(422, 'Enter valid applicant details')
        update[key] = value.strip()
        if key == 'full_name' and len(update[key]) < 2: raise HTTPException(422, 'Enter a full applicant name')
    if 'email' in update:
        update['email'] = normalize_email(update['email'])
        matches = await email_matches(db.candidates, 'email', update['email'], tenant_of(user))
        if any(m['_id'] != row['_id'] for m in matches): raise HTTPException(409, 'Another applicant already uses this email')
    if 'phone_number' in update:
        normalized = normalize_phone(update['phone_number'])
        for other in await db.candidates.find(tenant_query(tenant_of(user))).to_list(None):
            if other['_id'] == row['_id'] or not other.get('phone_number'): continue
            try: existing = normalize_phone(other['phone_number'])
            except HTTPException: continue
            if existing == normalized: raise HTTPException(409, 'Another applicant already uses this phone number')
        if update['phone_number'] != row.get('phone_number'): update['phone_number'] = normalized
    requested = body.stage
    if requested is not None and requested not in STAGES: raise HTTPException(422, 'Choose a supported recruitment stage')
    merged = {**row, **update}
    now = datetime.now(timezone.utc).isoformat()
    solver = None
    if requested == 'Active':
        if user.get('role') not in HR_ROLES: raise HTTPException(403, 'Only HR can confirm an Active Solver')
        if not body.confirm_active or stage(row) not in {'Passed', 'Awaiting confirmation'}:
            raise HTTPException(409, 'Record Passed or Awaiting confirmation first, then explicitly confirm activation')
        prior = await db.solvers.find({'$and': [tenant_query(tenant_of(user)), {'source_candidate_id': row['id']}]}).to_list(2)
        if len(prior) > 1: raise HTTPException(409, 'Duplicate candidate-linked Solvers require review')
        if prior:
            solver = prior[0]
            if solver.get('lifecycle_state') != 'Active' or not solver.get('activation_confirmed_by'):
                raise HTTPException(409, 'Existing candidate-linked Solver requires HR review; it has not been changed')
        else:
            identity = await solver_identity_write(db, {'full_name': merged['full_name'], 'email': merged.get('email'), 'phone_number': merged.get('phone_number')}, user)
            solver = {'id': str(uuid.uuid4()), 'tenant_id': tenant_of(user), **identity,
                      'county': merged.get('county'), 'area_covered': merged.get('town_area'),
                      'lifecycle_state': 'Active', 'activation_date': now[:10], 'activation_confirmed_by': user['id'],
                      'source_candidate_id': row['id'], 'created_at': now, 'updated_at': now,
                      'activation_publication_state': 'Pending_Audit'}
        update.update(solver_id=solver['id'], status='Converted')
    elif requested and requested != stage(row):
        update['status'] = {'Not selected': 'Rejected', 'Withdrawn': 'Withdrawn'}.get(requested, 'Active')
    if requested and requested != stage(row):
        update.update(solver_recruitment_stage=requested, current_stage=requested, current_stage_status='Confirmed' if requested == 'Active' else requested, stage_entered_date=now)
    update = {key: value for key, value in update.items() if value != row.get(key)}
    if not update: return projection(row, True, user.get('role') in HR_ROLES)
    await db.audit_logs.insert_one({'tenant_id': tenant_of(user), 'event': 'solver.applicant.updated', 'entity_id': row['id'],
        'actor_id': user['id'], 'timestamp': now, 'metadata': {'fields': sorted(update), 'previous_stage': stage(row), 'stage': requested or stage(row), 'reason': reason}})
    if solver is not None:
        if not solver.get('_id'): await db.solvers.insert_one(solver)
    await db.candidates.update_one({'_id': row['_id']}, {'$set': {**update, 'updated_at': now}})
    if solver is not None:
        await db.solvers.update_one({'id': solver['id'], 'tenant_id': tenant_of(user)}, {'$set': {'activation_publication_state': 'Ready'}})
    return projection({**row, **update, 'updated_at': now}, True, user.get('role') in HR_ROLES)
