"""Archive only unused V3 cycles; keep all records and audit history."""
from utils import performance_v3 as process, performance_workflows as flow


async def archive(db, user, reference, body):
    flow.require_hr(user); process.fields(body, {'reason'})
    row=await process.cycle(db,user,reference)
    if row.get('workflow_version')!=3: flow.fail('Use the original workflow for this cycle',409)
    if row.get('status')=='Archived': return {'id':row['id'],'status':'Archived'}
    reason=flow.text(body.get('reason'),'cycle deletion reason',1500)
    if len(reason)<10: flow.fail('Enter a clear reason of at least 10 characters')
    if row.get('status') not in {'Configured','Opening','Open'}: flow.fail('Only an unused cycle can be deleted',409)
    if row.get('company_feedback') is not None: flow.fail('This cycle already contains company feedback and cannot be deleted',409)
    reviews=await db.performance_reviews.find(process.scoped(user,{'cycle_id':row['id']})).to_list(None)
    protected=('self_assessment','manager_assessment','peer_summary','section_a_score','meeting_proposal','review_meeting','meeting_completed_at','released_at')
    if any(r.get('workflow_version')!=3 or r.get('status') not in {'Draft','Self_Draft'} or any(r.get(field) is not None for field in protected) for r in reviews):
        flow.fail('Assessment work has started. This cycle cannot be deleted.',409)
    tasks=await db.performance_peer_tasks.find(process.scoped(user,{'cycle_id':row['id']})).to_list(None)
    if any(t.get('status')!='Assigned' or t.get('started_at') or t.get('draft') is not None for t in tasks):
        flow.fail('Peer review work has started. This cycle cannot be deleted.',409)
    if await db.performance_peer_responses.find_one(process.scoped(user,{'cycle_id':row['id']})):
        flow.fail('This cycle has peer responses and cannot be deleted.',409)
    windows=await db.survey_windows.find(process.scoped(user,{'cycle_id':row['id']})).to_list(None)
    aliases=[value for window in windows for value in (window.get('id'),window.get('_id'),str(window.get('_id'))) if value is not None]
    if await db.survey_responses.find_one(process.scoped(user,{'$or':[{'cycle_id':row['id']},{'survey_window_id':{'$in':aliases}}]})):
        flow.fail('This cycle has Alignment Survey responses and cannot be deleted.',409)
    notices=await db.notifications.find(process.scoped(user,{'data.cycle_id':row['id'],'data.performance_v3':True})).to_list(None)
    now=flow.now(); update={'status':'Archived','archive_reason':reason,'archived_at':now,'archived_by':user['id']}
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            await db.audit_logs.insert_one({'tenant_id':process.tenant_of(user),'event':'performance.v3.cycle.archived','entity_id':row['id'],'actor_id':user['id'],'timestamp':now,'metadata':{'reason':reason,'unused_reviews':len(reviews),'unused_peer_tasks':len(tasks),'previous_status':row.get('status')}},session=session)
            await db.performance_cycles.update_one({'_id':row['_id']},{'$set':{**update,'archive_previous_status':row.get('status')}},session=session)
            for collection,records in ((db.performance_reviews,reviews),(db.performance_peer_tasks,tasks),(db.survey_windows,windows)):
                for record in records: await collection.update_one({'_id':record['_id']},{'$set':{**update,'archive_previous_status':record.get('status')}},session=session)
            for notice in notices:
                await db.notifications.update_one({'_id':notice['_id']},{'$set':{'cycle_archived':True,'is_read':True,'v3_email_pending':False}},session=session)
    return {'id':row['id'],'status':'Archived','unused_reviews':len(reviews)}
