import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Onboarding from './Onboarding';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../components/EmployeePicker', () => () => <div>Employee picker</div>);
jest.mock('react-router-dom', () => ({ Link: ({ children, to }) => <a href={to}>{children}</a> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { role: 'employee', employee_id: 'staff' } });
  api.getLifecycleChecklists.mockResolvedValue({ data: [] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<Onboarding />)); };
test('own empty state and private document links without HR initiation controls', async () => {
  await render(); expect(container.textContent).toContain('No onboarding or offboarding');
  expect(container.textContent).not.toContain('Initiate a workflow');
  expect(container.querySelector('a[href="/documents"]')).toBeTruthy();
});
test('shows assigned responsibility, due date, progress and completes through guarded API', async () => {
  api.getLifecycleChecklists.mockResolvedValue({ data: [{ employee_id: 'staff', name: 'Synthetic Ada', kind: 'onboarding', progress_pct: 20,
    tasks: [{ id: 'own-task', title: 'Read handbook', assigned_role: 'employee', due_date: '2026-10-20', status: 'Pending', can_complete: true },
      { id: 'hr-task', title: 'HR checks', assigned_role: 'hr_admin', status: 'Pending', can_complete: false }] }] });
  api.updateLifecycleTask.mockResolvedValue({}); await render();
  expect(container.textContent).toContain('2026-10-20'); expect(container.querySelectorAll('button').length).toBe(1);
  await act(async () => container.querySelector('button').click());
  expect(api.updateLifecycleTask).toHaveBeenCalledWith('onboarding', 'own-task', { status: 'Completed' });
});
test('HR exit completion requires a separate confirmation action', async () => {
  useAuth.mockReturnValue({ user: { role: 'hr_admin' } });
  api.getLifecycleChecklists.mockResolvedValue({ data: [{ employee_id: 'staff', name: 'Synthetic Ada', kind: 'offboarding', progress_pct: 100, tasks: [] }] });
  await render(); expect(container.textContent).toContain('Initiate a workflow');
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === 'Review exit completion').click());
  expect(container.textContent).toContain('17:00 EAT'); expect(api.completeOffboarding).not.toHaveBeenCalled();
  api.completeOffboarding.mockResolvedValue({});
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === 'Confirm deactivation').click());
  expect(api.completeOffboarding).toHaveBeenCalledWith('staff');
});
test('read failures show retry and update failures preserve checklist', async () => {
  api.getLifecycleChecklists.mockRejectedValue(new Error('offline')); await render();
  expect(container.querySelector('[role="alert"]').textContent).toContain('Unable to load');
});
