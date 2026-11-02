import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeLeaveGroups from './EmployeeLeaveGroups';
import { leaveStatus } from '../utils/leaveDisplay';

global.IS_REACT_ACT_ENVIRONMENT = true;
test('groups separate employee identities and leave types without counting denied days as approved', () => {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const rows = [
    { id: '1', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 1.75, status: 'Approved' },
    { id: '2', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Sick', working_days: 2, status: 'Pending_HR' },
    { id: '3', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 4, status: 'Rejected' },
    { id: '4', employee_id: 'b', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 3, status: 'Approved' },
  ];
  act(() => root.render(<EmployeeLeaveGroups rows={rows} renderRecords={records => <p>{records.map(row => row.id).join(',')}</p>} />));
  expect(container.querySelectorAll('[data-testid="employee-leave-groups"] > details')).toHaveLength(2);
  expect(container.textContent).toContain('1.75 approved days');
  expect(container.textContent).toContain('2 pending days');
  expect(container.textContent).toContain('Compassionate leave');
  expect(container.textContent).toContain('Maternity leave');
  expect(leaveStatus('Pending_Manager')).toBe('Pending');
  expect(leaveStatus('Pending_HR')).toBe('Pending');
  expect(leaveStatus('Rejected')).toBe('Denied');
  act(() => root.unmount()); container.remove();
});
