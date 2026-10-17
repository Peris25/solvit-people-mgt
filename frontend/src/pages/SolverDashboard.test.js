import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SolverDashboard from './SolverDashboard';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ Link: ({ to, children }) => <a href={to}>{children}</a> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'one', role: 'solver', full_name: 'Synthetic Solver' } });
  api.getMyFormTasks.mockResolvedValue({ data: [] }); api.getRecognitions.mockResolvedValue({ data: [] }); api.getSurveyWindows.mockResolvedValue({ data: [] });
  api.getMySolver.mockResolvedValue({ data: { id: 'solver-one', full_name: 'Synthetic Solver' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<SolverDashboard />)); };

test('missing scores and tier are not fabricated from defaults', async () => {
  await render(); expect(container.textContent).toContain('Not recorded');
  expect(container.textContent).not.toContain('Standard');
  expect(container.querySelector('a[href="/notifications"]')).toBeTruthy();
  expect(container.querySelector('a[href="/solvers"]')).toBeTruthy();
});

test('own saved Solver metrics replace token fields and preserve zero', async () => {
  useAuth.mockReturnValue({ user: { id: 'one', role: 'solver', accuracy_score: 99 } });
  api.getMySolver.mockResolvedValue({ data: { accuracy_score: 0, client_rating_average: 4.2, performance_tier: 'Elite' } });
  await render(); expect(container.textContent).toContain('Elite'); expect(container.textContent).toContain('4.2'); expect(container.textContent).not.toContain('99');
});

test('failed profile load produces an error without plausible performance defaults', async () => {
  api.getMySolver.mockRejectedValue(new Error('offline')); await render();
  expect(container.querySelector('[role="alert"]')).toBeTruthy(); expect(container.textContent).not.toContain('Standard');
});
