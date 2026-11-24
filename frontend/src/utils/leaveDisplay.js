export function leaveStatus(value) {
  if (value === 'Approved') return 'Approved';
  if (['Cancelled', 'Canceled', 'Withdrawn'].includes(value)) return 'Withdrawn';
  if (['Denied', 'Rejected'].includes(value)) return 'Denied';
  return 'Pending';
}

export function nairobiDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone:'Africa/Nairobi', year:'numeric', month:'2-digit', day:'2-digit' }).formatToParts(now);
  const value = type => parts.find(part => part.type === type).value;
  return `${value('year')}-${value('month')}-${value('day')}`;
}

export function leaveTiming(row, today) {
  if (row.status !== 'Approved' || !/^\d{4}-\d{2}-\d{2}$/.test(row.start_date || '') || !/^\d{4}-\d{2}-\d{2}$/.test(row.end_date || '') || row.end_date < row.start_date) return null;
  if (row.start_date <= today && row.end_date >= today) return 'On leave now';
  return row.start_date > today ? 'Upcoming leave' : null;
}

export const leaveCategories = {
  Annual: 'Annual leave', Sick: 'Sick leave', Compassionate: 'Compassionate leave',
  Maternity: 'Maternity leave', Paternity: 'Paternity leave', Unpaid: 'Unpaid leave',
};
