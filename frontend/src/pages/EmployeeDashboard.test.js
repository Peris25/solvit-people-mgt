import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeDashboard from './EmployeeDashboard';
import RoleDashboard from './RoleDashboard';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }));
jest.mock('./Dashboard', () => () => <div>Existing HR dashboard</div>);
jest.mock('./LineManagerDashboard', () => () => <div>Existing team dashboard</div>);
jest.mock('./SolverDashboard', () => () => <div>Existing Solver dashboard</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const user = { id: 'account', employee_id: 'staff', full_name: 'Account name', role: 'employee' };
const home = () => ({
  employee: { id: 'staff', full_name: 'Synthetic Ada', role_title: 'IT Lead', department: 'IT Support' },
  leave_balance: { annual_days_remaining: 0, sick_days_remaining: 12 }, pending_leave: [],
  tasks: [], notifications: [], unread_notifications: 0, reviews: [], recognitions: [],
  quick_links: [{ label: 'My Profile', path: '/employees/staff' }, { label: 'Leave', path: '/leave' }, { label: 'Documents & policies', path: '/policies' }],
});
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user }); api.getStaffHome.mockResolvedValue({ data: home() });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async element => { await act(async () => root.render(element || <EmployeeDashboard />)); };
const click = async text => {
  const button = [...container.querySelectorAll('button')].find(b => b.textContent === text);
  expect(button).toBeTruthy(); await act(async () => button.click());
};

test('personalized employee welcome, real zero balance and authorized quick links', async () => {
  await render();
  expect(container.textContent).toContain('Synthetic Ada');
  expect(container.textContent).toContain('IT Lead · IT Support');
  expect(container.querySelector('[data-testid="my-leave-zone"]').textContent).toContain('0');
  await click('My Profile'); expect(mockNavigate).toHaveBeenCalledWith('/employees/staff');
  await click('Documents & policies'); expect(mockNavigate).toHaveBeenCalledWith('/policies');
  await click('Open Notification Centre'); expect(mockNavigate).toHaveBeenCalledWith('/notifications');
  expect(api.getStaffHome).toHaveBeenCalledWith();
  expect(api.getRecognitions).not.toHaveBeenCalled();
});

test('pending requests, due actions and existing notifications render without private payloads', async () => {
  const data = home();
  data.pending_leave = [{ id: 'leave', leave_type: 'Annual', start_date: '2026-10-20', end_date: '2026-10-22', status: 'Pending_HR', medical_notes: 'restricted' }];
  data.tasks = [{ id: 'form', kind: 'form', form_title: 'Sign your form', due_date: '2026-01-01' }];
  data.notifications = [{ id: 'notice', title: 'Your update', message: '<script>unsafe()</script>', is_read: false, bank_account: 'restricted' }];
  data.unread_notifications = 1;
  api.getStaffHome.mockResolvedValue({ data }); await render();
  expect(container.textContent).toContain('1 awaiting approval');
  expect(container.textContent).toContain('Sign your form');
  expect(container.textContent).toContain('1 unread');
  expect(container.textContent).not.toContain('restricted');
  expect(container.querySelector('script')).toBeNull();
});

test('missing data produces empty states without invented balances, announcements or tasks', async () => {
  const data = home(); data.leave_balance = null;
  api.getStaffHome.mockResolvedValue({ data }); await render();
  expect(container.textContent).toContain('Leave balance not available');
  expect(container.textContent).toContain('No pending leave requests');
  expect(container.textContent).toContain('No notifications yet');
  expect(container.querySelector('[data-testid="emp-no-tasks"]')).toBeTruthy();
});

test('server denial or swallowed server error shows an error, never false all-caught-up', async () => {
  api.getStaffHome.mockResolvedValue({ data: null, status: 503 }); await render();
  expect(container.querySelector('[role="alert"]').textContent).toContain('unavailable');
  expect(container.querySelector('[data-testid="emp-no-tasks"]')).toBeNull();
});

test('revoked module links and tabs are absent', async () => {
  const data = home(); data.quick_links = []; data.pending_leave = null; data.reviews = null; data.recognitions = null;
  api.getStaffHome.mockResolvedValue({ data }); await render();
  expect(container.textContent).not.toContain('Documents & policies');
  expect(container.querySelector('[data-testid="emp-request-leave-btn"]')).toBeNull();
  expect(container.querySelector('[data-testid="emp-tab-reviews"]')).toBeNull();
});

test('switching accounts clears prior employee data while loading the next account', async () => {
  await render(); let resolve;
  api.getStaffHome.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { ...user, id: 'second', full_name: 'Second account' } });
  await render(); expect(container.textContent).not.toContain('Synthetic Ada');
  await act(async () => resolve({ data: { ...home(), employee: { id: 'second', full_name: 'Synthetic Ben' } } }));
  expect(container.textContent).toContain('Synthetic Ben');
});

test('linked managers get Staff Home first and retain their team dashboard', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'line_manager' } }); await render(<RoleDashboard />);
  expect(container.textContent).toContain('Synthetic Ada');
  await click('My Team'); expect(container.textContent).toContain('Existing team dashboard');
});

test('unlinked HR and Solver accounts retain their existing dashboards', async () => {
  useAuth.mockReturnValue({ user: { id: 'hr', role: 'hr_admin' } }); await render(<RoleDashboard />);
  expect(container.textContent).toContain('Existing HR dashboard');
  useAuth.mockReturnValue({ user: { id: 'solver', role: 'solver' } }); await render(<RoleDashboard />);
  expect(container.textContent).toContain('Existing Solver dashboard');
});
