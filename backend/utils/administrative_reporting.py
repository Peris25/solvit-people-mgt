"""Read-time audit federation and whitelisted operational reports; no migrations."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import heapq
import io
import math
import re
import uuid
from bson import ObjectId
from fastapi import HTTPException
from utils.access_matrix import get_module_access
from utils.employee_access import authorize_employee, reference_ids
from utils.employee_integrity import employee_key, is_direct_report, resolve_user_employee, tenant_of, tenant_query
from utils.staff_directory import employment_type, normalized
from utils.staff_views import restricted

HR={'hr_admin','hr_manager'}
KINDS={'solver_assessments':('M02','form_submissions','created_at'),'solvers':('M02','solvers','created_at'),'employees':('M01','employees','start_date'),'leave':('M18','leave_requests','start_date'),
       'leave_balances':('M18','leave_balances','updated_at'),'onboarding':('M04','onboarding_tasks','due_date'),
       'performance':('M05','performance_reviews','review_date'),'training':('M08','training_requests','proposed_start_date'),
       'benefits':('M10','benefit_requests','created_at'),
       'probation_dates':('M04','employees','probation_end_date'),'contract_dates':('M01','employees','contract_end_date')}
AUDIT_SOURCES=('audit_log','audit_logs','settings_audit','document_audit','email_delivery_audit','ai_actions_audit')
AUDIT_FIELDS={key:1 for key in ('_id','id','event','action','kind','entity','entity_id','entity_type','employee_id','solver_id','document_id','timestamp','created_at',
                              'actor_id','performed_by','by_user_id','changed_by','user_id','category','outcome','old_mode','new_mode')}
PREFIXES={'employee':'M01','profile':'M01','account':'Security','auth':'Security','security':'Security','login':'Security',
          'leave':'M18','onboarding':'M04','offboarding':'M04','lifecycle':'M04','performance':'M05','learning':'M08','training':'M08',
          'benefits':'M10','compensation':'M10','salary':'M10','pay_band':'M10','budget':'M12','settings':'Settings','report':'Reporting',
          'reporting':'Reporting','document':'M01','solver':'M02','recognition':'M11','policy':'M13','form':'M17','access':'Security'}
EAT=timezone(timedelta(hours=3))


def fail(message,status=422): raise HTTPException(status,message)
def scalar(value):
    if isinstance(value,str): return ''.join(c for c in value if ord(c)>=32 or c in '\t\n')[:2000]
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value): return value
    if isinstance(value,bool): return value
    return None

def stamp(value):
    try:
        parsed=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (AttributeError,TypeError,ValueError): return None

def bounds(date_from=None,date_to=None):
    def parse(value):
        if value is None or value=='': return None
        if not isinstance(value,str) or len(value)!=10: fail('Report dates must use YYYY-MM-DD')
        try: return date.fromisoformat(value)
        except ValueError: fail('Invalid report date')
    start,end=parse(date_from),parse(date_to)
    if start and end and start>end: fail('Report end precedes its start')
    return start,end

def in_period(value,start,end,until=None):
    parsed=stamp(value)
    finish=stamp(until) or parsed
    if not start and not end: return True
    if not parsed: return False
    return (not start or finish.astimezone(EAT).date()>=start) and (not end or parsed.astimezone(EAT).date()<=end)

def reference(value):
    if isinstance(value,ObjectId):return str(value)
    return value if isinstance(value,str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,200}',value) else None

def permission(user,module):
    entry=get_module_access(module,user.get('role'))
    return bool(entry and entry.get('level') in {'Read','Manage','Full'})

def report_allowed(user,kind):
    if kind not in KINDS: return False
    role=user.get('role'); module=KINDS[kind][0]
    allowed=(role in HR or role=='line_manager' and kind in {'employees','leave','onboarding','performance','training','probation_dates','contract_dates'} or
             role=='executive' and kind in {'employees','leave','performance'} or role=='finance' and kind in {'leave','benefits'})
    entry=get_module_access(module,role) or {}
    if kind=='solver_assessments':
        assessment_entry=get_module_access('M03',role) or {}
        if not assessment_entry or assessment_entry.get('scope') not in {None,'headcount_summary','aggregate'}:return False
        if role in HR and assessment_entry.get('level') not in {'Manage','Full'}:return False
    if kind in {'solvers','solver_assessments'}:
        return bool(role in HR.union({'executive'}) and permission(user,module) and entry.get('scope') in {None,'aggregate'})
    if role=='executive' and entry.get('scope') not in {None,'aggregate','envelope_only','own_team','own_reports','own_record'}:return False
    if role=='finance' and kind=='benefits' and entry.get('scope') not in {None,'no_perf_no_disciplinary'}:return False
    return bool(allowed and permission(user,module) and (kind!='benefits' or permission(user,'M01')))

def audit_allowed(user):
    return user.get('role')=='it_admin' or user.get('role') in HR and permission(user,'M01') and get_module_access('M01',user['role']).get('scope') is None

def catalogue(user):
    reports=[]
    for kind,(module,_,basis) in KINDS.items():
        if not report_allowed(user,kind):continue
        entry=get_module_access(module,user.get('role')) or {}
        summary=user.get('role')=='executive'
        scope='aggregate' if summary else 'direct_reports' if user.get('role')=='line_manager' else 'authorized_records'
        if entry.get('scope')=='own_record':scope='own_record'
        reports.append({'id':kind,'module':module,'date_basis':basis,'scope':scope,'summary_only':summary})
    if reports:reports.append({'id':'management','module':'Reporting','date_basis':'per_module_saved_date','summary_only':True})
    return {'reports':reports,'can_audit':audit_allowed(user)}

async def access_audit(db,user,event,**metadata):
    try:
        await db.audit_logs.insert_one({'id':str(uuid.uuid4()),'tenant_id':tenant_of(user),'event':event,'actor_id':user['id'],
                                      'timestamp':datetime.now(timezone.utc).isoformat(),'metadata':metadata})
    except Exception: fail('Report access could not be audited; retry after an administrator reviews logging',503)


def opaque(value,prefix): return prefix+hashlib.sha256(str(value).encode()).hexdigest()[:24]
def audit_module(source,row):
    if source=='settings_audit': return 'Settings'
    if source=='document_audit': return 'M02' if row.get('solver_id') else 'M01'
    if source=='email_delivery_audit': return 'Email'
    if source=='ai_actions_audit': return 'M16'
    event=row.get('event') or row.get('action') or ''
    if isinstance(event,str):
        prefix=re.split(r'[.:]',event.lower())[0]
        if prefix in PREFIXES: return PREFIXES[prefix]
    entity=row.get('entity_type') or row.get('entity')
    if isinstance(entity,str) and entity.lower().startswith('employee'): return 'M01'
    return 'Unknown'

def audit_visible(user,module):
    if user.get('role')=='it_admin': return True
    if module in {'Security','Unknown'}: return False
    if module in {'Settings','Email'}: return user.get('role')=='hr_admin'
    if module=='Reporting': return audit_allowed(user)
    entry=get_module_access(module,user.get('role'))
    return bool(entry and entry.get('level') in {'Read','Manage','Full'} and entry.get('scope') is None)

async def audit_projection(db,user,source,row,actors):
    module=audit_module(source,row)
    if not audit_visible(user,module): return None
    actor=row.get('actor_id') or row.get('performed_by') or row.get('by_user_id') or row.get('changed_by') or row.get('user_id')
    actor_key=opaque(str(tenant_of(user))+':'+str(actor),'actor:') if actor else 'actor:unknown'
    if actor_key not in actors:
        actor_name='Unknown / historical actor'
        if isinstance(actor,(str,ObjectId)):
            clauses=[{'id':str(actor)},{'_id':actor}]
            if ObjectId.is_valid(str(actor)): clauses.append({'_id':ObjectId(str(actor))})
            matches=await db.users.find({'$and':[tenant_query(tenant_of(user)),{'$or':clauses}]},{'_id':1,'id':1,'full_name':1}).to_list(2)
            if len(matches)==1:
                name=matches[0].get('full_name')
                if isinstance(name,str) and '@' not in name: actor_name=scalar(name)
                else: actor_name='Account '+str(matches[0]['_id'])[-8:]
        actors[actor_key]={'id':actor_key,'name':actor_name}
    event=row.get('event') or row.get('action') or row.get('kind')
    if not isinstance(event,str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.:-]{0,119}',event): event='legacy_event'
    timestamp=stamp(row.get('timestamp') or row.get('created_at'))
    target=row.get('entity_id') or row.get('entity') or row.get('employee_id') or row.get('document_id')
    result={'id':source+':'+str(row.get('_id') or row.get('id')),'source':source,'event':event,'module':module,
            'timestamp':timestamp.isoformat() if timestamp else None,'actor_id':actor_key,'actor_name':actors[actor_key]['name'],
            'target_reference':opaque(str(tenant_of(user))+':'+str(target),'target:') if target else None,'details_redacted':True}
    if row.get('outcome') in ('executed','cancelled','failed'):result['outcome']=row['outcome']
    for key in ('old_mode','new_mode'):
        if row.get(key) in ('testing','production'):result[key]=row[key]
    return result

async def audit_feed(db,user,*,date_from=None,date_to=None,event_type=None,module=None,actor=None,offset=0,limit=100,sources=None):
    if not audit_allowed(user): fail('Administrative audit access is required',403)
    if not 1<=limit<=500 or not 0<=offset<=10000: fail('Invalid audit pagination')
    start,end=bounds(date_from,date_to)
    if sources is not None and not set(sources)<=set(AUDIT_SOURCES): fail('Invalid audit source')
    actors={}; chosen=[]; total=0; missing_dates=0; events=set(); modules=set(); actor_options={}
    for source in sources or AUDIT_SOURCES:
        async for raw in getattr(db,source).find(tenant_query(tenant_of(user)),AUDIT_FIELDS):
            row=await audit_projection(db,user,source,raw,actors)
            if not row: continue
            if row['timestamp'] is None: missing_dates+=1
            if not in_period(row['timestamp'],start,end): continue
            if module and row['module']!=module or event_type and row['event']!=event_type or actor and row['actor_id']!=actor: continue
            total+=1;events.add(row['event']);modules.add(row['module']);actor_options[row['actor_id']]=actors[row['actor_id']]
            key=(row['timestamp'] or '',row['id'])
            if len(chosen)<offset+limit: heapq.heappush(chosen,(key,row))
            elif key>chosen[0][0]: heapq.heapreplace(chosen,(key,row))
    ordered=[row for _,row in sorted(chosen,key=lambda item:item[0],reverse=True)][offset:offset+limit]
    return {'items':ordered,'total':total,'offset':offset,'limit':limit,'missing_dates':missing_dates,
            'events':sorted(events),'modules':sorted(modules),'actors':sorted(actor_options.values(),key=lambda row:row['name'] or ''),
            'notice':'Read-time view of existing source records. Payloads, secrets and sensitive before/after values are redacted. Undated history is excluded when date filters are set.'}

async def report_data(db,user,kind,*,date_from=None,date_to=None,department=None,status=None,offset=0,limit=100,export=False):
    if kind=='management':return await management_report(db,user,date_from=date_from,date_to=date_to,department=department,status=status,offset=offset,limit=limit,export=export)
    if not report_allowed(user,kind): fail('This report is not authorized',403)
    if kind=='solver_assessments':return await solver_assessment_report(db,user,date_from,date_to,department,status,offset,limit,export)
    if kind=='solvers':return await solver_report(db,user,date_from,date_to,department,status,offset,limit,export)
    if not 1<=limit<=500 or not 0<=offset<=10000: fail('Invalid report pagination')
    start,end=bounds(date_from,date_to); module,collection,basis=KINDS[kind]
    if department is not None and (not isinstance(department,str) or len(department)>200): fail('Invalid department filter')
    if status is not None and (not isinstance(status,str) or len(status)>100): fail('Invalid status filter')
    role=user.get('role'); summary=role=='executive'
    entry=get_module_access(module,role)
    team_scope=(role in {'line_manager','finance'} and kind!='benefits') or (summary and entry.get('scope') in {'own_team','own_reports'})
    own_scope=summary and entry.get('scope')=='own_record'
    if team_scope or own_scope:
        own=await resolve_user_employee(db,user)
        if not own: fail('A verified manager employee link is required',409)
        user={**user,'employee_id':employee_key(own),'employee_reference_ids':reference_ids(own)+[own['_id']]}
    employees=await db.employees.find(tenant_query(tenant_of(user))).to_list(None)
    index=defaultdict(list)
    for employee in employees:
        for ref in set(reference_ids(employee)):
            if reference(ref):index[ref].append(employee)
    def resolve(ref):
        matches=index.get(reference(ref),[])
        return matches[0] if len(matches)==1 else None
    visible={}; issues=0; departments=set()
    for employee in employees:
        if restricted(employee.get('board_only')): continue
        if department and normalized(employee.get('department'))!=normalized(department): continue
        if team_scope and not is_direct_report(employee,user): continue
        if own_scope and employee_key(employee)!=user.get('employee_id'):continue
        if employee.get('id') not in (None,'') and reference(employee.get('id')) is None:
            issues+=1;continue
        if resolve(employee_key(employee)) is not employee or resolve(employee.get('_id')) is not employee:
            issues+=1;continue
        if not summary and not (role=='finance' and kind=='benefits'):
            try: await authorize_employee(db,user,str(employee['_id']),module)
            except HTTPException as error:
                if error.status_code==403:continue
                raise
        visible[str(employee['_id'])]=employee
        if isinstance(employee.get('department'),str):departments.add(employee['department'])
    data=employees if collection=='employees' else await getattr(db,collection).find(tenant_query(tenant_of(user))).to_list(None)
    rows=[];missing_dates=0
    for record in data:
        employee=record if collection=='employees' else resolve(record.get('entity_id') if kind=='onboarding' else record.get('employee_id'))
        if not employee:
            issues+=1;continue
        if str(employee['_id']) not in visible: continue
        value=record.get(basis) or (record.get('created_at') if collection!='employees' else None)
        if not stamp(value):
            missing_dates+=1
            if kind in {'probation_dates','contract_dates'}:continue
        if not in_period(value,start,end,record.get('end_date') if kind=='leave' else None):continue
        base={'employee_id':employee_key(employee),'employee_name':scalar(employee.get('full_name')),'department':scalar(employee.get('department'))}
        if collection=='employees':
            manager=resolve(employee.get('line_manager_id'))
            base.update(role_title=scalar(employee.get('role_title')),work_email=scalar(employee.get('work_email')),employment_type=employment_type(employee.get('employment_type')),
                status=scalar(employee.get('lifecycle_state') or employee.get('status') or employee.get('employment_status')),
                start_date=scalar(employee.get('start_date')),probation_end_date=scalar(employee.get('probation_end_date')),contract_end_date=scalar(employee.get('contract_end_date')),
                last_working_day=scalar(employee.get('last_working_day') or employee.get('exit_date')),line_manager_name=scalar(manager.get('full_name')) if manager and not restricted(manager.get('board_only')) else 'Manager not found or restricted')
            if role not in HR and normalized(base['status']) in {'pip','realignment'}:base['status']='Active'
        elif kind=='leave':
            if role=='finance' and record.get('status')!='Approved':continue
            base.update({key:scalar(record.get(key)) for key in ('start_date','end_date','working_days','status')})
            if role in HR:base['leave_type']=scalar(record.get('leave_type'))
        elif kind=='leave_balances':
            def remaining(name,*aliases):
                value=record.get(name)
                if isinstance(value,dict) and scalar(value.get('remaining')) is not None:return scalar(value['remaining'])
                return next((scalar(record.get(key)) for key in aliases if scalar(record.get(key)) is not None),None)
            base.update(year=scalar(record.get('year')),annual_remaining=remaining('Annual','annual_remaining_days','annual_days_remaining'),sick_remaining=remaining('Sick','sick_remaining_days','sick_days_remaining'),source='Recorded snapshot',status='Recorded')
        elif kind=='onboarding':base.update({key:scalar(record.get(key)) for key in ('task_key','status','assigned_role','due_date','completed_at')})
        elif kind=='performance':
            from utils.performance_workflows import projection
            safe=projection(record,user,employee)
            base.update({key:scalar(safe.get(key)) for key in ('cycle_type','cycle_year','status','overall_score','rating')})
        elif kind=='training':
            base.update(training_name=scalar(record.get('training_name') or record.get('title') or record.get('name')),
                        **{key:scalar(record.get(key)) for key in ('status','proposed_start_date','proposed_end_date','due_on','completed_on','duration_days')})
        else:base.update({key:scalar(record.get(key)) for key in ('scheme_title','cover_level','status','created_at','reviewed_at')})
        if status and normalized(base.get('status'))!=normalized(status):continue
        base['record_id']=reference(record.get('id')) or reference(record.get('_id'))
        rows.append(base)
    if summary:
        counts=Counter((row['department'] or 'Not recorded',str(row.get('status') or 'Not recorded')) for row in rows)
        rows=[{'department':department,'status':state,'count':count} for (department,state),count in sorted(counts.items())]
    else:rows.sort(key=lambda row:(str(row.get('employee_name') or ''),row.get('record_id') or ''))
    if export and len(rows)>10000:fail('Export exceeds 10000 authorized rows; narrow the date or department filters',413)
    return {'report':kind,'summary_only':summary,'items':rows if export else rows[offset:offset+limit],'total':len(rows),'offset':offset,'limit':limit,
        'departments':sorted(departments),'unresolved_records':issues if role in HR else None,'missing_dates':missing_dates,'date_basis':basis,'scope':'direct_reports' if team_scope else 'own_record' if own_scope else 'aggregate' if summary else 'authorized_records',
        'notice':'Current saved records only; not historical point-in-time headcount or an attrition calculation. Undated rows are excluded by date filters. Balances are recorded snapshots, never recalculated. Restricted or ambiguous employee links are excluded.'}


def export_value(value):
    value=scalar(value)
    if isinstance(value,str) and value.lstrip(' \t\r\n\ufeff').startswith(('=','+','-','@')):return "'"+value
    return '' if value is None else value

def csv_bytes(rows):
    output=io.StringIO(newline='');headers=list(dict.fromkeys(key for row in rows for key in row)) or ['info']
    writer=csv.DictWriter(output,fieldnames=headers);writer.writeheader()
    for row in rows:writer.writerow({key:export_value(row.get(key)) for key in headers})
    return ('\ufeff'+output.getvalue()).encode('utf-8')

def xlsx_bytes(rows):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    book=Workbook(write_only=True);sheet=book.create_sheet('Report')
    headers=list(dict.fromkeys(key for row in rows for key in row)) or ['info'];sheet.append(headers)
    for row in rows:
        cells=[]
        for key in headers:
            value=export_value(row.get(key));cell=WriteOnlyCell(sheet,value=value)
            if isinstance(value,str):cell.data_type='s'
            cells.append(cell)
        sheet.append(cells)
    output=io.BytesIO();book.save(output);return output.getvalue()


class SafeCSVWriter:
    def __init__(self,stream): self.writer=csv.writer(stream)
    def writerow(self,values): return self.writer.writerow([export_value(value) for value in values])
    def writerows(self,rows):
        for row in rows:self.writerow(row)


async def management_report(db,user,**filters):
    allowed=[kind for kind in KINDS if report_allowed(user,kind)]
    if not allowed:fail('Management reporting is not authorized',403)
    offset=filters.get('offset',0);limit=filters.get('limit',100)
    if not 1<=limit<=500 or not 0<=offset<=10000:fail('Invalid report pagination')
    rows=[];missing=0;issues=0;departments=set()
    for kind in allowed:
        data=await report_data(db,user,kind,date_from=filters.get('date_from'),date_to=filters.get('date_to'),department=filters.get('department'),status=filters.get('status'),export=True)
        counts=Counter()
        for row in data['items']:
            counts[(row.get('department') or 'Not recorded',row.get('status') or 'Not recorded')]+=row['count'] if data['summary_only'] else 1
        rows.extend({'report_kind':kind,'date_basis':data['date_basis'],'department':dept,'status':state,'count':count} for (dept,state),count in sorted(counts.items()))
        departments.update(data['departments']);missing+=data['missing_dates'];issues+=data['unresolved_records'] or 0
    return {'report':'management','summary_only':True,'scope':'authorized_module_summaries','items':rows if filters.get('export') else rows[offset:offset+limit],
            'total':len(rows),'offset':offset,'limit':limit,'departments':sorted(departments),'missing_dates':missing,
            'unresolved_records':issues if user.get('role') in HR else None,'date_basis':'per module saved date',
            'notice':'Meeting summary counts authorized saved records by module, department and status. Each module uses its stated date basis; these are not historical headcount, attrition rates or payment approvals.'}


async def solver_report(db,user,date_from,date_to,region,status,offset,limit,export):
    from utils.solver_access import find_solver, solver_key, solver_access
    from utils.solver_workflows import view
    await solver_access(db,user)
    if not 1<=limit<=500 or not 0<=offset<=10000:fail('Invalid report pagination')
    start,end=bounds(date_from,date_to)
    rows=[];missing=0
    for record in await db.solvers.find(tenant_query(tenant_of(user))).to_list(None):
        await find_solver(db,solver_key(record),user)
        row=view(record)
        if region and normalized(region)!=normalized(row.get('region')):continue
        if status and normalized(status)!=normalized(row.get('lifecycle_state')):continue
        if not stamp(row.get('created_at')):missing+=1
        if not in_period(row.get('created_at'),start,end):continue
        rows.append({'solver_id':solver_key(record),'solver_name':scalar(row.get('full_name')),
                     'department':scalar(row.get('region')),'status':scalar(row.get('lifecycle_state')),
                     'region':scalar(row.get('region')),'created_at':scalar(row.get('created_at'))})
    summary=user.get('role')=='executive'
    regions=sorted({r['region'] for r in rows if r['region']})
    if summary:
        counts=Counter((row['region'] or 'Not recorded',row['status']) for row in rows)
        rows=[{'department':region,'region':region,'status':state,'count':count} for (region,state),count in sorted(counts.items())]
    if export and len(rows)>10000:fail('Narrow the report filters',413)
    return {'report':'solvers','summary_only':summary,'scope':'aggregate' if summary else 'authorized_records',
            'items':rows if export else rows[offset:offset+limit],'total':len(rows),'offset':offset,'limit':limit,
            'departments':regions,'missing_dates':missing,'unresolved_records':0,'date_basis':'created_at',
            'notice':'Saved Solver records only. Department filter groups by region. Contacts, payment details, private assessments and documents are excluded.'}


async def solver_assessment_report(db,user,date_from,date_to,region,status,offset,limit,export):
    from utils.solver_assessments import KIND, hr
    from utils.solver_access import find_solver
    from utils.solver_workflows import view
    if user.get('role') in HR:hr(user)
    if not 1<=limit<=500 or not 0<=offset<=10000:fail('Invalid report pagination')
    start,end=bounds(date_from,date_to);rows=[];missing=0;issues=0
    for row in await db.form_submissions.find({'$and':[tenant_query(tenant_of(user)),{'workflow_kind':KIND,'publication_state':'Ready'}]}).to_list(None):
        try:record=await find_solver(db,row.get('subject_solver_id'),user)
        except HTTPException as error:
            if error.status_code==404:issues+=1;continue
            raise
        saved=view(record);area=scalar(saved.get('region'))
        if region and normalized(region)!=normalized(area):continue
        if status and normalized(status)!=normalized(row.get('status')):continue
        if not stamp(row.get('created_at')):missing+=1
        if not in_period(row.get('created_at'),start,end):continue
        item={'solver_id':reference(row.get('subject_solver_id')),'solver_name':scalar(record.get('full_name')),
              'department':area,'region':area,'status':scalar(row.get('status')),'assessment_title':scalar(row.get('title')),
              'configuration_version':scalar(row.get('configuration_version')),'created_at':scalar(row.get('created_at')),
              'submitted_at':scalar(row.get('submitted_at')),'released_at':scalar(row.get('released_at'))}
        if row.get('status')=='Released':item.update(score=scalar(row.get('score')),outcome=scalar(row.get('outcome')))
        rows.append(item)
    regions=sorted({row['region'] for row in rows if row['region']});summary=user.get('role')=='executive'
    if summary:
        counts=Counter((row['region'] or 'Not recorded',row['status'] or 'Not recorded') for row in rows)
        rows=[{'department':region,'region':region,'status':state,'count':count} for (region,state),count in sorted(counts.items())]
    if export and len(rows)>10000:fail('Narrow the report filters',413)
    return {'report':'solver_assessments','summary_only':summary,'scope':'aggregate' if summary else 'authorized_records',
            'items':rows if export else rows[offset:offset+limit],'total':len(rows),'offset':offset,'limit':limit,
            'departments':regions,'missing_dates':missing,'unresolved_records':issues if not summary else None,'date_basis':'created_at',
            'notice':'Current assessment workflow status only. Region uses the department filter. No private answers, rubrics, keys, notes or document paths are exported. Scores appear only for released results.'}
