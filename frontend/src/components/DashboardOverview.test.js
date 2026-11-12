import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { DashboardAttention, DashboardMetric } from './DashboardOverview';

global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const render = async element => act(async () => root.render(element));

test('zero balance is preserved and a missing metric is not presented as zero', async () => {
  await render(<><DashboardMetric label="Annual leave" value={0} unit="days" /><DashboardMetric label="Tasks" value={null} /></>);
  expect(container.querySelectorAll('.dashboard-metric-value')[0].textContent).toBe('0days');
  expect(container.querySelectorAll('.dashboard-metric-value')[1].textContent).toBe('—');
});

test('pending actions expose their real count and open the assigned destination', async () => {
  const open = jest.fn();
  await render(<DashboardAttention items={[{ key: 'approval', label: 'Leave approvals', count: 2, detail: 'Awaiting your decision', onClick: open }, { key: 'tasks', label: 'Tasks', count: 0 }]} />);
  expect(container.textContent).toContain('Leave approvals');
  expect(container.querySelector('.dashboard-action-count').textContent).toBe('2');
  expect(container.querySelectorAll('.dashboard-attention-row').length).toBe(1);
  await act(async () => container.querySelector('button').click());
  expect(open).toHaveBeenCalledTimes(1);
});

test('unavailable actions cannot show an all-clear success or invoke an action', async () => {
  await render(<DashboardAttention items={[{ key: 'approval', label: 'Approvals', count: null, onClick: jest.fn() }]} />);
  expect(container.textContent).toContain('Information unavailable');
  expect(container.textContent).not.toContain('up to date');
  expect(container.querySelector('button')).toBeNull();
});

test('confirmed zero actions use the shared empty state', async () => {
  await render(<DashboardAttention items={[{ key: 'tasks', label: 'Tasks', count: 0 }]} />);
  expect(container.textContent).toContain('You’re up to date');
  expect(container.querySelector('.dashboard-attention-list')).toBeNull();
});
