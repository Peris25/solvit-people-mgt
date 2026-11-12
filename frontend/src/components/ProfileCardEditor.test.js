import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ProfileCardEditor from './ProfileCardEditor';
import * as api from '../services/api';

jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, saved;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); saved = jest.fn(); api.updateEmployee.mockResolvedValue({ data: {} }); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const open = async (section, employee = {}, role = 'hr_admin') => {
  await act(async () => root.render(<ProfileCardEditor employee={{ id: 'staff', full_name: 'Synthetic staff', ...employee }} section={section} user={{ role }} onSaved={saved} />));
  await act(async () => container.querySelector('button').click());
};
const change = async (label, value) => act(async () => {
  const input = container.querySelector(`[aria-label="${label}"]`);
  const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});
const submit = async () => act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));

test('bank modal preserves leading zeroes and submits only corrected bank fields', async () => {
  await open('bank', { bank_account: '00123', preferred_payment_method: 'M-Pesa' });
  expect(container.querySelector('[aria-label="Bank account number"]').value).toBe('00123');
  expect(container.querySelector('[aria-label="Payment method"]').value).toBe('M-Pesa');
  await change('Bank account number', '00009876'); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { bank_account_number: '00009876' });
  expect(saved).toHaveBeenCalledWith({ bank_account_number: '00009876' });
  expect(container.querySelector('dialog')).toBeNull();
});

test('contacts modal edits structured contact fields while preserving the other contact values', async () => {
  await open('contacts', { next_of_kin: { name: 'Synthetic contact', relationship: 'Sibling' } });
  await change('Next of kin phone number', '+254700000001'); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { next_of_kin: { name: 'Synthetic contact', relationship: 'Sibling', phone_number: '+254700000001' } });
});

test('education rows retain numeric legacy year and can be edited without exposing JSON', async () => {
  await open('contacts', { education: [{ institution: 'Synthetic college', qualification: 'Diploma', year: 2020 }] });
  expect(container.querySelector('[aria-label="Education 1 year"]').value).toBe('2020');
  await change('Education 1 qualification', 'Degree'); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { education: [{ institution: 'Synthetic college', qualification: 'Degree', year: '2020' }] });
});

test('HR manager can edit employment but lifecycle stays under existing admin controls', async () => {
  await open('employment', { employee_number: 'Legacy ID', lifecycle_state: 'Active' }, 'hr_manager');
  expect(container.querySelector('[aria-label="Lifecycle"]').disabled).toBe(true);
  expect(container.querySelector('[aria-label="Staff ID"]').value).toBe('Legacy ID');
  await change('Staff ID', 'S001'); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { staff_id: 'S001' });
});

test('unchanged modal closes without writing or clearing missing fields', async () => {
  await open('contacts'); await submit();
  expect(api.updateEmployee).not.toHaveBeenCalled();
  expect(container.querySelector('dialog')).toBeNull();
});
