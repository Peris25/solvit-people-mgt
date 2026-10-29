import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Sidebar from './Sidebar';
import EmployeeLoginReview from './EmployeeLoginReview';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../context/AuthContext');
jest.mock('../services/api');
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn(), useLocation: () => ({ pathname: '/dashboard' }) }));
jest.mock('../context/NotificationContext', () => ({ useNotifications: () => ({ items: [], unreadCount: 0 }) }));
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ theme: 'light', toggle: jest.fn() }), themeTokens: () => ({}) }));

global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'staff', role: 'employee', full_name: 'Synthetic', department: 'Finance' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async element => { await act(async () => root.render(element)); };

test('FTE navigation includes authorized self-service and colleague information, without HR administration', async () => {
  await render(<Sidebar collapsed={false} onToggle={jest.fn()} />);
  for (const route of ['dashboard', 'my-profile', 'documents', 'benefits', 'leave', 'performance', 'lnd', 'policies', 'recognition', 'surveys', 'staff-directory', 'organogram', 'forms', 'my-tasks', 'onboarding', 'projects', 'notifications', 'account-security']) {
    expect(container.querySelector(`[data-testid="nav-${route}"]`)).not.toBeNull();
  }
  for (const route of ['employees', 'roles-permissions', 'data-import', 'compensation', 'reporting', 'retention', 'masters']) {
    expect(container.querySelector(`[data-testid="nav-${route}"]`)).toBeNull();
  }
});

test('ordinary employees cannot open account review or invoke its API', async () => {
  await render(<EmployeeLoginReview />);
  expect(container.textContent).toBe(''); expect(api.getEmployeeLoginReview).not.toHaveBeenCalled();
});

test.each(['it_admin', 'hr_admin'])('%s can identify missing accounts without creating accounts or changing roles', async role => {
  useAuth.mockReturnValue({ user: { id: 'actor', role } });
  api.getEmployeeLoginReview.mockResolvedValue({ data: [{ record_id: 'one', employee_id: 'one', full_name: 'Synthetic FTE', status: 'Needs review', issues: ['No login account found'] }] });
  await render(<EmployeeLoginReview />);
  await act(async () => container.querySelector('button').click());
  expect(container.textContent).toContain('No login account found');
  expect(container.textContent).toContain('1 employee records checked; 1 need review');
  expect(api.provisionEmployeeAccount).not.toHaveBeenCalled();
  expect(api.updateUserRole).not.toHaveBeenCalled();
});

test('review errors are retryable and account switching hides previous employee data', async () => {
  useAuth.mockReturnValue({ user: { id: 'it', role: 'it_admin' } });
  api.getEmployeeLoginReview.mockRejectedValueOnce(new Error('private details')).mockResolvedValueOnce({ data: [{ record_id: 'one', full_name: 'Prior private record', status: 'Linked', issues: [] }] });
  await render(<EmployeeLoginReview />);
  await act(async () => container.querySelector('button').click());
  expect(container.querySelector('[role="alert"]').textContent).toContain('Please retry');
  expect(container.textContent).not.toContain('private details');
  await act(async () => container.querySelector('button').click());
  expect(container.textContent).toContain('Prior private record');
  useAuth.mockReturnValue({ user: { id: 'it', role: 'hr_admin' } });
  await render(<EmployeeLoginReview />);
  expect(container.textContent).not.toContain('Prior private record');
  useAuth.mockReturnValue({ user: { id: 'another', role: 'it_admin' } });
  await render(<EmployeeLoginReview />);
  expect(container.textContent).not.toContain('Prior private record');
});

test('HR can prepare only unambiguous missing accounts and must confirm creation separately', async () => {
  useAuth.mockReturnValue({ user: { id: 'hr', role: 'hr_admin' } });
  const onPrepare = jest.fn();
  api.getEmployeeLoginReview.mockResolvedValue({ data: [
    { record_id: 'one', employee_id: 'one', full_name: 'Example One', work_email: 'one@example.test', status: 'Needs review', issues: ['No login account found'] },
    { record_id: 'two', employee_id: 'two', status: 'Needs review', issues: ['No login account found', 'Employee identifier is duplicated'] },
    { record_id: 'three', employee_id: 'three', status: 'Linked', issues: [] },
  ] });
  await render(<EmployeeLoginReview onPrepareAccounts={onPrepare} />);
  await act(async () => container.querySelector('button').click());
  const prepare = [...container.querySelectorAll('button')].find(button => button.textContent === 'Prepare 1 missing employee accounts');
  await act(async () => prepare.click());
  expect(onPrepare).toHaveBeenCalledWith([{ id: 'one', full_name: 'Example One', work_email: 'one@example.test' }]);
  expect(api.provisionEmployeeAccount).not.toHaveBeenCalled();
});
