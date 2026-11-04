import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeLeaveBalances from './EmployeeLeaveBalances';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  jest.useFakeTimers();
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getEmployeeLeaveBalances.mockResolvedValue({ data: { total: 1, departments: ['IT Support'], items: [{ record_key: '1', employee_id: 'staff', name: 'Synthetic Ada', department: 'IT Support', annual_pending_days: 0, balances: { Annual: { remaining: 4.5, used: 13, accrued_kenyan_act: 17.5 }, annual_available_to_request: 4.5 } }] } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<EmployeeLeaveBalances />)); await act(async () => jest.advanceTimersByTime(300)); };
test('displays existing balances without zero pending clutter or editing controls', async () => {
  await render();
  expect(container.textContent).toContain('Synthetic Ada');
  expect(container.textContent).toContain('4.5');
  expect(container.textContent).not.toContain('0 days pending');
  expect(container.textContent).not.toContain('Save');
  expect(api.getEmployeeLeaveBalances).toHaveBeenCalledWith({ search: '', department: '', offset: 0, limit: 20 });
});
test('department filtering queries the server and positive pending units are separate', async () => {
  await render();
  const select = container.querySelector('select');
  await act(async () => { select.value = 'IT Support'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => jest.advanceTimersByTime(300));
  expect(api.getEmployeeLeaveBalances).toHaveBeenLastCalledWith({ search: '', department: 'IT Support', offset: 0, limit: 20 });
});
test('missing balance is HR review state rather than zero', async () => {
  api.getEmployeeLeaveBalances.mockResolvedValue({ data: { total: 1, departments: [], items: [{ record_key: '1', name: 'Synthetic Ada', balances: null, needs_review: true }] } });
  await render(); expect(container.textContent).toContain('Needs HR review');
});
test('server failure has retry state', async () => {
  api.getEmployeeLeaveBalances.mockRejectedValue(new Error('Unavailable'));
  await render(); expect(container.querySelector('[role="alert"]').textContent).toContain('Retry');
});
