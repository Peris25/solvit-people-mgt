import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './Dashboard';
import LineManagerDashboard from './LineManagerDashboard';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 'manager', full_name: 'Synthetic manager', role: 'line_manager' } }) }));
const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getKanban.mockResolvedValue({ data: { Active: [], Onboarding: [], Exiting: [], Exited: [] } });
  api.getEmployeeStats.mockResolvedValue({ data: { active: 23, active_solvers: 4, onboarding: 2, open_tasks: 3 } });
  api.getNotifications.mockResolvedValue({ data: [{ id: 'approval', title: 'Leave awaiting review', kind: 'Approvals', is_read: false }] });
  api.getCalendarEvents.mockResolvedValue({ data: [] });
  api.getTalentDensity.mockResolvedValue({ data: { score_pct: 85, target_pct: 85 } });
  api.getVoluntaryAttrition.mockResolvedValue({ data: { pct: 2, target_pct: 10 } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });

test('HR overview places real summary and actionable alerts before employee stages', async () => {
  await act(async () => root.render(<Dashboard />));
  const summary = container.querySelector('[data-testid="quick-stats-bar"]');
  const attention = container.querySelector('[aria-label="Needs attention"]');
  const stages = container.querySelector('[data-testid="kanban-board"]');
  expect(summary.compareDocumentPosition(stages) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(attention.textContent).toContain('Approval alerts');
  expect(attention.querySelector('.dashboard-action-count').textContent).toBe('1');
  await act(async () => attention.querySelector('button').click());
  expect(mockNavigate).toHaveBeenCalledWith('/notifications');
});

test('failed notification data is unavailable rather than an all-clear result', async () => {
  api.getNotifications.mockResolvedValue({ data: null, status: 503 });
  await act(async () => root.render(<Dashboard />));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Alerts');
  expect(container.querySelector('[data-testid="alerts-all-clear"]')).toBeNull();
  expect(container.querySelector('[aria-label="Needs attention"]').textContent).toContain('Information unavailable');
});

test('manager leave action opens the team approval view and hides confirmed zero tasks', async () => {
  api.getLineManagerWidget.mockResolvedValue({ data: { team: [], team_size: 0, pending_leave: 2, open_reviews: 1, my_open_tasks: 0 } });
  await act(async () => root.render(<LineManagerDashboard />));
  const attention = container.querySelector('[aria-label="Needs attention"]');
  expect(attention.querySelectorAll('button').length).toBe(2);
  await act(async () => attention.querySelector('button').click());
  expect(mockNavigate).toHaveBeenCalledWith('/leave?view=team');
});
