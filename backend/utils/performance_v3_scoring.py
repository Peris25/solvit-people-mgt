"""V3 calculations: explicit inputs, Decimal arithmetic, no fabricated ratings."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from utils.performance_workflows import fail

VALUES = ['Integrity','Hard Work & Ownership','Teamwork & Decency','Solution Orientation','Timeliness']
QUESTIONS = [
'Does this person consistently do what they say they will do, and act in the best interests of the team and company?',
'Does this person take full accountability for their outcomes and consistently perform without needing to be pushed?',
'Does this person work well with others and treat every colleague with respect, regardless of level or role?',
'When this person encounters a problem, do they come with solutions and follow through on agreed actions?',
'Does this person reliably honour time - deadlines, meeting commitments, and response standards?']


def number(value, low=0, high=1000000000):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)): fail('Enter a finite number')
    try: value=Decimal(str(value))
    except InvalidOperation: fail('Enter a finite number')
    if not value.is_finite() or not Decimal(str(low))<=value<=Decimal(str(high)): fail('Number is outside its permitted range')
    return value


def rounded(value): return float(Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


def achievement_score(percent):
    return min(Decimal(3),max(Decimal(1),Decimal(1)+(Decimal(100)-percent)/Decimal(20)))


def kpi_score(goal, actual):
    kind=goal['direction']
    if kind=='Rated': return rounded(number(actual,1,3))
    if kind=='Binary':
        if not isinstance(actual,bool): fail('Done/not-done KPIs require true or false')
        return 1.0 if actual else 3.0
    actual=number(actual)
    target=number(goal.get('target_value'))
    if target<=0: fail('Zero targets require an approved scoring rule; HR must correct this KPI')
    if kind=='Higher': ratio=actual/target
    elif kind=='Lower':
        if actual==0: fail('A zero actual for a lower-is-better KPI requires HR clarification')
        ratio=target/actual
    else: fail('Confirm the KPI scoring method before assessment')
    return rounded(achievement_score(ratio*100))


def section_a(goals, actuals, group_weights=None):
    if not goals or len({g['id'] for g in goals}) != len(goals): fail('KPIs require unique identifiers')
    if not isinstance(actuals, dict): fail('Provide KPI actuals by identifier')
    if set(actuals)!={g['id'] for g in goals}: fail('Provide an actual for every KPI, exactly once')
    scores={g['id']:kpi_score(g,actuals[g['id']]) for g in goals}
    groups=group_weights or {}
    def weighted(rows):
        total=sum(number(g['weight'],0,100) for g in rows)
        if total!=100: fail('KPI weights must total 100%')
        return sum(Decimal(str(scores[g['id']]))*number(g['weight'],0,100) for g in rows)/100
    if groups:
        if sum(number(w,0,100) for w in groups.values())!=100: fail('Group weights must total 100%')
        if any(g.get('group') not in groups for g in goals): fail('Every KPI needs its approved group')
        result=sum(weighted([g for g in goals if g['group']==group])*number(weight,0,100)/100 for group,weight in groups.items())
    else: result=weighted(goals)
    return {'score':rounded(result),'kpi_scores':scores}


def section_b(responses, self_values):
    if len(responses)<3: fail('At least three peer reviews are required',409)
    if not isinstance(self_values, list) or len(self_values) != 5: fail('Provide five self-assessment values')
    if any(not isinstance(r.get('scores'), list) or len(r['scores']) != 5 for r in responses): fail('Each peer assessment must contain five values')
    if any(number(r.get('retain'), 0, 10) not in {Decimal(0), Decimal(5), Decimal(10)} for r in responses): fail('Choose Yes, Maybe or No for retention')
    averages=[sum(number(r['scores'][i],0,10) for r in responses)/len(responses) for i in range(5)]
    converted=[min(Decimal(3),max(Decimal(1),Decimal(1)+(Decimal(10)-avg)/2)) for avg in averages]
    gaps=[number(self_values[i],0,10)-avg for i,avg in enumerate(averages)]
    return {'score':rounded(sum(converted)/5),'averages':[rounded(x) for x in averages],
        'dimension_scores':[rounded(x) for x in converted],'gaps':[rounded(x) for x in gaps],
        'flagged':[abs(x)>2 for x in gaps],
        'retention_average':rounded(sum(number(r['retain'],0,10) for r in responses)/len(responses))}


def section_c(nps,csat):
    nps=number(nps,-100,100);csat=number(csat,1,5)
    n=Decimal(3) if nps<0 else achievement_score(nps/50*100)
    c=achievement_score(csat/Decimal('4.7')*100)
    return rounded((n+c)/2)


def final(a,b,c): return rounded(number(a,1,3)*Decimal('.5')+number(b,1,3)*Decimal('.3')+number(c,1,3)*Decimal('.2'))


def placement(a,b):
    a,b=number(a,1,3),number(b,1,3)
    if a<Decimal('1.5'): return 'Stars' if b<Decimal('1.5') else 'Core_Contributor' if b<2 else 'Culture_Risk'
    if a<2: return 'Core_Contributor' if b<2 else 'Culture_Risk'
    return 'Realignment_Needed' if b<2 else 'Exit_Track'


def bonus_multiplier(score, company_scorecard, values_hold=False):
    score = number(score, 1, 3)
    gate = number(company_scorecard, 0, 100)
    if gate < 80 or values_hold or score >= Decimal('2.5'): return 0.0
    bands = [(Decimal('1'), Decimal('1.15')), (Decimal('1.5'), Decimal('1.05')),
             (Decimal('2'), Decimal('1')), (Decimal('2.5'), Decimal('0'))]
    for (low, start), (high, end) in zip(bands, bands[1:]):
        if low <= score <= high:
            return float((start + (end - start) * (score - low) / (high - low)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP))
