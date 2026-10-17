"""Approved benefit schemes and HR-reviewed membership; never a payroll engine."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import hashlib
import math
import uuid
from fastapi import HTTPException
from utils.access_matrix import get_module_access
from utils.employee_integrity import employee_key, resolve_user_employee, tenant_of, tenant_query, find_employee
from utils.employee_access import personal_grant, find_linked_record, reference_ids
from utils.staff_directory import employment_type, normalized
from utils.staff_views import restricted

HR = {'hr_admin', 'hr_manager'}
SCHEME = {'title','insurer','policy_number','cover_type','cover_levels','starts_on','ends_on','renewal_on',
          'worker_types','minimum_service_days','max_dependants','enrolment_deadline','insurer_contact',
          'claim_instructions','approval_reference','status'}


def now(): return datetime.now(timezone.utc).isoformat()
def today(): return datetime.now(timezone(timedelta(hours=3))).date()
def fail(message, status=422): raise HTTPException(status, message)
def text(value, label, limit=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value): fail('A valid '+label+' is required')
    return value.strip()
def day(value):
    if not isinstance(value,str) or len(value)!=10: fail('Dates must use YYYY-MM-DD')
    try: return date.fromisoformat(value)
    except ValueError: fail('Invalid date')
def integer(value, maximum):
    if type(value)!=int or not 0<=value<=maximum: fail('Invalid eligibility limit')
    return value

def privileged(user, finance=False, write=False):
    roles={'finance'} if finance else HR
    entry=get_module_access('M10',user.get('role'))
    if user.get('role') not in roles or not entry or entry.get('level') not in ({'Manage','Full'} if write else {'Read','Manage','Full'}): fail('Benefits administration is not authorized',403)
    if not finance: personal_grant(user,'M01',write=write)

async def self_employee(db,user):
    personal_grant(user,'M01')
    employee=await resolve_user_employee(db,user)
    if not employee: fail('An employee account link is required',409)
    if restricted(employee.get('board_only')) or normalized(employee.get('lifecycle_state') or employee.get('status')) not in {'active','onboarding','probation','onleave','pip','realignment'}: fail('Benefits self-service is unavailable for this classification or status',403)
    return employee

async def audit(db,user,event,reference,**metadata):
    await db.audit_logs.insert_one({'tenant_id':tenant_of(user),'event':event,'entity_id':str(reference),'actor_id':user['id'],'timestamp':now(),'metadata':metadata})

async def notify(db,row,event):
    recipients=[('employee',row['employee_id']),('role','hr_admin'),('role','hr_manager')]
    for kind,recipient in recipients:
        key='benefit:'+hashlib.sha256(f"{tenant_of(row)}:{row['id']}:{event}:{kind}:{recipient}".encode()).hexdigest()
        await db.notifications.update_one({'_id':key},{'$setOnInsert':{'id':key,'tenant_id':tenant_of(row),'category':'Benefits','created_at':now(),
            **({'recipient_type':'employee','recipient_id':recipient} if kind=='employee' else {'recipient_role':recipient}),
            'data':{'employee_id':row['employee_id'],'benefit_request_id':row['id']}}},upsert=True)

async def scheme(db,user,reference):
    if not isinstance(reference,str): fail('Invalid scheme identifier')
    return await find_linked_record(db.benefit_schemes,reference,user)

def scheme_view(row):
    return {'id':str(row.get('id') or row['_id']),**{key:deepcopy(row[key]) for key in SCHEME if key in row}}

def eligible(row,employee):
    if row.get('status')!='Published' or not row.get('approval_reference') or restricted(employee.get('board_only')) or normalized(employee.get('lifecycle_state') or employee.get('status')) not in {'active','onboarding','probation','onleave','pip','realignment'}: return False
    current=today()
    try:
        return (day(row['starts_on'])<=current<=day(row['ends_on']) and day(employee['start_date'])+timedelta(days=row['minimum_service_days'])<=current and
            employment_type(employee.get('employment_type')) in {employment_type(v) for v in row['worker_types']})
    except (KeyError,TypeError,ValueError,HTTPException): return False

async def save_scheme(db,user,body,reference=None):
    privileged(user,write=True)
    if not isinstance(body,dict) or set(body)-SCHEME: fail('Unknown or Finance-only scheme fields')
    previous=await scheme(db,user,reference) if reference else None
    # Approved policy definitions are versioned by creating a replacement, not by changing existing membership terms.
    if previous and (previous.get('published_at') or previous.get('status')=='Published') and set(body)-{'status'}: fail('Create a replacement scheme to change published policy terms',409)
    row={**(previous or {}),**body}
    for key in ('title','insurer','policy_number','insurer_contact','claim_instructions'): row[key]=text(row.get(key),key)
    if row.get('cover_type') not in ('Medical','Accident'): fail('Choose Medical or Accident cover')
    if row.get('status','Draft') not in ('Draft','Published','Archived'): fail('Invalid scheme status')
    row['status']=row.get('status','Draft')
    for key in ('cover_levels','worker_types'):
        values=row.get(key)
        if not isinstance(values,list) or not values or len(values)>30: fail('Provide explicit cover levels and eligible worker types')
        row[key]=list(dict.fromkeys(text(value,key,150) for value in values))
    for key in ('starts_on','ends_on','renewal_on','enrolment_deadline'): row[key]=day(row.get(key)).isoformat()
    if row['ends_on']<row['starts_on'] or row['enrolment_deadline']>row['ends_on']: fail('Invalid policy period or enrolment deadline')
    row['minimum_service_days']=integer(row.get('minimum_service_days'),36500)
    row['max_dependants']=integer(row.get('max_dependants'),30)
    if row['status']=='Published': row['approval_reference']=text(row.get('approval_reference'),'HR/Finance policy approval reference')
    else: row['approval_reference']=text(row['approval_reference'],'approval reference') if row.get('approval_reference') else None
    if row['status']=='Published': row['published_at']=(previous or {}).get('published_at') or now()
    row.update(id=(previous or {}).get('id') or str(uuid.uuid4()),tenant_id=tenant_of(user),updated_at=now())
    await audit(db,user,'benefits.scheme.saved',row['id'],before=scheme_view(previous) if previous else None,after=scheme_view(row))
    if previous: await db.benefit_schemes.update_one({'_id':previous['_id']},{'$set':{k:v for k,v in row.items() if k!='_id'}})
    else: await db.benefit_schemes.insert_one(row)
    return scheme_view(row)

async def evidence(db,user,employee,reference):
    from routes.documents import _visible, _restricted
    if not isinstance(reference,str): fail('Select an authorized Document Centre record')
    doc=await find_linked_record(db.employee_documents,reference,user)
    if doc.get('employee_id') not in reference_ids(employee)+[employee['_id']] or doc.get('deleted_at') or doc.get('publication_state') not in (None,'Ready') or _restricted(doc) or not _visible(doc,employee,user): fail('Supporting document is unavailable or not authorized',403)
    return doc

async def memberships(db,user,employee):
    return await db.benefit_requests.find({'$and':[tenant_query(tenant_of(user)),{'employee_id':{'$in':reference_ids(employee)+[employee['_id']]}}]}).sort('created_at',-1).to_list(None)

async def submit(db,user,body):
    # Like profile-change requests, own M01 read access permits a request, never an approved employee mutation.
    personal_grant(user,'M01')
    employee=await self_employee(db,user)
    user={**user,'employee_id':employee_key(employee)}
    allowed={'scheme_id','cover_level','dependants','beneficiaries','reason','supporting_document_id','confirm_cover'}
    if not isinstance(body,dict) or set(body)-allowed: fail('Only your own benefit membership may be requested')
    row=await scheme(db,user,body.get('scheme_id'))
    if not eligible(row,employee): fail('You are not eligible for this published scheme',403)
    if body.get('confirm_cover') is not True: fail('Confirm your selected cover')
    if body.get('cover_level') not in row['cover_levels']: fail('Choose an approved cover level')
    history=[r for r in await memberships(db,user,employee) if r.get('scheme_id')==row['id']]
    if any(r.get('status')=='Pending_HR' for r in history): fail('A membership request is already awaiting HR review',409)
    superseded={r.get('supersedes_id') for r in history if r.get('status')=='Approved'}
    approved_rows=[r for r in history if r.get('status')=='Approved' and r.get('id') not in superseded]
    if len(approved_rows)>1: fail('Conflicting approved memberships require HR reconciliation',409)
    approved=approved_rows[0] if approved_rows else None
    if not approved and today().isoformat()>row['enrolment_deadline']: fail('Enrolment deadline has passed; contact HR',409)
    reason=body.get('reason')
    if approved:
        if reason not in ('Marriage','Birth','Adoption','Dependant leaving cover'): fail('Choose a documented membership change reason')
        await evidence(db,user,employee,body.get('supporting_document_id'))
    elif reason not in (None,'Enrolment'): fail('Initial membership must be an enrolment')
    if body.get('supporting_document_id') and not approved: await evidence(db,user,employee,body['supporting_document_id'])
    dependants=body.get('dependants',[])
    if not isinstance(dependants,list) or len(dependants)>row['max_dependants']: fail('Too many dependants for this scheme')
    clean=[]
    for item in dependants:
        if not isinstance(item,dict) or set(item)-{'name','date_of_birth','relationship','document_id'}: fail('Invalid dependant fields; medical information must not be stored')
        dob=day(item.get('date_of_birth'))
        if dob>today(): fail('Dependant date of birth cannot be in the future')
        await evidence(db,user,employee,item.get('document_id'))
        clean.append({'name':text(item.get('name'),'dependant name',160),'date_of_birth':dob.isoformat(),'relationship':text(item.get('relationship'),'relationship',80),'document_id':item['document_id']})
    if len({(normalized(item['name']),item['date_of_birth']) for item in clean})!=len(clean): fail('Duplicate dependant entries')
    beneficiaries=body.get('beneficiaries',[])
    if not isinstance(beneficiaries,list) or len(beneficiaries)>30: fail('Invalid beneficiaries')
    normalized_beneficiaries=[]
    for item in beneficiaries:
        if not isinstance(item,dict) or set(item)-{'name','relationship','percentage'}: fail('Invalid beneficiary fields')
        percentage=item.get('percentage')
        if type(percentage) not in (int,float) or not math.isfinite(percentage) or not 0<percentage<=100: fail('Invalid beneficiary percentage')
        normalized_beneficiaries.append({'name':text(item.get('name'),'beneficiary name',160),'relationship':text(item.get('relationship'),'relationship',80),'percentage':percentage})
    if row['cover_type']=='Accident' and (not normalized_beneficiaries or abs(sum(r['percentage'] for r in normalized_beneficiaries)-100)>0.000001): fail('Accident beneficiary shares must total 100%')
    if row['cover_type']=='Medical' and normalized_beneficiaries: fail('Beneficiaries apply to accident cover')
    request={'id':str(uuid.uuid4()),'tenant_id':tenant_of(user),'employee_id':employee_key(employee),'scheme_id':row['id'],'scheme_title':row['title'],
        'scheme_snapshot':scheme_view(row),'cover_type':row['cover_type'],'cover_level':body['cover_level'],'dependants':clean,'beneficiaries':normalized_beneficiaries,
        'reason':reason or 'Enrolment','supporting_document_id':body.get('supporting_document_id'),'status':'Pending_HR','created_at':now(),
        'submitted_by':user['id'],'supersedes_id':approved['id'] if approved else None}
    await audit(db,user,'benefits.membership.requested',request['id'],scheme_id=row['id'])
    await db.benefit_requests.insert_one(request)
    await notify(db,request,'requested')
    return request_view(request,employee,user,personal=True)


def request_view(row,employee,user,personal=False):
    result={key:deepcopy(row.get(key)) for key in ('scheme_id','scheme_title','cover_type','cover_level','status','created_at','reviewed_at','review_reason')}
    result.update(id=str(row.get('id') or row['_id']),employee_id=employee_key(employee),employee_name=employee.get('full_name'))
    if user.get('role') in HR or (personal and employee_key(employee)==user.get('employee_id')):
        result['scheme_snapshot']=deepcopy(row.get('scheme_snapshot'))
        result.update(dependants=[{k:v for k,v in item.items() if k!='document_id'} for item in row.get('dependants',[])],beneficiaries=deepcopy(row.get('beneficiaries',[])),reason=row.get('reason'))
    if user.get('role') not in HR and not personal: result.pop('review_reason',None)
    if normalized(employee.get('lifecycle_state') or employee.get('status')) in {'exited','terminated','deactivated'}: result['coverage_notice']='Employee has exited; insurer removal must be confirmed by HR. This is a historical record, not proof of current coverage.'
    return result

async def decide(db,user,reference,body):
    privileged(user,write=True)
    if not isinstance(body,dict) or set(body)-{'decision','reason'} or body.get('decision') not in ('Approve','Reject'): fail('Invalid membership decision')
    row=await find_linked_record(db.benefit_requests,reference,user)
    employee=await find_employee(db,row.get('employee_id'),tenant_of(user))
    if not employee: fail('Employee link needs reconciliation',409)
    if row.get('submitted_by')==user['id'] or employee_key(employee)==user.get('employee_id'): fail('You cannot approve your own membership request',403)
    if row.get('status')!='Pending_HR': fail('Membership is not awaiting HR review',409)
    reason=text(body.get('reason'),'HR decision reason')
    if body['decision']=='Approve':
        policy=await scheme(db,user,row['scheme_id'])
        if not eligible(policy,employee): fail('Scheme or employee eligibility changed; reconcile before approval',409)
        for item in row.get('dependants',[]): await evidence(db,user,employee,item['document_id'])
        if row.get('supporting_document_id'): await evidence(db,user,employee,row['supporting_document_id'])
    update={'status':'Approved' if body['decision']=='Approve' else 'Rejected','review_reason':reason,'reviewed_at':now(),'reviewed_by':user['id']}
    await audit(db,user,'benefits.membership.decided',row['id'],before=row['status'],after=update['status'])
    # Prior approved records remain immutable history. The new approval explicitly references its predecessor.
    await db.benefit_requests.update_one({'_id':row['_id']},{'$set':update}); row.update(update)
    await notify(db,row,'decided')
    return request_view(row,employee,user)

async def overview(db,user):
    employee=await self_employee(db,user)
    user={**user,'employee_id':employee_key(employee)}
    schemes=await db.benefit_schemes.find(tenant_query(tenant_of(user))).to_list(None)
    rows=await memberships(db,user,employee)
    superseded={row.get('supersedes_id') for row in rows if row.get('status')=='Approved'}
    views=[]
    for row in rows:
        view=request_view(row,employee,user,personal=True)
        if row['id'] in superseded: view['status']='Superseded (historical)'
        view['coverage_notice']='HR approval is recorded locally; insurer confirmation and effective cover must be verified with HR.'
        views.append(view)
    return {'schemes':[scheme_view(row) for row in schemes if eligible(row,employee)],'memberships':views,
        'payroll_notice':'Payslips and P9s use the private Document Centre and existing HR sharing restrictions. No payroll feed or approved payroll balance is available here.',
        'pension_notice':'The Handbook describes an optional Britam Tier II pension plan. Contact HR for verified terms and enrolment; no contribution or membership is assumed.'}

async def premium(db,user,reference,body):
    privileged(user,finance=True,write=True)
    row=await scheme(db,user,reference)
    if not isinstance(body,dict) or set(body)-{'month','amount_kes','approval_reference'}: fail('Unknown premium fields')
    month=body.get('month'); day(str(month)+'-01')
    amount=body.get('amount_kes')
    if type(amount) not in (int,float) or not math.isfinite(amount) or amount<0: fail('Premium must be an approved non-negative amount')
    approved=text(body.get('approval_reference'),'premium approval reference')
    key=hashlib.sha256(f"{tenant_of(user)}:{row['id']}:{month}".encode()).hexdigest()
    await audit(db,user,'benefits.premium.recorded',key,scheme_id=row['id'],month=month)  # No premium amounts in HR-readable audit metadata.
    previous=await db.benefit_premiums.find_one({'_id':key})
    history=[*(previous or {}).get('history',[]),{key:deepcopy(value) for key,value in (previous or {}).items() if key not in {'_id','history'}}] if previous else []
    await db.benefit_premiums.update_one({'_id':key},{'$set':{'history':history,'tenant_id':tenant_of(user),'scheme_id':row['id'],'month':month,'amount_kes':amount,'approval_reference':approved,'recorded_by':user['id'],'recorded_at':now()}},upsert=True)
    return {'scheme_id':row['id'],'month':month,'amount_kes':amount}
