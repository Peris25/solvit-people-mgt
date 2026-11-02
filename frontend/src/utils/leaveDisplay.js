export function leaveStatus(value) {
  if (value === 'Approved') return 'Approved';
  if (['Denied', 'Rejected', 'Cancelled'].includes(value)) return 'Denied';
  return 'Pending';
}

export const leaveCategories = {
  Annual: 'Annual leave', Sick: 'Sick leave', Compassionate: 'Compassionate leave',
  Maternity: 'Maternity leave', Paternity: 'Paternity leave', Unpaid: 'Unpaid leave',
};
