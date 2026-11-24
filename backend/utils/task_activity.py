"""User-approved active work boundary; historical records are never changed."""
from datetime import date,datetime,time,timedelta,timezone

EAT=timezone(timedelta(hours=3))
ACTIVE_SINCE='2026-11-23'
BOUNDARY=datetime(2026,11,23,tzinfo=EAT)


def timestamp(value):
    if isinstance(value,datetime):parsed=value
    elif isinstance(value,date):return datetime.combine(value,time(),tzinfo=EAT)
    elif isinstance(value,str):
        try:
            if len(value)==10:return datetime.combine(date.fromisoformat(value),time(),tzinfo=EAT)
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    else:return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def current(row,*anchors):
    # A future due date or a recent status edit must not revive an old task.
    values=[row.get(key) for key in ('created_at','assigned_at','assigned_on','requested_at','submitted_at')]+list(anchors)
    return any(parsed is not None and parsed>=BOUNDARY for parsed in map(timestamp,values))


def current_checklist(row,employee):
    # Retrospective template creation must not revive an old employee's induction.
    assigned=[timestamp(row.get(key)) for key in ('assigned_at','assigned_on')]
    if any(value is not None for value in assigned):return any(value is not None and value>=BOUNDARY for value in assigned)
    start=timestamp(employee.get('onboarding_started_at') or employee.get('start_date'))
    return start is not None and start>=BOUNDARY
