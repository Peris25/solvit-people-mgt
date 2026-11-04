import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OnboardingRegister from './OnboardingRegister';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getOnboardingRegister.mockResolvedValue({ data: [
    { id: 'old', name: 'Synthetic Established', department: 'Operations', employment_status: 'Active', onboarding_status: 'Completed' },
    { id: 'new', name: 'Synthetic New', department: 'IT Support', employment_status: 'Active', onboarding_status: 'In_Progress' },
  ] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<OnboardingRegister onRecorded={jest.fn()} />)); };
test('shows completed and new employees separately without inferring from Active status', async () => {
  await render();
  expect(container.textContent).toContain('Completed: 1');
  const select = container.querySelector('select');
  await act(async () => { select.value = 'In_Progress'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(container.textContent).toContain('Synthetic New');
  expect(container.textContent).not.toContain('Synthetic Established');
  expect(api.recordOnboardingStatus).not.toHaveBeenCalled();
});
test('HR recording requires explicit selection and a confirmation reason', async () => {
  await render();
  expect([...container.querySelectorAll('button')].find(b => b.textContent.includes('Record completed')).disabled).toBe(true);
  await act(async () => container.querySelector('input[aria-label="Select Synthetic New"]').click());
  const field = container.querySelector('textarea');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(field, 'HR confirmed onboarding in progress');
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
  api.recordOnboardingStatus.mockResolvedValue({ data: { recorded: 1 } });
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent.includes('Record onboarding in progress')).click());
  expect(api.recordOnboardingStatus).toHaveBeenCalledWith({ employee_ids: ['new'], status: 'In_Progress', reason: 'HR confirmed onboarding in progress' });
});
test('failed load is visible and never treated as zero completed employees silently', async () => {
  api.getOnboardingRegister.mockRejectedValue(new Error('offline'));
  await render(); expect(container.querySelector('[role="alert"]').textContent).toContain('Unable to load');
});
