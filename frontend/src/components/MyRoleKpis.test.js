import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import MyRoleKpis from './MyRoleKpis';
import { getMyRoleKpis } from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<MyRoleKpis />)); };

test('shows assigned KPIs and Week 3 guidance without assessment editing controls', async () => {
  getMyRoleKpis.mockResolvedValue({ data: { name: 'Synthetic role', goals: [{ id: 'quality', objective: 'Quality', metric: 'Verified report', target: '95%', weight: 100 }] } });
  await render();
  expect(container.textContent).toContain('Synthetic role');
  expect(container.textContent).toContain('95%');
  expect(container.textContent).toContain('Week 3');
  expect(container.querySelectorAll('input,textarea,select')).toHaveLength(0);
});

test('missing approved KPIs show an honest empty state', async () => {
  getMyRoleKpis.mockResolvedValue({ data: null }); await render();
  expect(container.textContent).toContain('HR has not assigned approved role KPIs yet');
  expect(container.querySelector('table')).toBeNull();
});

test('failed loading can retry without leaving stale data', async () => {
  getMyRoleKpis.mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce({ data: null });
  await render(); expect(container.querySelector('[role="alert"]')).not.toBeNull();
  await act(async () => container.querySelector('button').click());
  expect(getMyRoleKpis).toHaveBeenCalledTimes(2);
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

test('loading state is present while request is pending', async () => {
  getMyRoleKpis.mockReturnValue(new Promise(() => {})); await render();
  expect(container.querySelector('[role="status"]').textContent).toContain('Loading');
});
