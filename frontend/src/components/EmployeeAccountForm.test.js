import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeAccountForm from './EmployeeAccountForm';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('./EmployeePicker', () => ({ onChange, disabled }) => <button type="button" disabled={disabled} data-testid="choose-employee" onClick={() => onChange({ id: 'synthetic-employee' })}>Choose</button>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

test.each([true, false])('provisions an employee account (created %s)', async created => {
  const onSaved = jest.fn();
  api.provisionEmployeeAccount.mockResolvedValue({ data: { id: 'synthetic-user', created } });
  await act(async () => root.render(<EmployeeAccountForm onSaved={onSaved} />));
  expect(container.querySelector('[data-testid="provision-account"]').disabled).toBe(true);
  await act(async () => container.querySelector('[data-testid="choose-employee"]').click());
  const password = container.querySelector('[data-testid="account-initial-password"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(password, 'Synthetic-passphrase');
    password.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.provisionEmployeeAccount).toHaveBeenCalledWith({ employee_id: 'synthetic-employee', initial_password: 'Synthetic-passphrase' });
  expect(password.value).toBe('');
  expect(onSaved).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain(created ? 'Account created' : 'Password and role preserved');
});

test('displays a safe duplicate conflict without resetting or creating another account', async () => {
  api.provisionEmployeeAccount.mockRejectedValue({ response: { data: { detail: 'Employee has conflicting accounts.' } } });
  await act(async () => root.render(<EmployeeAccountForm />));
  await act(async () => container.querySelector('[data-testid="choose-employee"]').click());
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.textContent).toContain('Employee has conflicting accounts.');
  expect(api.provisionEmployeeAccount).toHaveBeenCalledTimes(1);
});

const batchEmployees = [{ id: 'one', full_name: 'Example One', work_email: 'one@example.test' }, { id: 'two', full_name: 'Example Two', work_email: 'two@example.test' }];
const enterInitialPassword = async () => {
  const input = container.querySelector('[data-testid="account-initial-password"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'Synthetic-staff-setup');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

test('batch setup reviews identities, deduplicates selection and clears the single entered password', async () => {
  api.provisionEmployeeAccount.mockResolvedValueOnce({ data: { id: 'user-one', created: true } }).mockResolvedValueOnce({ data: { id: 'user-two', created: false } });
  const onSaved = jest.fn();
  await act(async () => root.render(<EmployeeAccountForm selectedEmployees={[...batchEmployees, batchEmployees[0]]} onSaved={onSaved} />));
  expect(container.textContent).toContain('Review these 2 employees');
  expect(container.textContent).toContain('one@example.test');
  await enterInitialPassword();
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.provisionEmployeeAccount.mock.calls.map(call => call[0].employee_id)).toEqual(['one', 'two']);
  expect(container.textContent).toContain('1 created; 1 linked; 0 need review');
  expect(container.textContent).toContain('Existing password and role preserved');
  expect(container.querySelector('input[type="password"]').value).toBe('');
  expect(onSaved).toHaveBeenCalledTimes(1);
});

test('partial batch conflicts are reported without stopping independent eligible employees', async () => {
  api.provisionEmployeeAccount.mockRejectedValueOnce({ response: { data: { detail: 'IT Admin must manage this account.' } } }).mockResolvedValueOnce({ data: { id: 'two', created: true } });
  await act(async () => root.render(<EmployeeAccountForm selectedEmployees={batchEmployees} />));
  await enterInitialPassword();
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.textContent).toContain('Example One: Needs review');
  expect(container.textContent).toContain('Example Two: Created');
  expect(container.textContent).toContain('1 created; 0 linked; 1 need review');
  expect(container.textContent).not.toContain('Synthetic-staff-setup');
});

test('batch setup stops if the session expires and leaves remaining records unprocessed', async () => {
  api.provisionEmployeeAccount.mockResolvedValue({ status: 401, data: null });
  await act(async () => root.render(<EmployeeAccountForm selectedEmployees={batchEmployees} />));
  await enterInitialPassword();
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.provisionEmployeeAccount).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain('Session expired');
  expect(container.textContent).toContain('2 need review or remain unprocessed');
});
