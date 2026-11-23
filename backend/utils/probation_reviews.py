"""Manager-led probation assessment, meeting, HR outcome and acknowledgement."""
from copy import deepcopy
from datetime import datetime, date, timezone
import uuid
from utils import performance_workflows as flow, performance_v3 as process, performance_v3_scoring as calc
from utils.employee_integrity import employee_key, is_direct_report
from utils.employee_access import reference_ids, personal_grant


def applies(row): return row.get('workflow_version') == 1 and row.get('cycle_type') == 'Probation'
def version(row): return str(row.get('probation_version') or row.get('updated_at') or row.get('created_at') or '') + ':' + str(row.get('kpi_assignment_version') or '')


async def prepare(db, row, employee):
    result = deepcopy(row)
    if not result.get('section_a_kpis') and not result.get('manager_assessment'):
        saved = await process.assignment(db, employee)
        values = (saved or {}).get('values') or {}
        try: valid = values.get('scope') == 'Probation' and not process.library.issues(values)
        except (KeyError, TypeError, ValueError): valid = False
        if valid:
            result.pop('probation_kpi_issue',None)
            result.update(section_a_kpis=deepcopy(values['goals']), probation_group_weights=deepcopy(values.get('group_weights') or {}), kpi_assignment_version=saved.get('version'))
        else: result['probation_kpi_issue'] = 'HR must assign complete approved Probation KPIs before the manager can assess this employee.'
    return result


def project(row, user, employee, result):
    own = user.get('employee_id') in reference_ids(employee)
    result.update(manager_led_probation=True, probation_version=version(row), can_self_assess=False, can_update_goal_progress=False,
                  probation_kpi_issue=row.get('probation_kpi_issue'), meeting_completed_at=row.get('meeting_completed_at'),
                  probation_group_weights=deepcopy(row.get('probation_group_weights') or {}))
    if result.get('can_manage'):
        result['probation_manager_draft'] = deepcopy(row.get('probation_manager_draft'))
    # Submitted manager findings are available for the discussion; drafts stay private.
    reviewer = not own and (user.get('role') in flow.HR or is_direct_report(employee,user))
    if reviewer or flow.released(row) or (own and row.get('status') in {'Manager_Submitted','HR_Reviewed','Completed'}):
        for key in ('manager_assessment','section_a_score','section_b_score','probation_meeting','employee_comments'):
            if key in row: result[key] = deepcopy(row[key])
    if (user.get('role') in flow.HR and not own) or flow.released(row):
        for key in ('probation_outcome','hr_summary','probation_acknowledgement'):
            if key in row: result[key] = deepcopy(row[key])
    writable=True
    try: personal_grant(user,'M05',write=True)
    except flow.HTTPException: writable=False
    result['can_probation_comment'] = writable and own and row.get('status') == 'Manager_Submitted'
    result['can_probation_acknowledge'] = writable and own and flow.released(row) and not row.get('probation_acknowledgement')
    result['probation_assessment_submitted'] = bool(row.get('manager_assessment'))
    return result


def checked(body, allowed, row):
    if set(body) - set(allowed) - {'expected_version'}: flow.fail('Unknown probation review fields')
    if body.get('expected_version') != version(row): flow.fail('This review changed. Reload before saving.',409)


async def save(db, user, row, update, event):
    await flow.save(db,user,row,{**update,'probation_version':str(uuid.uuid4())},event)


