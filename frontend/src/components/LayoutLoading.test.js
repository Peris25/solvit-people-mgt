import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Layout from './Layout';

let mockSuspend = false;
const mockPending = new Promise(() => {});
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 'staff', role: 'employee', full_name: 'Synthetic staff' } }) }));
jest.mock('../context/NotificationContext', () => ({ useNotifications: () => ({ unreadCount: 0 }) }));
jest.mock('react-router-dom', () => ({
  Outlet: () => { if (mockSuspend) throw mockPending; return <div>Page content</div>; },
  Link: ({ children }) => <span>{children}</span>, Navigate: () => null,
}));
jest.mock('./Sidebar', () => () => <nav>Main navigation</nav>);
jest.mock('./FirstLoginTour', () => () => null);
jest.mock('./RequiredPasswordChange', () => () => null);
jest.mock('../pages/MfaSecurity', () => () => null);
global.IS_REACT_ACT_ENVIRONMENT = true;

test('navigation and workspace header remain visible while a new page bundle loads', async () => {
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<Layout />));
    mockSuspend = true;
    await act(async () => root.render(<Layout />));
    expect(container.textContent).toContain('Main navigation');
    expect(container.textContent).toContain('My workspace');
    expect(container.textContent).toContain('Loading page...');
  } finally { mockSuspend = false; await act(async () => root.unmount()); container.remove(); }
});
