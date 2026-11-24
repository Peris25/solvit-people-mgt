"""Read-only, caller-scoped action queue shared by task lists and dashboard counts."""
import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import quote
from fastapi import HTTPException
from bson import ObjectId
from utils.employee_integrity import tenant_query, tenant_of, user_employee_aliases, resolve_user_employee, employee_key
from utils.employee_access import personal_grant
from utils.task_activity import current,current_checklist,ACTIVE_SINCE

logger=logging.getLogger(__name__)
OPEN=['Pending','In_Progress','Open']


def identifier(row): return str(row.get('id') or row.get('_id'))
def route(path,key,reference): return path+'?'+key+'='+quote(str(reference),safe='')
def grant(user,module):
    try: personal_grant(user,module);return True
    except HTTPException as error:
        if error.status_code==403:return False
        raise


async def queue(db,user):
    employee=await resolve_user_employee(db,user)
    refs=list(dict.fromkeys([str(value) for value in user_employee_aliases(user) if value and value!='__unlinked_employee__']))
    if employee: refs=list(dict.fromkeys([*refs,employee_key(employee),str(employee['_id'])]))
    if employee:user={**user,'employee_id':employee_key(employee),'employee_reference_ids':refs}
    actor_refs=[str(user['id']),*refs]
    stored_actor_refs=[*actor_refs,*[ObjectId(value) for value in actor_refs if ObjectId.is_valid(value)]]
    role=user.get('role');tenant=tenant_query(tenant_of(user))
    if not isinstance(role,str) or not role:raise HTTPException(403,'An active account role is required')
    hr=role in {'hr_admin','hr_manager','general_manager'}
    def scoped(extra): return {'$and':[tenant,extra]}
    def item(kind,row,title,path,due=None,**extra):
        return {'id':kind+':'+identifier(row),'reference':identifier(row),'kind':kind,'title':title,
                'status':row.get('status'),'due_date':due or row.get('due_date') or row.get('due_on'), 'path':path,**extra}
    async def permitted(function,*args,**kwargs):
        try: await function(*args,**kwargs);return True
        except HTTPException as error:
            if error.status_code in {403,404}: return False
            raise

    async def assigned_tasks():
        from utils.task_access import authorize_task
        candidates=await db.tasks.find(scoped({'status':{'$in':OPEN},'$or':[
            {'assigned_to':{'$in':stored_actor_refs}},{'assigned_to_user_id':user['id']},
            {'assigned_role':role,'assigned_to':{'$in':[None,'']},'assigned_to_user_id':{'$in':[None,'']}}]})).to_list(None)
        result=[]
        for row in candidates:
            if not current(row):continue
            if row.get('assigned_to') and str(row['assigned_to']) not in actor_refs: continue
            if row.get('assigned_to_user_id') and str(row['assigned_to_user_id'])!=str(user['id']):continue
            check={**row}
            if check.get('assigned_to'):check['assigned_to']=str(check['assigned_to'])
            if row.get('assigned_to_user_id'):check['assigned_to']=user['id']
            if not await permitted(authorize_task,db,user,check):continue
            if str(row.get('task_type') or '').startswith(('onboarding','probation_review_','check_in','checkin')):
                from utils.employee_integrity import find_employee
                subject=await find_employee(db,row.get('employee_id') or row.get('entity_id'),tenant_of(user))
                if not subject or not current_checklist(row,subject):continue
            checklist=row.get('task_type')=='exit_workflow'
            can_complete=not checklist and await permitted(authorize_task,db,user,check,write=True)
            path='/onboarding' if checklist else None
            result.append(item('assigned',row,row.get('title') or str(row.get('task_type') or 'Assigned task').replace('_',' '),path,
                               can_complete=can_complete,description=str(row.get('description') or row.get('notes') or '')[:1500]))
        return result

    async def forms():
        from utils.form_access import authorize_signature
        result=[]
        for row in await db.form_submissions.find(scoped({'status':'InProgress','next_required_role':{'$in':[role,'employee']}})).to_list(None):
            if not current(row):continue
            if row.get('form_id')=='form-06':continue
            if await permitted(authorize_signature,db,user,row.get('next_required_role'),row.get('subject_employee_id'),row.get('started_by')):
                result.append(item('form',row,row.get('form_title') or row.get('form_id') or 'Form sign-off',route('/forms','submission',identifier(row))))
        return result

    async def performance():
        if not grant(user,'M05'):return []
        from utils.employee_access import scoped_employee_query
        from utils import performance_workflows as flow
        from utils.probation_reviews import applies,prepare
        scope=await scoped_employee_query(db,user,'M05')
        reports=await db.employees.find(scoped({'line_manager_id':{'$in':refs}}),{'id':1,'_id':1}).to_list(None) if refs else []
        report_refs=[value for record in reports for value in [str(record.get('id') or record['_id']),str(record['_id'])]]
        relevant=[{'employee_id':{'$in':refs},'status':{'$in':['Draft','Self_Draft','Completed','HR_Reviewed']}}]
        if report_refs:relevant.append({'employee_id':{'$in':report_refs},'status':{'$in':['Draft','Self_Draft','Self_Submitted','Manager_Submitted','HR_Reviewed']}})
        if hr:relevant.append({'status':{'$in':['Manager_Submitted','HR_Reviewed']}})
        rows=await db.performance_reviews.find({'$and':[scope,{'$or':relevant}]}).to_list(None)
        result=[]
        for row in rows:
            if not current(row,row.get('starts_on'),row.get('released_at'),
                           (row.get('self_assessment') or {}).get('submitted_at'),
                           (row.get('manager_assessment') or {}).get('submitted_at')):continue
            try: subject=await flow.employee_access(db,user,row.get('employee_id'))
            except HTTPException as error:
                if error.status_code in {403,404}:continue
                raise
            if applies(row):row=await prepare(db,row,subject)
            view=flow.projection(row,user,subject);status=row.get('status')
            title=None;due=None
            if view.get('can_self_assess'):title='Complete your self-review';due=row.get('self_due_on')
            elif view.get('can_probation_acknowledge') or (row.get('workflow_version')==3 and user.get('employee_id') in {employee_key(subject),str(subject['_id'])} and flow.released(row) and not row.get('acknowledged_at')):
                title='Acknowledge your released review';due=row.get('ack_due_on')
            elif view.get('can_manage'):
                if view.get('manager_led_probation') and status in {'Draft','Self_Draft','Self_Submitted'} and not row.get('manager_assessment'):
                    title='Complete probation manager assessment';due=row.get('manager_due_on')
                elif status=='Self_Submitted':title='Complete manager assessment';due=row.get('manager_due_on')
                elif (status=='HR_Reviewed' or (status=='Manager_Submitted' and row.get('workflow_version')!=3)) and not row.get('review_meeting'):title='Propose review meeting';due=row.get('review_due_on')
                elif row.get('review_meeting') and not row.get('meeting_completed_at') and row.get('workflow_version') in {1,3}:
                    title='Record probation meeting completion' if view.get('manager_led_probation') else 'Attend review meeting';due=row['review_meeting'].get('scheduled_at')
            if not title and view.get('can_hr_review'):
                if status=='Manager_Submitted':title='Review assessment / arrange meeting';due=row.get('review_due_on')
                elif status=='HR_Reviewed':title='Complete meeting / release review';due=row.get('review_due_on')
            if title:result.append(item('review',row,title,route('/performance','review',view['id']),due,subject=subject.get('full_name')))
        return result

    async def peer_and_surveys():
        if not employee or not grant(user,'M05'):return []
        from utils.performance_v3_peers import listing
        from utils.performance_v3_alignment import windows
        peers,surveys=await asyncio.gather(listing(db,user),windows(db,user))
        result=[]
        from utils import performance_v3 as process
        for row in peers:
            if row.get('status')!='Assigned' or not row.get('can_submit'):continue
            raw=await db.performance_peer_tasks.find_one(process.scoped(user,{'id':row['id']}))
            cycle=await process.cycle(db,user,row['cycle_id'])
            if current(raw or {},cycle.get('starts_on')):result.append(item('peer',row,'Complete confidential peer review',route('/performance','peer',row['id']),row.get('due_on'),subject=row.get('employee_name')))
        today=process.today().isoformat()
        for row in surveys:
            if row.get('submitted') or not row.get('starts_on','z')<=today<=row.get('due_on',''):continue
            cycle=await process.cycle(db,user,row['id'])
            if cycle.get('status')=='Open' and current(cycle,cycle.get('starts_on')):result.append(item('alignment',row,'Complete Alignment Survey',route('/performance','alignment',row['id']),row.get('due_on')))
        return result

    async def checklists():
        from utils.lifecycle_workflows import task_access
        collection=getattr(db,'onboarding_tasks',None)
        if collection is None:return []
        result=[]
        for row in await collection.find(scoped({'entity_type':'employee','status':{'$in':OPEN},'assigned_role':{'$in':[role,'employee','line_manager']}})).to_list(None):
            # HR visibility does not make another party's checklist item their task.
            if row.get('assigned_role')=='employee' and str(row.get('entity_id')) not in refs:continue
            from utils.employee_integrity import find_employee,is_direct_report
            subject=await find_employee(db,row.get('entity_id'),tenant_of(user))
            if not subject or not current_checklist(row,subject):continue
            if subject and subject.get('onboarding_recorded_status')=='Completed':continue
            if row.get('assigned_role')=='line_manager':
                if not subject or not is_direct_report(subject,user):continue
            elif row.get('assigned_role') not in {role,'employee'}:continue
            if await permitted(task_access,db,user,row,write=True):result.append(item('onboarding',row,row.get('title') or 'Complete onboarding checklist item','/onboarding'))
        return result

    async def leave():
        from utils.leave_workflow import stage_for
        candidates={'status':{'$in':['Pending_Manager','Pending_HR']}}
        if not hr:candidates['line_manager_id']={'$in':refs}
        result=[]
        for row in await db.leave_requests.find(scoped(candidates)).to_list(None):
            if not current(row,row.get('manager_decided_at') if row.get('status')=='Pending_HR' else None):continue
            if await stage_for(db,user,row):result.append(item('leave',row,'Review leave request',route('/leave','request',identifier(row))+'&view=team',row.get('start_date')))
        return result

    async def learning():
        if not grant(user,'M08'):return []
        collection=getattr(db,'training_requests',None)
        if collection is None:return []
        choices=[{'employee_id':{'$in':refs},'status':'Approved'},{'line_manager_id':{'$in':refs},'status':'Pending_Manager_Approval'}]
        if hr:choices.append({'status':{'$in':['Pending_HR_Approval','Completion_Submitted']}})
        query={'$or':choices}
        from utils.learning_workflows import employee_access,projection
        result=[]
        for row in await collection.find(scoped(query)).to_list(None):
            if not current(row,row.get('manager_decided_at'),row.get('hr_decided_at'),
                           (row.get('completion_submission') or {}).get('submitted_at')):continue
            try:subject=await employee_access(db,user,row.get('employee_id'))
            except HTTPException as error:
                if error.status_code in {403,404}:continue
                raise
            view=await projection(db,user,row,subject)
            title='Review training request' if view['can_decide'] else 'Verify training completion' if view['can_verify_completion'] else 'Complete assigned training' if view['can_submit_completion'] else None
            if title:result.append(item('learning',row,title,route('/lnd','training',identifier(row)),row.get('due_on') or row.get('proposed_end_date'),subject=subject.get('full_name')))
        return result

    sources={'Assigned tasks':assigned_tasks,'Forms':forms,'Reviews':performance,'Peer reviews and surveys':peer_and_surveys,'Onboarding':checklists,'Leave approvals':leave,'Learning':learning}
    results=await asyncio.gather(*(asyncio.wait_for(source(),12) for source in sources.values()),return_exceptions=True)
    items=[];errors=[]
    for name,result in zip(sources,results):
        if isinstance(result,Exception):
            if isinstance(result,HTTPException) and result.status_code==403:continue
            logger.warning('Personal task source unavailable: %s (%s)',name,type(result).__name__)
            errors.append(name)
        else:items.extend(result)
    unique={row['id']:row for row in items}
    ordered=sorted(unique.values(),key=lambda row:(not bool(row.get('due_date')),str(row.get('due_date') or ''),row['title']))
    return {'items':ordered,'count':len(ordered) if not errors else None,'errors':errors,'active_since':ACTIVE_SINCE,'as_of':datetime.now(timezone.utc).isoformat()}
