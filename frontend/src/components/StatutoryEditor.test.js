import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import StatutoryEditor from './StatutoryEditor';
import * as api from '../services/api';

jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, onSaved;
const employee = { id: 'staff', national_id_number: '00123', gender: 'Female' };
beforeEach(async () => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  onSaved = jest.fn();
  await act(async () => root.render(<StatutoryEditor employee={employee} onSaved={onSaved} />));
  await act(async () => container.querySelector('button').click());
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const change = async (label, value) => act(async () => {
  const input = container.querySelector(`[aria-label="${label}"]`);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
});
const submit = async () => act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));

test('sends only changed values for the selected employee and shows saved confirmation', async () => {
  api.updateEmployee.mockResolvedValue({ data: { ...employee, sha_number: 'SHA-001' } });
  expect(container.querySelector('[aria-label="National ID"]').value).toBe('00123');
  await change('SHA', 'SHA-001'); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { sha_number: 'SHA-001' });
  expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ sha_number: 'SHA-001' }));
  expect(container.textContent).toContain('Statutory information saved.');
});

test('failed save retains entered data and shows server error', async () => {
  api.updateEmployee.mockRejectedValue({ response: { data: { detail: 'Date of birth cannot be in the future' } } });
  await change('Date of birth', '2999-01-01'); await submit();
  expect(container.querySelector('[role="alert"]').textContent).toContain('cannot be in the future');
  expect(container.querySelector('[aria-label="Date of birth"]').value).toBe('2999-01-01');
  expect(onSaved).not.toHaveBeenCalled();
});

test('cancel discards edits without saving', async () => {
  await change('National ID', 'changed');
  await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === 'Cancel').click());
  expect(api.updateEmployee).not.toHaveBeenCalled();
  await act(async () => container.querySelector('button').click());
  expect(container.querySelector('[aria-label="National ID"]').value).toBe('00123');
});

test('clearing a field sends an explicit empty value', async () => {
  api.updateEmployee.mockResolvedValue({ data: { national_id_number: '' } });
  await change('National ID', ''); await submit();
  expect(api.updateEmployee).toHaveBeenCalledWith('staff', { national_id_number: '' });
});
