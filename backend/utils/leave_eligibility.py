"""Parental leave eligibility from the saved employee profile."""


def parental_leave_type(employee):
    gender = str((employee or {}).get('gender') or '').strip().casefold()
    if gender in {'female', 'f'}:
        return 'Maternity'
    if gender in {'male', 'm'}:
        return 'Paternity'
    return None


def eligible_leave_types(types, employee):
    parental = parental_leave_type(employee)
    return {kind: value for kind, value in types.items()
            if kind not in {'Maternity', 'Paternity'} or kind == parental}
