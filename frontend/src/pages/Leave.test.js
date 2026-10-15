import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Leave from './Leave';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
const mockRefresh = jest.fn();
jest.mock('../context/NotificationContext', () => ({ useNotifications: () => ({ refresh: mockRefresh }) }));
jest.mock('react-router-dom', () => ({ useSearchParams: () => [new URLSearchParams(), jest.fn()] }));
jest.mock('../components/EmployeePicker', () => () => <div>Covering colleague picker</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const user = { id: 'account', employee_id: 'staff', role: 'employee' };
const row = { id: 'request', employee_id: 'staff', employee_name: 'Synthetic Ada', leave_type: 'Annual', start_date: '2026-11-05', end_date: '2026-11-06', working_days: 2, status: 'Pending_Manager', can_cancel: true };
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user });
  api.getLeaveRequests.mockResolvedValue({ data: [row] });
  api.getLeaveTypes.mockResolvedValue({ data: { Annual: { description: 'Annual leave' } } });
  api.getMyEmployee.mockResolvedValue({ data: { id: 'staff', line_manager_id: 'boss', line_manager_name: 'Synthetic Manager' } });
  api.getLeaveBalances.mockResolvedValue({ data: { Annual: { remaining: 9.25 }, annual_available_to_request: 0 } });
  api.getLeaveRollover.mockResolvedValue({ data: null });
  api.getLeaveCalendar.mockResolvedValue({ data: { events: [] } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<Leave />)); };
const click = async text => { const button = [...container.querySelectorAll('button')].find(b => b.textContent === text); expect(button).toBeTruthy(); await act(async () => button.click()); };

test('shows saved fractional balances, real zero availability and own history without approval controls', async () => {
  await render();
  expect(container.querySelector('[data-testid="balance-accrued"]').textContent).toContain('0');
  expect(container.textContent).toContain('9.25');
  expect(container.textContent).toContain('Synthetic Ada');
  expect(container.textContent).not.toContain('HR final approval');
  expect(api.getLeaveBalances).toHaveBeenCalledWith('staff');
});

test('unknown availability is an HR review state, never invented zero credit', async () => {
  api.getLeaveBalances.mockResolvedValue({ data: { Annual: { remaining: 9.25 }, annual_available_to_request: null } });
  await render(); expect(container.textContent).toContain('Needs HR review');
});

test('failed history has retry state rather than an empty successful history', async () => {
  api.getLeaveRequests.mockRejectedValue(new Error('offline'));
  await render(); expect(container.textContent).toContain('Leave history is unavailable');
  expect(container.textContent).toContain('Retry');
});

test('withdrawal failure keeps the request visible', async () => {
  api.cancelLeave.mockRejectedValue({ response: { data: { detail: 'Only future pending leave can be withdrawn' } } });
  await render(); await click('Withdraw');
  expect(container.textContent).toContain('Only future pending leave');
  expect(container.querySelector('[data-testid="leave-request"]')).toBeTruthy();
});

test('manager recommendation uses the server-assigned stage and does not finalize HR approval', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'line_manager' } });
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, employee_id: 'report', approval_stage: 'manager', can_cancel: false, can_reject: true }] });
  api.leaveDecision.mockResolvedValue({ data: { id: 'request', status: 'Pending_HR' } });
  await render(); await act(async () => container.querySelector('[data-testid="leave-tab-team"]').click());
  await click('Review'); expect(container.textContent).not.toContain('HR final approval');
  await click('Recommend to HR');
  expect(api.leaveDecision).toHaveBeenCalledWith('request', expect.objectContaining({ decision: 'Approve', stage: 'manager', policy_review_confirmed: false }));
});

test('HR final review includes contract, calendar and document confirmations', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } });
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, employee_id: 'report', status: 'Pending_HR', approval_stage: 'hr', can_cancel: false }] });
  await render(); await act(async () => container.querySelector('[data-testid="leave-tab-team"]').click());
  await click('Review'); expect(container.textContent).toContain('Contract eligibility, recorded balance and gazetted holiday calendar verified');
  expect(container.textContent).toContain('HR final approval');
});

test('switching accounts clears the previous employee history while loading', async () => {
  await render(); let resolve;
  api.getLeaveRequests.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { ...user, id: 'second-account', employee_id: 'second' } });
  await render(); expect(container.textContent).not.toContain('Synthetic Ada');
  await act(async () => resolve({ data: [] }));
  expect(container.textContent).not.toContain('Synthetic Ada');
});

test('working-day display uses the server quote including fractional holiday-adjusted units', async () => {
  jest.useFakeTimers();
  try {
    api.previewLeave.mockResolvedValue({ data: { working_days: 1.5, notice_days_required: 7, warning: 'Calendar verified server-side' } });
    await render();
    await act(async () => container.querySelector('[data-testid="apply-leave-btn"]').click());
    for (const [label, value] of [['Leave start date', '2026-11-05'], ['Leave end date', '2026-11-07']]) {
      const input = container.querySelector(`[aria-label="${label}"]`);
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }
    await act(async () => jest.advanceTimersByTime(250));
    expect(api.previewLeave).toHaveBeenCalledWith(expect.objectContaining({ employee_id: 'staff' }), expect.any(Object));
    expect(container.textContent).toContain('Working Days: 1.5');
  } finally { jest.useRealTimers(); }
});
