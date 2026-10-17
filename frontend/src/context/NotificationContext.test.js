import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { NotificationProvider, useNotifications } from './NotificationContext';
import { useAuth } from './AuthContext';
import * as api from '../services/api';
jest.mock('./AuthContext'); jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, current;
function Probe() { current = useNotifications(); return <div>{current.unreadCount ?? 'Unknown'} {current.error} {current.items.map(item => item.title).join(' ')}</div>; }
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'one', role: 'employee' } });
  api.getNotificationCentre.mockResolvedValue({ data: { items: [{ id: 'notice', title: 'Own update', is_read: false }], unread_count: 7 } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<NotificationProvider><Probe /></NotificationProvider>)); };
test('shared bell uses the server total, not the limited preview count', async () => { await render(); expect(current.unreadCount).toBe(7); });
test('failed read acknowledgement cannot decrement the badge optimistically', async () => {
  await render(); api.markNotificationRead.mockResolvedValue({ data: null, status: 503 });
  await act(async () => { await expect(current.markRead('notice')).rejects.toThrow(); }); expect(current.unreadCount).toBe(7);
});
test('successful persisted read refreshes the shared count and previews', async () => {
  await render(); api.markNotificationRead.mockResolvedValue({ data: { is_read: true } });
  api.getNotificationCentre.mockResolvedValue({ data: { items: [{ id: 'notice', title: 'Own update', is_read: true }], unread_count: 6 } });
  await act(async () => current.markRead('notice')); expect(current.unreadCount).toBe(6); expect(current.items[0].is_read).toBe(true);
});
test('changing account clears old items while waiting for its inbox', async () => {
  await render(); let resolve; api.getNotificationCentre.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { id: 'two', role: 'employee' } }); await render(); expect(container.textContent).not.toContain('Own update');
  await act(async () => resolve({ data: { items: [], unread_count: 0 } })); expect(current.unreadCount).toBe(0);
});
test('first-login restricted sessions do not fetch protected notifications', async () => {
  useAuth.mockReturnValue({ user: { id: 'one', role: 'employee', must_change_password: true } }); await render(); expect(api.getNotificationCentre).not.toHaveBeenCalled();
});

 test('MFA challenge sessions do not fetch protected notifications', async () => {
  useAuth.mockReturnValue({ user: { id: 'one', role: 'it_admin', mfa_required: true, mfa_verified: false } });
  await render(); expect(api.getNotificationCentre).not.toHaveBeenCalled();
});
