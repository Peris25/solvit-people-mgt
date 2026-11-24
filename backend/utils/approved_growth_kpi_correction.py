"""One-time authorized four-KPI correction for Lucy; no emails or review launch."""
from copy import deepcopy
import logging
import uuid
from fastapi import HTTPException
from utils import performance_v3 as process,role_kpi_library as library
from utils.employee_integrity import employee_key,integrity_write
from utils.staff_views import token

logger=logging.getLogger(__name__)
MARKER=process.key('approved-data-correction','solvit','lucy-four-growth-kpis-20261124')
EXPECTED={'valuationprospects':40,'averagepartnernps':20,'keypartnersretention':20,'newpartnersawardedfleets':20}


def require(value,reason):
    if not value:raise HTTPException(409,reason)


def approved_values(source):
    for field in (('values',) if source.get('values') else ('published_values',)):
        candidate=source.get(field)
        if not candidate:continue
        try:
            values=library.validate({key:deepcopy(candidate[key]) for key in library.ENTRY_FIELDS})
            weights={token(goal['objective']):goal['weight'] for goal in values['goals']}
            if 'keypartnerretention' in weights:weights['keypartnersretention']=weights.pop('keypartnerretention')
            if values['role_id']!='growth-captain' or len(values['goals'])!=4 or weights!=EXPECTED or values['scope']!='Annual' or library.issues(values):continue
        except (HTTPException,KeyError,TypeError,ValueError):continue
        values['notes']='Four Annual Growth Captain KPIs, as approved in the 24 November 2026 change request.'
        return values,source.get('version') if field=='values' else source.get('published_version') or source.get('version'),field
    require(False,'approved_role_not_ready')


def definition(goal):
    return tuple(str(goal.get(key,'')).strip().casefold() for key in ('objective','metric','target','target_value','direction','unit'))


def review_update(review,values):
    require(review.get('workflow_version')==3 and review.get('status')=='Self_Draft' and not review.get('manager_assessment') and not review.get('released_at'),'review_requires_hr_reconciliation')
    result={'section_a_kpis':deepcopy(values['goals']),'group_weights':deepcopy(values['group_weights'])}
    if result['section_a_kpis']==review.get('section_a_kpis') and result['group_weights']==review.get('group_weights',{}):return {}
    assessment=review.get('self_assessment')
    if assessment is not None:
        require(isinstance(assessment,dict) and isinstance(assessment.get('actuals',{}),dict),'draft_requires_hr_reconciliation')
        previous=assessment.get('actuals',{})
        if previous:
            retained={}
            for goal in values['goals']:
                matches=[old for old in review.get('section_a_kpis',[]) if definition(old)==definition(goal)]
                if len(matches)==1 and matches[0]['id'] in previous:
                    retained[goal['id']]=deepcopy(previous[matches[0]['id']])
            result['self_assessment']={**deepcopy(assessment),'actuals':retained}
            result['kpi_draft_revisions']=[*deepcopy(review.get('kpi_draft_revisions') or []),{
                'recorded_at':process.flow.now(),'reason':'Updated to the four HR-approved Growth Captain KPIs.',
                'goals':deepcopy(review.get('section_a_kpis') or []),'actuals':deepcopy(previous)}]
    result['kpi_revision_note']='Your review now uses the four approved Growth Captain KPIs. Matching answers were retained; check the new or changed KPIs before submitting. Previous KPI draft entries, where present, are available below.'
    return result


async def prepare(db):
    people=await db.employees.find(process.tenant_query('solvit')).to_list(None)
    matches=[person for person in people if token(person.get('full_name'))=='lucyndinguri']
    require(len(matches)==1,'employee_identity_not_unique')
    employee=matches[0]
    canonical=await process.find_employee(db,employee_key(employee),'solvit')
    require(canonical and canonical['_id']==employee['_id'],'employee_identity_not_unique')
    require(process.enabled(employee) and process.fte(employee) and process.employee_kpi_scope(employee)=='Annual','employee_not_annual_eligible')
    source=await db.system_settings.find_one({'_id':library.identity(employee,'growth-captain'),'tenant_id':'solvit'})
    require(source,'approved_role_not_ready')
    values,source_version,source_field=approved_values(source)
    require(source_version,'approved_role_not_ready')
    assigned=await process.assignment(db,employee)
    require(assigned and assigned.get('version'),'assignment_requires_hr_review')
    rows=await db.performance_reviews.find(process.scoped(employee,{'employee_id':{'$in':process.reference_ids(employee)+[employee['_id']]},
        'cycle_type':'Year_End','cycle_year':2026,'status':{'$nin':['Archived','Cancelled','Completed']}})).to_list(None)
    changes=[]
    if assigned['values']!=values:changes.append(('system_settings',assigned,{'values':values,'source_version':source_version}))
    for row in rows:
        update=review_update(row,values)
        if update:changes.append(('performance_reviews',row,update))
    return employee,source,assigned,values,source_field,changes


async def apply(db):
    async with integrity_write(db):
        previous=await db.audit_logs.find_one({'_id':MARKER})
        if previous:return {'status':'applied','already_applied':True,'kpi_count':4,'reviews_updated':previous['metadata']['reviews_updated']}
        employee,source,assigned,values,source_field,changes=await prepare(db)
        now=process.flow.now();assignment_version=str(uuid.uuid4()) if any(name=='system_settings' for name,_,_ in changes) else assigned['version']
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                require(await db.employees.find_one({'_id':employee['_id']},session=session)==employee,'concurrent_record_change')
                require(await db.system_settings.find_one({'_id':source['_id']},session=session)==source,'concurrent_record_change')
                require(await db.system_settings.find_one({'_id':assigned['_id']},session=session)==assigned,'concurrent_record_change')
                for name,original,update in changes:
                    require(await db[name].find_one({'_id':original['_id']},session=session)==original,'concurrent_record_change')
                    await db.removed_employee_records.insert_one({'tenant_id':'solvit','source_collection':name,'original':original,'repair_id':str(MARKER),'created_at':now},session=session)
                    update={**update,'version':assignment_version if name=='system_settings' else str(uuid.uuid4()),'updated_at':now}
                    if name=='performance_reviews':update['kpi_assignment_version']=assignment_version
                    result=await db[name].update_one({'_id':original['_id'],'version':original['version']},{'$set':update},session=session)
                    require(result.modified_count==1,'concurrent_record_change')
                await db.audit_logs.insert_one({'_id':MARKER,'tenant_id':'solvit','event':'performance.growth.four_kpis_corrected','entity_id':employee_key(employee),
                    'actor_id':'operator:approved-four-growth-kpis','timestamp':now,'metadata':{'reason':'User approved Lucy’s four Growth Captain KPIs and weights, 24 November 2026.',
                    'source_field':source_field,'source_version':source.get('version'),'reviews_updated':sum(name=='performance_reviews' for name,_,_ in changes),'changed_records':len(changes)}},session=session)
        require(not (await prepare(db))[-1],'saved_state_unconfirmed')
        return {'status':'applied','kpi_count':4,'reviews_updated':sum(name=='performance_reviews' for name,_,_ in changes)}


async def run(db):
    try:return await apply(db)
    except HTTPException as error:
        logger.warning('Approved four-KPI correction needs review (%s).',error.detail)
        return {'status':'needs_review','reason':error.detail}
    except Exception as error:
        logger.error('Approved four-KPI correction unconfirmed (%s).',type(error).__name__)
        return {'status':'unconfirmed'}