def assessment(row, body, submit):
    goals=row.get('section_a_kpis') or []
    if not goals: flow.fail(row.get('probation_kpi_issue') or 'HR must assign approved Probation KPIs.',409)
    entries=body.get('kpis',{}); values=body.get('values',[])
    if not isinstance(entries,dict) or set(entries)-{g['id'] for g in goals}: flow.fail('Use the assigned KPI identifiers only')
    if not isinstance(values,list) or len(values)>5: flow.fail('Provide the five values ratings')
    scores={}; cleaned={}
    for goal in goals:
        item=entries.get(goal['id'],{})
        if not isinstance(item,dict) or set(item)-{'m1','m2','m3','combined_actual','score','evidence','score_reason'}: flow.fail('Invalid monthly KPI fields')
        entry={}
        for key in ('m1','m2','m3','evidence','score_reason'):
            text=item.get(key,'')
            if not isinstance(text,str) or len(text)>4000: flow.fail('Invalid KPI evidence or monthly actual')
            entry[key]=text.strip()
        actual=item.get('combined_actual')
        if actual not in (None,''): entry['combined_actual']=float(calc.number(actual))
        score=item.get('score')
        automatic=None
        if goal.get('direction') in {'Higher','Lower'} and actual not in (None,''):
            automatic=calc.kpi_score(goal,actual)
        if score not in (None,''): scores[goal['id']]=float(calc.number(score,1,3))
        elif automatic is not None: scores[goal['id']]=automatic
        if goal['id'] in scores: entry['score']=scores[goal['id']]
        if submit:
            month=row.get('review_month')
            if not entry.get(f'm{month}') or (month==3 and not entry.get('m2')): flow.fail('Record actuals for the review month; Month 3 also requires Month 2 actuals.')
            if not entry['evidence'] or goal['id'] not in scores: flow.fail('Provide a score and supporting evidence for every KPI')
            if goal.get('direction') in {'Higher','Lower'} and actual in (None,''): flow.fail('Provide the numeric result used for each measured KPI; Month 3 uses the verified combined Months 2–3 result.')
            if automatic is not None and scores[goal['id']] != automatic and not entry['score_reason']: flow.fail('Explain any manager score that differs from the calculated KPI score')
        cleaned[goal['id']]=entry
    clean_values=[]
    for item in values:
        if not isinstance(item,dict) or set(item)-{'score','evidence','concerns'}: flow.fail('Invalid values rating')
        if any(not isinstance(item.get(key,''),str) for key in ('evidence','concerns')): flow.fail('Values evidence and concerns must be text')
        value={key:item.get(key,'').strip() for key in ('evidence','concerns')}
        if any(len(text)>4000 for text in value.values()): flow.fail('Values evidence is too long')
        if item.get('score') not in (None,''): value['score']=float(calc.number(item['score'],1,3))
        clean_values.append(value)
    text_fields={}
    for key in ('summary','strengths','development_actions','recommendation'):
        value=body.get(key,'')
        if not isinstance(value,str) or len(value)>4000: flow.fail('Invalid probation assessment text')
        text_fields[key]=value.strip()
    section_a=section_b=None
    if submit:
        if len(clean_values)!=5 or any('score' not in v or not v['evidence'] for v in clean_values): flow.fail('Score all five values and provide observed evidence')
        if not all(text_fields.values()): flow.fail('Complete the summary, strengths, development actions and recommendation')
        allowed={'Confirm','Extend','Not confirmed'} if row.get('review_month')==3 else {'Continue probation','Concerns raised'}
        if text_fields['recommendation'] not in allowed: flow.fail('Choose a recommendation appropriate to this probation month')
        section_a=calc.weighted_kpi_scores(goals,scores,row.get('probation_group_weights'))['score']
        section_b=calc.rounded(sum(calc.number(v['score'],1,3) for v in clean_values)/5)
    return {**text_fields,'kpis':cleaned,'values':clean_values,'basis':'Months 2–3 combined' if row.get('review_month')==3 else f"Month {row.get('review_month')}",
            'section_a_score':section_a,'section_b_score':section_b}


