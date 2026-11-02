import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeLeaveGroups from './EmployeeLeaveGroups';
import * as api from '../services/api';
jest.mock('../services/api');
import { leaveStatus } from '../utils/leaveDisplay';

global.IS_REACT_ACT_ENVIRONMENT = true;
test('groups separate employee identities and leave types without counting denied days as approved', () => {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const rows = [
    { id: '1', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 1.75, status: 'Approved', start_date: `${new Date().getFullYear()}-01-05` },
    { id: '2', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Sick', working_days: 2, status: 'Pending_HR', start_date: `${new Date().getFullYear()}-01-05` },
    { id: '3', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 4, status: 'Rejected', start_date: `${new Date().getFullYear()}-01-05` },
    { id: '4', employee_id: 'b', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 3, status: 'Approved', start_date: `${new Date().getFullYear()}-01-05` },
  ];
  act(() => root.render(<EmployeeLeaveGroups rows={rows} renderRecords={records => <p>{records.map(row => row.id).join(',')}</p>} />));
  expect(container.querySelectorAll('[data-testid="employee-leave-groups"] > details')).toHaveLength(2);
  expect(container.textContent).toContain('Days taken: 1.75');
  expect(container.textContent).not.toContain('pending days');
  expect(container.textContent).toContain('Days remaining:');
  expect(container.textContent).toContain('Compassionate leave');
  expect(container.textContent).toContain('Maternity leave');
  expect(leaveStatus('Pending_Manager')).toBe('Pending');
  expect(leaveStatus('Pending_HR')).toBe('Pending');
  expect(leaveStatus('Rejected')).toBe('Denied');
  act(() => root.unmount()); container.remove();
});


test('loads each expanded employee balance from the authorized API and never invents remaining days', async () => {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  api.getLeaveBalances.mockResolvedValue({ data: { annual_available_to_request: 3.25, Annual: { remaining: 4.25 }, Sick: { remaining: 12 } } });
  await act(async () => root.render(<EmployeeLeaveGroups rows={[{ id: 'r', employee_id: 'a', employee_name: 'Synthetic Ada', leave_type: 'Annual', working_days: 2, status: 'Approved', start_date: `${new Date().getFullYear()}-01-05` }]} renderRecords={() => <p>Dated rows</p>} />));
  expect(api.getLeaveBalances).not.toHaveBeenCalled();
  await act(async () => { const section = container.querySelector('details'); section.open = true; section.dispatchEvent(new Event('toggle')); });
  expect(api.getLeaveBalances).toHaveBeenCalledWith('a');
  expect(container.textContent).toContain('Days remaining: 4.25');
  expect(container.textContent).toContain('Days remaining: 12');
  expect(container.textContent).toContain('Needs HR review');
  act(() => root.unmount()); container.remove(); jest.clearAllMocks();
});
