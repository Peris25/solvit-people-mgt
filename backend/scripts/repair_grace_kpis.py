"""Explicit Grace-only KPI correction. Preview by default; never runs at startup.

Run in the backend environment with its existing MONGO_URL and DB_NAME.
--apply requires the exact preview fingerprint. No notifications are created.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bson import json_util
from fastapi import HTTPException
from database import init_db, close_db
from utils import performance_v3 as process, role_kpi_library as library
from utils.employee_integrity import integrity_write, tenant_query, employee_key
from utils.staff_views import token

WEIGHTS = {'scheduled':15, 'schedule_tat':10, 'pending':15, 'approval_tat':15,
           'throughput':10, 'mismatch':5, 'invoicing':10, 'collections':10, 'payments':10}


def require(value, message):
    if not value: raise HTTPException(409,message)


def identify(goal):
    name = token(goal.get('objective'))
    wording = name + token(goal.get('metric'))
    matches = []
    if name in {'scheduledrate','schedulingrate'}: matches.append('scheduled')
    if 'tat' in name and ('initiat' in name or 'initiat' in wording) and 'scheduled' in name: matches.append('schedule_tat')
    if 'pendingscheduling' in name: matches.append('pending')
    if 'totaltat' in name and 'approval' in name: matches.append('approval_tat')
    if 'endtoendthroughput' in name: matches.append('throughput')
    if 'mismatch' in wording and ('record' in wording or 'financial' in wording): matches.append('mismatch')
    if 'invoic' in name and ('tims' in wording or 'shared' in wording): matches.append('invoicing')
    if ('billing' in wording and 'collect' in wording) or name == 'accountsreceivable': matches.append('collections')
    if 'solver' in wording and ('salar' in wording or 'statutory' in wording): matches.append('payments')
    require(len(matches) == 1, 'A KPI cannot be matched uniquely to the nine approved objectives; no changes applied.')
    return matches[0]


def corrected_goals(goals):
    require(isinstance(goals,list) and len(goals)==9, 'Expected exactly nine amended KPIs; no changes applied.')
    result=deepcopy(goals); seen=set()
    for goal in result:
        key=identify(goal)
        require(key not in seen, 'Duplicate approved objective; no changes applied.')
        seen.add(key); goal.update(weight=WEIGHTS[key],group='')
    require(seen==set(WEIGHTS), 'Incomplete approved objectives; no changes applied.')
    return result


def corrected_values(values):
    require(values.get('role_id')=='finance-operations-manager' and values.get('scope')=='Annual', 'The stored assignment is not the expected Annual Finance role.')
    result=library.combined_finance_weights(values)
    result['goals']=corrected_goals(result['goals'])
    require(not library.issues(result), 'The amended KPI assignment has other validation issues; no changes applied.')
    return result


async def prepare(db):
    people=await db.employees.find({'$and':[tenant_query('solvit'),{'work_email':{'$regex':'^gmungai@solvit\\.co\\.ke$','$options':'i'}}]}, {'_id':1,'id':1,'tenant_id':1,'full_name':1,'work_email':1,'lifecycle_state':1,'status':1,'employment_type':1,'board_only':1}).to_list(3)
    require(len(people)==1 and token(people[0].get('full_name'))=='gracewanguimungai', 'Grace identity could not be verified uniquely.')
    employee=people[0]
    require(process.enabled(employee) and process.fte(employee), 'Grace is not an active eligible employee.')
    assigned=await process.assignment(db,employee)
    require(assigned and assigned.get('version'), 'Grace has no versioned employee KPI assignment.')
    changes=[]
    values=corrected_values(assigned['values'])
    if values!=assigned['values']: changes.append(('system_settings',assigned,{'values':values}))
    reviews=await db.performance_reviews.find(process.scoped(employee,{'employee_id':{'$in':process.reference_ids(employee)},'workflow_version':3,'cycle_year':2026,'cycle_type':'Year_End','status':{'$nin':['Completed','Archived','Cancelled']}})).to_list(None)
    for review in reviews:
        require(review.get('status')=='Self_Draft' and not review.get('self_assessment'), 'Grace has an assessment in progress or submitted. HR must review it before any correction; no changes applied.')
        goals=corrected_goals(review['section_a_kpis'])
        if goals!=review['section_a_kpis'] or review.get('group_weights'):
            changes.append(('performance_reviews',review,{'section_a_kpis':goals,'group_weights':{}}))
    return employee,assigned,changes


def fingerprint(plan):
    return hashlib.sha256(json_util.dumps(plan,sort_keys=True).encode()).hexdigest()


async def apply(db, expected):
    async with integrity_write(db):
        plan=await prepare(db)
        require(fingerprint(plan)==expected, 'Records changed since preview; prepare a fresh plan.')
        employee,assigned,changes=plan
        if not changes: return {'status':'already_correct','changed_records':0}
        now=datetime.now(timezone.utc).isoformat()
        assignment_version=str(uuid.uuid4()) if any(name=='system_settings' for name,_,_ in changes) else assigned['version']
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                for name,original,update in changes:
                    current=await db[name].find_one({'_id':original['_id']},session=session)
                    require(current==original, 'Concurrent record change; transaction cancelled.')
                    await db.removed_employee_records.insert_one({'tenant_id':'solvit','repair_plan':expected,'source_collection':name,'original':original,'actor_id':'operator:approved-grace-kpi-correction','created_at':now},session=session)
                    update={**update,'version':assignment_version if name=='system_settings' else str(uuid.uuid4()),'updated_at':now}
                    if name=='performance_reviews': update['kpi_assignment_version']=assignment_version
                    result=await db[name].update_one({'_id':original['_id'],'version':original['version']},{'$set':update},session=session)
                    require(result.modified_count==1, 'Record update not confirmed; transaction cancelled.')
                await db.audit_logs.insert_one({'tenant_id':'solvit','event':'performance.finance.grace_weights_corrected','entity_id':employee_key(employee),'actor_id':'operator:approved-grace-kpi-correction','timestamp':now,'metadata':{'repair_plan':expected,'reason':'HR-approved combined nine KPI weights, 23 November 2026','changed_records':len(changes)}},session=session)
        verified=await prepare(db)
        require(not verified[2], 'Saved state needs review; do not rerun automatically.')
        return {'status':'corrected_and_verified','changed_records':len(changes),'weights':list(WEIGHTS.values())}


async def main(args):
    db=await init_db()
    try:
        plan=await prepare(db); digest=fingerprint(plan)
        if args.apply:
            require(args.confirm_plan==digest, 'Apply requires --confirm-plan with the reviewed preview fingerprint.')
            print(json.dumps(await apply(db,digest)))
        else:
            _,assigned,changes=plan
            after=corrected_values(assigned['values'])
            print(json.dumps({'status':'preview_only','plan':digest,'employee':'Grace Wangui Mungai','changed_records':len(changes),'goals':[{'objective':g['objective'],'weight':g['weight'],'group':g['group']} for g in after['goals']]}))
    finally: await close_db()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm-plan')
    try:
        asyncio.run(main(parser.parse_args()))
    except HTTPException as error:
        print('Repair stopped: '+str(error.detail)); sys.exit(1)
    except KeyError as error:
        if error.args[0] in {'MONGO_URL','DB_NAME'}:
            print('Production connection is not configured in this code session. Run in the backend environment with its existing MONGO_URL and DB_NAME.')
        else: print('Repair stopped: unexpected record structure.')
        sys.exit(1)
    except Exception as error:
        print('Repair not confirmed ('+type(error).__name__+'). Do not retry without reviewing the saved state.'); sys.exit(1)
