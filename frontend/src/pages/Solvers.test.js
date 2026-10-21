import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Solvers from './Solvers';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../components/SolverWorkflow', () => () => <div>Solver workflow</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getSolvers.mockResolvedValue({ data: [] });
  api.getSolverDirectoryOptions.mockResolvedValue({ data: { regions: [], categories: [] } });
  useAuth.mockReturnValue({ user: { id: 'synthetic', role: 'hr_admin' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<Solvers />)); };

test('registration controls use server-qualified management permission', async () => {
  api.getSolverStats.mockResolvedValue({ data: { total: 0, by_state: {}, active: 0, can_manage: true } });
  await render(); expect(container.textContent).toContain('Register Solver');
});

test('self/aggregate/read-only views do not show Solver write controls', async () => {
  api.getSolverStats.mockResolvedValue({ data: { total: 0, by_state: {}, active: 0, can_manage: false } });
  await render(); expect(container.textContent).not.toContain('Register Solver');
});

test('server permission denial gives a safe error instead of rendering stale Solver records', async () => {
  api.getSolvers.mockResolvedValue({ data: null, error: 'No access to this Solver operation' });
  api.getSolverStats.mockResolvedValue({ data: null });
  await render();
  expect(container.querySelector('[role="alert"]').textContent).toContain('No access');
  expect(container.textContent).not.toContain('Register Solver');
});

const change = async (input, value) => { await act(async () => {
  Object.getOwnPropertyDescriptor(input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value);
  input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true }));
}); };

test('search, region, category and status filters reach the server', async () => {
  api.getSolverStats.mockResolvedValue({ data: { can_manage: false } });
  api.getSolverDirectoryOptions.mockResolvedValue({ data: { regions: ['Coast'], categories: ['SUV'] } });
  await render();
  await change(container.querySelector('[data-testid="search-solvers"]'), 'Synthetic');
  await change(container.querySelector('[aria-label="Filter Solver region"]'), 'Coast');
  await change(container.querySelector('[aria-label="Filter Solver category"]'), 'SUV');
  await change(container.querySelector('[data-testid="filter-solver-state"]'), 'Active');
  expect(api.getSolvers).toHaveBeenLastCalledWith({ search: 'Synthetic', region: 'Coast', category: 'SUV', lifecycle_state: 'Active' });
});

test('directory-only profile cannot open assessment or HR workflow controls', async () => {
  api.getSolverStats.mockResolvedValue({ data: { can_manage: false, directory_only: true } });
  api.getSolvers.mockResolvedValue({ data: [{ id: 'one', full_name: 'Synthetic Solver', region: 'Coast', phone_number: 'work-contact' }] });
  await render(); await act(async () => container.querySelector('[data-testid="view-solver-one"]').click());
  expect(container.textContent).toContain('work-contact');
  expect(container.textContent).not.toContain('Solver workflow');
  expect(container.textContent).not.toContain('Register Solver');
});

test('zero scores remain visible and no invented 5-point rating scale is appended', async () => {
  api.getSolverStats.mockResolvedValue({ data: { can_manage: false } });
  api.getSolvers.mockResolvedValue({ data: [{ id: 'one', full_name: 'Synthetic', accuracy_score: 0, reliability_score: 0, client_rating_average: 85 }] });
  await render(); expect(container.textContent).toContain('0%'); expect(container.textContent).not.toContain('/5.0');
});

test('an account switch hides the prior response while the next account loads', async () => {
  api.getSolverStats.mockResolvedValue({ data: { can_manage: true } });
  api.getSolvers.mockResolvedValueOnce({ data: [{ id: 'one', full_name: 'Private prior record' }] });
  await render(); expect(container.textContent).toContain('Private prior record');
  api.getSolvers.mockReturnValue(new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'other-account', role: 'employee' } }); await render();
  expect(container.textContent).not.toContain('Private prior record'); expect(container.textContent).not.toContain('Register Solver');
});

const statusFixture = async (role = 'hr_admin', canManage = true) => {
  useAuth.mockReturnValue({ user: { id: 'synthetic', role } });
  api.getSolverStats.mockResolvedValue({ data: { can_manage: canManage } });
  api.getSolvers.mockResolvedValue({ data: [{ id: 'one', full_name: 'Synthetic Solver', lifecycle_state: 'Active' }] });
  await render();
};

test('HR changes status using only the existing authorized update endpoint', async () => {
  await statusFixture();
  api.updateSolver.mockResolvedValue({ data: {} });
  await act(async () => container.querySelector('[data-testid="edit-solver-one"]').click());
  expect(container.querySelector('#solver-status').value).toBe('Active');
  await change(container.querySelector('#solver-status'), 'Inactive');
  await act(async () => container.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.updateSolver).toHaveBeenCalledWith('one', { lifecycle_state: 'Inactive' });
  expect(container.querySelector('[role="dialog"]')).toBeNull();
});

test.each(['employee', 'solver', 'solvers_manager', 'finance', 'it_admin'])('%s cannot see HR status editor', async role => {
  await statusFixture(role);
  expect(container.querySelector('[data-testid="edit-solver-one"]')).toBeNull();
});

test('HR with revoked management permission cannot edit status', async () => {
  await statusFixture('hr_admin', false);
  expect(container.querySelector('[data-testid="edit-solver-one"]')).toBeNull();
});

test('saving unchanged status does not write a record', async () => {
  await statusFixture('hr_manager');
  await act(async () => container.querySelector('[data-testid="edit-solver-one"]').click());
  await act(async () => container.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.updateSolver).not.toHaveBeenCalled();
});

test('status errors remain visible and reactivation cannot bypass verification', async () => {
  await statusFixture();
  api.updateSolver.mockRejectedValue({ response: { data: { detail: 'Status update denied' } } });
  await act(async () => container.querySelector('[data-testid="edit-solver-one"]').click());
  await change(container.querySelector('#solver-status'), 'Suspended');
  await act(async () => container.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.querySelector('[role="alert"]').textContent).toBe('Status update denied');
  expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  api.getSolvers.mockResolvedValue({ data: [{ id: 'one', full_name: 'Synthetic Solver', lifecycle_state: 'Inactive' }] });
  await act(async () => Array.from(container.querySelectorAll('button')).find(b => b.textContent === 'Cancel').click());
  await change(container.querySelector('[data-testid="search-solvers"]'), 'Synthetic');
  await act(async () => container.querySelector('[data-testid="edit-solver-one"]').click());
  expect(container.querySelector('#solver-status option[value="Active"]').disabled).toBe(true);
});
