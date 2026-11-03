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

test('employee withdrawal is labelled Withdrawn rather than Denied and has no approval control', async () => {
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, status: 'Cancelled', can_cancel: false }] });
  await render();
  expect(container.querySelector('[data-testid="status-badge-Withdrawn"]')).not.toBeNull();
  expect(container.textContent).not.toContain('Denied');
  expect([...container.querySelectorAll('button')].some(button => button.textContent === 'Review')).toBe(false);
});

test('HR starts in the pending application queue including pending imported entries', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } });
  api.getLeaveRequests.mockResolvedValue({ data: [
    { ...row, employee_id: 'report', employee_name: 'Synthetic Joseph', can_hr_override: true },
    { ...row, id: 'history', employee_id: 'old', employee_name: 'Imported history', historical_import: true, status: 'Pending' },
    { ...row, id: 'withdrawn', employee_id: 'other', employee_name: 'Withdrawn employee', status: 'Cancelled' },
  ] });
  await render();
  expect(container.textContent).toContain('Synthetic Joseph');
  expect(container.textContent).toContain('Imported history');
  expect(container.querySelector('[data-testid="employee-leave-groups"]')).toBeNull();
  expect(container.querySelector('[data-testid="team-leave"] tbody tr')).not.toBeNull();
  expect(container.textContent).not.toContain('0 pending days');
  expect(container.textContent).not.toContain('Withdrawn employee');
  const select = container.querySelector('[aria-label="Team leave status"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'Withdrawn');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  expect(container.textContent).toContain('Withdrawn employee');
  expect(container.textContent).not.toContain('Synthetic Joseph');
});

test('employee edits dates and resubmits through the authorized API', async () => {
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, can_edit: true }] });
  api.resubmitLeave.mockResolvedValue({ data: { ...row, end_date: '2026-11-09' } });
  await render(); await click('Edit and resubmit');
  const end = container.querySelector('[aria-label="Leave end date"]');
  expect(end.disabled).toBe(false);
  expect(container.querySelector('[aria-label="Leave type"]').disabled).toBe(false);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(end, '2026-11-09');
    end.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.resubmitLeave).toHaveBeenCalledWith(row.id, expect.objectContaining({ start_date: row.start_date, end_date: '2026-11-09', leave_type: 'Annual' }));
  expect(api.supplementLeave).not.toHaveBeenCalled();
  expect(api.createLeaveRequest).not.toHaveBeenCalled();
});

test.each(['Approved', 'Rejected', 'Cancelled'])('employee cannot edit a finalized %s request', async status => {
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, status, can_edit: false, can_cancel: false }] });
  await render();
  expect([...container.querySelectorAll('button')].some(button => button.textContent === 'Edit and resubmit')).toBe(false);
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

test('HR can select direct approval with reason and policy confirmations while manager routing remains pending', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } });
  api.getLeaveRequests.mockResolvedValue({ data: [{ ...row, employee_id: 'report', can_cancel: false, can_hr_override: true }] });
  api.leaveDecision.mockResolvedValue({ data: { id: row.id, status: 'Approved' } });
  await render(); await act(async () => container.querySelector('[data-testid="leave-tab-team"]').click());
  await click('Review');
  const override = [...container.querySelectorAll('label')].find(label => label.textContent.includes('overriding manager routing')).querySelector('input');
  expect(override.checked).toBe(true);
  expect(container.textContent).toContain('Contract eligibility');
  await click('Approve directly as HR');
  expect(api.leaveDecision).toHaveBeenCalledWith(row.id, expect.objectContaining({ hr_override: true, stage: 'hr', decision: 'Approve' }));
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


test('HR can approve the pending imported row directly from Team Leave without changing dates or days', async () => {
  HTMLDialogElement.prototype.showModal = jest.fn(function () { this.setAttribute('open', ''); });
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } });
  const imported = { ...row, id: 'imported', employee_id: 'report', employee_name: 'Synthetic Joseph', historical_import: true, can_correct_history: true, status: 'Pending', revision: 3, day_basis: 'Recorded units', can_cancel: false };
  api.getLeaveRequests.mockResolvedValue({ data: [imported] });
  api.correctLeaveHistory.mockResolvedValue({ data: { ...imported, status: 'Approved', revision: 4 } });
  await render(); await click('Review');
  expect(document.body.querySelector('dialog').textContent).toContain('Review imported leave');
  await act(async () => {
    const input = document.body.querySelector('[aria-label="Imported leave decision reason"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'HR reviewed and approved source entry');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => [...document.body.querySelectorAll('button')].find(button => button.textContent === 'Approve leave').click());
  expect(api.correctLeaveHistory).toHaveBeenCalledWith('imported', expect.objectContaining({ status: 'Approved', revision: 3, start_date: imported.start_date, end_date: imported.end_date, working_days: 2, reason: 'HR reviewed and approved source entry' }));
  expect(api.leaveDecision).not.toHaveBeenCalled();
});
