import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EligibleSolvers from './EligibleSolvers';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
const stages = ['Eligible', 'Interviewing', 'Awaiting assessment', 'Passed', 'Awaiting confirmation', 'Active'];
const row = { id: 'candidate', full_name: 'Synthetic Applicant', email: 'candidate@example.com', phone_number: '0712345678', recruitment_stage: 'Eligible', edit_version: 'a'.repeat(64), can_edit: true, can_confirm: true };
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.listEligibleSolvers.mockResolvedValue({ data: { rows: [row], stages } });
  api.listSolverRequisitions.mockResolvedValue({ data: { requisitions: [] } });
  api.getEligibleSolver.mockResolvedValue({ data: row });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<EligibleSolvers />)); };
const click = async text => { const button = [...container.querySelectorAll('button')].find(b => b.textContent === text); expect(button).toBeTruthy(); await act(async () => button.click()); };
const change = async (field, value) => { await act(async () => { Object.getOwnPropertyDescriptor(field.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLTextAreaElement.prototype, 'value').set.call(field, value); field.dispatchEvent(new Event('change', { bubbles: true })); field.dispatchEvent(new Event('input', { bubbles: true })); }); };

test('eligible rows have a visible Edit button and supported stage options', async () => {
  await render(); await click('Edit');
  expect(container.querySelector('[role="dialog"]')).toBeTruthy();
  const select = container.querySelector('[aria-label="Recruitment stage"]');
  expect(select.textContent).toContain('Interviewing');
  expect(select.textContent).toContain('Awaiting assessment');
  expect(api.updateEligibleSolver).not.toHaveBeenCalled();
});
test('saving stage sends the checked version and reason, then refreshes the list', async () => {
  await render(); await click('Edit');
  await change(container.querySelector('[aria-label="Recruitment stage"]'), 'Interviewing');
  await change(container.querySelector('textarea'), 'HR scheduled the applicant interview');
  api.updateEligibleSolver.mockResolvedValue({ data: { ...row, recruitment_stage: 'Interviewing' } });
  await act(async () => container.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.updateEligibleSolver).toHaveBeenCalledWith('candidate', expect.objectContaining({ stage: 'Interviewing', expected_version: row.edit_version, reason: 'HR scheduled the applicant interview' }));
  expect(container.querySelector('[role="dialog"]')).toBeNull();
});
test('Active requires a visible HR confirmation and does not automatically create a login', async () => {
  await render(); await click('Edit');
  await change(container.querySelector('[aria-label="Recruitment stage"]'), 'Active');
  expect(container.querySelector('input[type="checkbox"]').required).toBe(true);
  expect(container.textContent).toContain('does not create a login account');
});
test('non-HR editors do not receive the Active confirmation option', async () => {
  api.getEligibleSolver.mockResolvedValue({ data: { ...row, can_confirm: false } });
  await render(); await click('Edit');
  expect([...container.querySelector('[aria-label="Recruitment stage"]').options].map(o => o.value)).not.toContain('Active');
});
test('stale record rejection keeps the editor open', async () => {
  await render(); await click('Edit');
  api.updateEligibleSolver.mockRejectedValue({ response: { data: { detail: 'Applicant changed. Reopen before saving.' } } });
  await act(async () => container.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Applicant changed');
  expect(container.querySelector('[role="dialog"]')).toBeTruthy();
});
test('read-only applicant rows cannot open an editor', async () => {
  api.listEligibleSolvers.mockResolvedValue({ data: { rows: [{ ...row, can_edit: false }], stages } });
  await render(); expect([...container.querySelectorAll('button')].some(b => b.textContent === 'Edit')).toBe(false);
});
