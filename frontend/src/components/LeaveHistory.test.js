import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LeaveHistory from './LeaveHistory';
import * as api from '../services/api';

jest.mock('../services/api', () => ({ correctLeaveHistory: jest.fn(), previewLeaveHistory: jest.fn(), importLeaveHistory: jest.fn(), approveRecordedLeaveHistory: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;

beforeEach(() => { HTMLDialogElement.prototype.showModal = jest.fn(function () { this.setAttribute('open', ''); }); container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks(); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
const row = { id: 'synthetic-leave', revision: 1, employee_name: 'Synthetic employee', leave_type: 'Annual', start_date: '2026-01-05', end_date: '2026-01-06', working_days: 1.5, status: 'Approved', day_basis: 'Recorded units', can_correct_history: true };
const button = text => [...container.querySelectorAll('button')].find(element => element.textContent === text);

test('historical view shows empty state and preserves half days and source status', () => {
  act(() => root.render(<LeaveHistory rows={[]} onSaved={jest.fn()} />));
  expect(container.textContent).toContain('No leave records.');
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={jest.fn()} />));
  expect(container.textContent).toContain('1.5');
  expect(container.textContent).toContain('Approved');
});

test('only server-authorized historical rows expose correction action', () => {
  act(() => root.render(<LeaveHistory rows={[{ ...row, can_correct_history: false }]} onSaved={jest.fn()} />));
  expect(button('Edit historical record')).toBeUndefined();
});

test('HR correction preserves identity and revision, requires reason, and refreshes only after confirmed save', async () => {
  const saved = jest.fn(); api.correctLeaveHistory.mockResolvedValue({ data: { id: row.id } });
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={saved} />));
  act(() => button('Edit historical record').click());
  expect(document.body.querySelector('dialog[open]').textContent).toContain('Synthetic employee');
  expect(document.body.querySelector('input[aria-label="Historical reason"]').required).toBe(true);
  expect(document.body.querySelector('[aria-label="Historical employee_id"]')).toBeNull();
  act(() => {
    const input = document.body.querySelector('input[aria-label="Historical reason"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Source checked by HR');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => document.body.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.correctLeaveHistory).toHaveBeenCalledWith(row.id, expect.objectContaining({ revision: 1, working_days: 1.5, status: 'Approved', reason: 'Source checked by HR' }));
  expect(saved).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Historical record corrected.');
});

test('failed correction stays open and reports error without claiming success', async () => {
  api.correctLeaveHistory.mockRejectedValue({ response: { data: { detail: 'Record changed. Reload.' } } });
  const saved = jest.fn();
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={saved} />));
  act(() => button('Edit historical record').click());
  await act(async () => document.body.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(document.body.querySelector('[role="alert"]').textContent).toContain('Record changed');
  expect(document.body.querySelector('form')).not.toBeNull();
  expect(saved).not.toHaveBeenCalled();
});


test('Edit opens a modal immediately and Cancel closes it without writing', () => {
  act(() => root.render(<LeaveHistory rows={[row]} onSaved={jest.fn()} />));
  const trigger = button('Edit historical record');
  expect(trigger.classList.contains('leave-action')).toBe(true);
  expect(trigger.getAttribute('aria-label')).toBe(`Edit historical record for ${row.employee_name}`);
  act(() => trigger.click());
  expect(document.body.querySelector('dialog[open]')).not.toBeNull();
  expect(container.querySelector('form')).toBeNull();
  act(() => [...document.body.querySelectorAll('button')].find(element => element.textContent === 'Cancel').click());
  expect(document.body.querySelector('dialog[open]')).toBeNull();
  expect(api.correctLeaveHistory).not.toHaveBeenCalled();
});

test('HR can explicitly confirm only recorded source entries with a reason', async () => {
  const saved = jest.fn(); api.approveRecordedLeaveHistory.mockResolvedValue({ data: { approved: 1, already_approved: 0 } });
  act(() => root.render(<LeaveHistory rows={[{ ...row, status: 'Recorded' }]} onSaved={saved} />));
  act(() => button('Approve 1 recorded entries').click());
  act(() => {
    const input = document.body.querySelector('[aria-label="Source approval reason"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'HR confirmed source workbook');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => document.body.querySelector('dialog form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.approveRecordedLeaveHistory).toHaveBeenCalledWith({ targets: [{ id: row.id, revision: 1 }], reason: 'HR confirmed source workbook' });
  expect(saved).toHaveBeenCalledTimes(1);
});
