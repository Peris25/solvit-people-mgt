import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LeaveHistory from './LeaveHistory';
import * as api from '../services/api';

jest.mock('../services/api', () => ({ correctLeaveHistory: jest.fn(), previewLeaveHistory: jest.fn(), importLeaveHistory: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks(); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
const row = { id: 'synthetic-leave', revision: 1, employee_name: 'Synthetic employee', leave_type: 'Annual', start_date: '2026-01-05', end_date: '2026-01-06', working_days: 1.5, status: 'Recorded', day_basis: 'Recorded units', can_correct_history: true };
const button = text => [...container.querySelectorAll('button')].find(element => element.textContent === text);

test('historical view shows empty state and preserves half days and source status', () => {
  act(() => root.render(<LeaveHistory rows={[]} onSaved={jest.fn()} />));
  expect(container.textContent).toContain('No historical records imported.');
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={jest.fn()} />));
  expect(container.textContent).toContain('1.5');
  expect(container.textContent).toContain('Recorded');
});

test('only server-authorized historical rows expose correction action', () => {
  act(() => root.render(<LeaveHistory rows={[{ ...row, can_correct_history: false }]} onSaved={jest.fn()} />));
  expect(button('Edit historical record')).toBeUndefined();
});

test('HR correction preserves identity and revision, requires reason, and refreshes only after confirmed save', async () => {
  const saved = jest.fn(); api.correctLeaveHistory.mockResolvedValue({ data: { id: row.id } });
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={saved} />));
  act(() => button('Edit historical record').click());
  expect(container.querySelector('input[aria-label="Historical reason"]').required).toBe(true);
  expect(container.querySelector('[aria-label="Historical employee_id"]')).toBeNull();
  act(() => {
    const input = container.querySelector('input[aria-label="Historical reason"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Source checked by HR');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.correctLeaveHistory).toHaveBeenCalledWith(row.id, expect.objectContaining({ revision: 1, working_days: 1.5, status: 'Recorded', reason: 'Source checked by HR' }));
  expect(saved).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Historical record corrected.');
});

test('failed correction stays open and reports error without claiming success', async () => {
  api.correctLeaveHistory.mockRejectedValue({ response: { data: { detail: 'Record changed. Reload.' } } });
  const saved = jest.fn();
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={saved} />));
  act(() => button('Edit historical record').click());
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Record changed');
  expect(container.querySelector('form')).not.toBeNull();
  expect(saved).not.toHaveBeenCalled();
});
