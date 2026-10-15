import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Notifications from './Notifications';
import { useAuth } from '../context/AuthContext';
import { useNotifications } from '../context/NotificationContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../context/NotificationContext');
jest.mock('react-router-dom', () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const inbox = items => ({ items, unread_count: items.filter(item => !item.is_read).length, total: items.length, filtered_total: items.length, categories: ['Leave', 'Training'], offset: 0, limit: 20 });
const item = (id = 'one', values = {}) => ({ id, title: 'Leave update', message: 'There is an update about a leave request.', category: 'Leave', kind: 'Updates', sender: 'System', is_read: false, created_at: new Date().toISOString(), link: '/leave?request=record', ...values });
const markRead = jest.fn(), refresh = jest.fn();
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'staff-account', role: 'employee' } });
  useNotifications.mockReturnValue({ markRead, refresh }); markRead.mockResolvedValue(undefined);
  api.getNotificationCentre.mockResolvedValue({ data: inbox([item()]) });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<Notifications />)); };
const click = async label => { const button = [...container.querySelectorAll('button')].find(node => node.textContent === label); expect(button).toBeTruthy(); await act(async () => button.click()); };

test('central inbox shows unread count, Today/Earlier groups and safe related links', async () => {
  api.getNotificationCentre.mockResolvedValue({ data: inbox([item(), item('older', { created_at: '2020-01-01', is_read: true })]) });
  await render(); expect(container.textContent).toContain('1 unread');
  expect(container.querySelector('[aria-label="Today"]')).toBeTruthy(); expect(container.querySelector('[aria-label="Earlier"]')).toBeTruthy();
  expect(container.querySelector('a[href="/leave?request=record"]')).toBeTruthy();
});

test('marking read persists through the API-backed context and reloads the inbox', async () => {
  await render(); api.getNotificationCentre.mockResolvedValue({ data: inbox([item('one', { is_read: true })]) });
  await click('Mark as read'); expect(markRead).toHaveBeenCalledWith('one'); expect(container.textContent).toContain('0 unread');
});

test('failed marking read remains unread and displays a useful error', async () => {
  await render(); markRead.mockRejectedValueOnce(new Error('failed')); await click('Mark as read');
  expect(container.querySelector('[role="alert"]').textContent).toContain('could not be marked');
  expect(container.textContent).toContain('1 unread');
});

test('category and unread filters are sent to the server, not applied to private unfiltered data', async () => {
  await render();
  await act(async () => { const select = container.querySelector('[aria-label="Notification category"]'); select.value = 'Training'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => { const select = container.querySelector('[aria-label="Notification status"]'); select.value = 'unread'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(api.getNotificationCentre).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'Training', read_status: 'unread', offset: 0 }));
});

test('external URLs are not linked and preview text cannot render scripts', async () => {
  api.getNotificationCentre.mockResolvedValue({ data: inbox([item('one', { link: 'javascript:alert(1)', message: '<script>unsafe()</script>' })]) });
  await render(); expect(container.querySelector('script')).toBeNull(); expect(container.querySelector('a')).toBeNull();
});

test('empty, loading and server error states are distinct', async () => {
  api.getNotificationCentre.mockResolvedValue({ data: inbox([]) }); await render(); expect(container.textContent).toContain('No notifications yet');
  api.getNotificationCentre.mockResolvedValue({ data: null, status: 503 }); await click('Refresh'); expect(container.querySelector('[role="alert"]')).toBeTruthy();
  let resolve; api.getNotificationCentre.mockReturnValue(new Promise(r => { resolve = r; }));
  await click('Retry'); expect(container.querySelector('[role="status"]')).toBeTruthy();
  await act(async () => resolve({ data: inbox([]) }));
});

test('switching accounts clears old preview data immediately while the new inbox loads', async () => {
  await render(); let resolve; api.getNotificationCentre.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { id: 'other-account', role: 'employee' } }); await render();
  expect(container.textContent).not.toContain('Leave update');
  await act(async () => resolve({ data: inbox([]) })); expect(container.textContent).toContain('No notifications yet');
});

test('server-authorized approval reuses the existing decision endpoint and records read receipt', async () => {
  api.getNotificationCentre.mockResolvedValue({ data: inbox([item('approval', { action: { kind: 'leave', record_id: 'authorized-record' } })]) });
  api.leaveDecision.mockResolvedValue({ data: { status: 'Approved' } }); await render(); await click('Approve');
  expect(api.leaveDecision).toHaveBeenCalledWith('authorized-record', { decision: 'Approve' }); expect(markRead).toHaveBeenCalledWith('approval');
});

test('pagination requests a fresh authorized page', async () => {
  api.getNotificationCentre.mockResolvedValue({ data: { ...inbox([item()]), total: 21, filtered_total: 21 } }); await render(); await click('Next');
  expect(api.getNotificationCentre).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20, limit: 20 }));
});