async def assess(db,user,row,employee,stage,body):
    personal_grant(user,'M05',write=True)
    own=user.get('employee_id') in reference_ids(employee)
    manager=not own and is_direct_report(employee,user)
    hr=user.get('role') in flow.HR and not own
    status=row.get('status')
    if stage=='self': flow.fail('Probation is manager-led. Employees add comments after the manager submits; no self-scoring is required.',409)
    if stage=='manager':
        if not manager: flow.fail('Only the current line manager may score this probation review',403)
        if status not in {'Draft','Self_Draft','Self_Submitted'} or row.get('manager_assessment'): flow.fail('The manager assessment has already been submitted',409)
        checked(body,{'kpis','values','summary','strengths','development_actions','recommendation','submit'},row)
        if type(body.get('submit')) is not bool: flow.fail('Choose Save draft or Submit')
        values=assessment(row,body,body['submit'])
        update={'probation_workflow_version':2,'section_a_kpis':row['section_a_kpis'],'probation_group_weights':row.get('probation_group_weights') or {},'kpi_assignment_version':row.get('kpi_assignment_version')}
        if body['submit']:
            values.update(actor_id=user['id'],submitted_at=flow.now())
            update.update(manager_assessment=values,status='Manager_Submitted',section_a_score=values['section_a_score'],section_b_score=values['section_b_score'],probation_manager_draft=None)
        else: update['probation_manager_draft']=values
        await save(db,user,row,update,'performance.assessment.manager' if body['submit'] else 'performance.probation.manager_draft')
    elif stage=='employee-comments':
        if not own or status!='Manager_Submitted': flow.fail('Only the employee may add comments before HR approval',403)
        checked(body,{'comments'},row)
        await save(db,user,row,{'employee_comments':{'text':flow.text(body.get('comments'),'employee comments'),'actor_id':user['id'],'recorded_at':flow.now()}},'performance.probation.employee_comments')
    elif stage=='meeting-complete':
        if not(manager or hr): flow.fail('The line manager or HR must record the meeting',403)
        if status!='Manager_Submitted' or row.get('meeting_completed_at'): flow.fail('The meeting cannot be completed at this stage',409)
        checked(body,{'discussion','agreed_actions'},row)
        try: scheduled=datetime.fromisoformat(row['review_meeting']['scheduled_at'].replace('Z','+00:00'))
        except (KeyError,ValueError,TypeError): flow.fail('HR must confirm the meeting date and participants first',409)
        if scheduled.tzinfo is None or scheduled>datetime.now(timezone.utc): flow.fail('The meeting must take place before its completion is recorded',409)
        current_manager=await process.find_employee(db,employee.get('line_manager_id'),process.tenant_of(employee))
        if not current_manager or set(row['review_meeting'].get('participant_employee_ids') or [])!={employee_key(employee),employee_key(current_manager)}:
            flow.fail('The reporting line changed. HR must confirm the meeting with the current line manager.',409)
        meeting={'discussion':flow.text(body.get('discussion'),'discussion notes'),'agreed_actions':flow.text(body.get('agreed_actions'),'agreed development actions'),'recorded_by':user['id']}
        await save(db,user,row,{'probation_meeting':meeting,'meeting_completed_at':flow.now()},'performance.probation.meeting_completed')
    elif stage=='hr':
        if not hr: flow.fail('HR must approve the probation outcome',403)
        if status!='Manager_Submitted' or not row.get('meeting_completed_at'): flow.fail('Complete the employee–manager review meeting before HR approval',409)
        checked(body,{'summary','outcome','extension_end_date','extension_agreement_reference'},row)
        outcome=body.get('outcome')
        allowed={'Confirm','Extend','Not confirmed'} if row.get('review_month')==3 else {'Continue probation','Concerns raised'}
        if outcome not in allowed: flow.fail('Choose an outcome appropriate to this probation month')
        decision={'outcome':outcome,'approved_by':user['id'],'approved_at':flow.now()}
        if outcome=='Extend':
            try: end=date.fromisoformat(body.get('extension_end_date',''))
            except (TypeError,ValueError): flow.fail('Enter the new probation end date')
            if end<=process.today(): flow.fail('Extension end date must be in the future')
            decision.update(extension_end_date=end.isoformat(),extension_agreement_reference=flow.text(body.get('extension_agreement_reference'),'employee written extension agreement reference'))
        await save(db,user,row,{'probation_outcome':decision,'hr_summary':flow.text(body.get('summary'),'HR summary'),'hr_reviewed_by':user['id'],'hr_reviewed_at':flow.now(),'status':'HR_Reviewed'},'performance.probation.hr_approved')
    elif stage=='release':
        if not hr: flow.fail('HR must release the outcome',403)
        checked(body,set(),row)
        if status!='HR_Reviewed' or not row.get('meeting_completed_at') or not row.get('probation_outcome'): flow.fail('Complete the meeting and HR outcome approval before release',409)
        await save(db,user,row,{'status':'Completed','released_at':flow.now(),'released_by':user['id']},'performance.assessment.release')
    elif stage=='acknowledge':
        if not own or not flow.released(row): flow.fail('Only the employee may acknowledge a released outcome',403)
        checked(body,{'acknowledged','comments'},row)
        if body.get('acknowledged') is not True: flow.fail('Confirm receipt of the review')
        if row.get('probation_acknowledgement'): flow.fail('Receipt is already recorded',409)
        comments=body.get('comments','')
        if not isinstance(comments,str) or len(comments)>4000: flow.fail('Invalid acknowledgement comments')
        await save(db,user,row,{'probation_acknowledgement':{'actor_id':user['id'],'recorded_at':flow.now(),'comments':comments,'receipt_only':True}},'performance.probation.acknowledged')
    else: flow.fail('Unknown probation review action')
    return flow.projection(row,user,employee)
