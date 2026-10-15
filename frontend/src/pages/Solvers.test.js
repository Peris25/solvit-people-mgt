import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Solvers from './Solvers';
import * as api from '../services/api';

jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getSolvers.mockResolvedValue({ data: [] });
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
