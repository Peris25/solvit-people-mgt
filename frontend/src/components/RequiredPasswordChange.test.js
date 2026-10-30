import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Layout from './Layout';
import { useAuth } from '../context/AuthContext';

jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('react-router-dom', () => ({
  Outlet: () => <div data-testid="private-outlet">Private application</div>,
  Navigate: () => <div>Sign in</div>,
}));
jest.mock('./Sidebar', () => () => <div data-testid="sidebar" />);
jest.mock('./AIAgent', () => () => <div />);
jest.mock('./FirstLoginTour', () => () => <div data-testid="tour" />);

global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, changePassword, logout;
beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  changePassword = jest.fn().mockResolvedValue({ message: 'Password updated' });
  logout = jest.fn();
  useAuth.mockReturnValue({ user: { role: 'employee', must_change_password: true }, changePassword, logout });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

const render = async () => act(async () => root.render(<Layout />));
const fill = async (confirmation = 'Updated-local-test-password-2026') => act(async () => {
  const values = ['Original-local-test-password-2026', 'Updated-local-test-password-2026', confirmation];
  container.querySelectorAll('input').forEach((input, index) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, values[index]);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
});
const submit = async () => act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));

test.each(['employee', 'hr_admin', 'it_admin', 'solver'])('restricted %s sees only password recovery and sign out', async role => {
  useAuth.mockReturnValue({ user: { role, must_change_password: true }, changePassword, logout });
  await render();
  expect(container.textContent).toContain('Change your password');
  expect(container.querySelector('[data-testid="private-outlet"]')).toBeNull();
  expect(container.querySelector('[data-testid="sidebar"]')).toBeNull();
  expect(container.querySelector('[data-testid="tour"]')).toBeNull();
  await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === 'Sign out').click());
  expect(logout).toHaveBeenCalledTimes(1);
});

test('normal accounts continue to see the existing layout', async () => {
  useAuth.mockReturnValue({ user: { role: 'employee' }, changePassword, logout });
  await render();
  expect(container.querySelector('[data-testid="private-outlet"]')).not.toBeNull();
  expect(container.querySelector('form')).toBeNull();
});

test('matching passwords submit through the authentication flow', async () => {
  await render();
  await fill();
  await submit();
  expect(changePassword).toHaveBeenCalledWith('Original-local-test-password-2026', 'Updated-local-test-password-2026');
});

test('mismatched confirmation makes no request', async () => {
  await render();
  await fill('Different-local-test-password-2026');
  await submit();
  expect(changePassword).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]').textContent).toContain('do not match');
});

test('server policy rejection leaves the user on the required change screen', async () => {
  changePassword.mockRejectedValue({ response: { data: { detail: 'You cannot reuse a previous password.' } } });
  await render();
  await fill();
  await submit();
  expect(container.querySelector('[role="alert"]').textContent).toContain('cannot reuse');
  expect(container.querySelector('[data-testid="private-outlet"]')).toBeNull();
  expect(logout).not.toHaveBeenCalled();
  expect(container.querySelector('button[type="submit"]').disabled).toBe(false);
});
