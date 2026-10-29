import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { ForgotPassword, ResetPassword } from './PasswordRecovery';
import Login from './Login';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: jest.fn() }) }));
jest.mock('react-router-dom', () => ({ Link: ({ to, children }) => <a href={to}>{children}</a>, useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  window.history.replaceState(null, '', '/');
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const enter = async (selector, value) => {
  await act(async () => {
    const field = container.querySelector(selector);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
};
const submit = async () => { await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };

test('login exposes a Forgot password link', async () => {
  await act(async () => root.render(<Login />));
  expect(container.querySelector('a[href="/forgot-password"]').textContent).toBe('Forgot password?');
});

test.each(['staff@example.com', 'unknown@example.com'])('forgot request for %s shows the same non-enumerating result', async email => {
  api.forgotPassword.mockResolvedValue({ data: { message: 'Generic response' } });
  await act(async () => root.render(<ForgotPassword />));
  await enter('#recovery-email', email); await submit();
  expect(api.forgotPassword).toHaveBeenCalledWith(email);
  expect(container.querySelector('[role="status"]').textContent).toContain('If an eligible account exists');
  expect(container.textContent).toContain('15 minutes');
});

test('forgot delivery request failure is retryable without revealing server details', async () => {
  api.forgotPassword.mockRejectedValue(new Error('Private transport configuration'));
  await act(async () => root.render(<ForgotPassword />));
  await enter('#recovery-email', 'staff@example.com'); await submit();
  expect(container.querySelector('[role="alert"]').textContent).toContain('Please retry');
  expect(container.textContent).not.toContain('Private transport');
  expect(container.querySelector('button').disabled).toBe(false);
});

test('missing reset token shows a recovery link without submitting a credential', async () => {
  await act(async () => root.render(<ResetPassword />));
  expect(container.textContent).toContain('missing or invalid');
  expect(container.querySelector('a[href="/forgot-password"]')).not.toBeNull();
  expect(api.resetPassword).not.toHaveBeenCalled();
});

test('reset token is removed from the URL, password confirmation is required, and success does not sign in', async () => {
  window.history.replaceState(null, '', '/reset-password#token=synthetic-token');
  api.resetPassword.mockResolvedValue({ data: { message: 'Password updated' } });
  await act(async () => root.render(<ResetPassword />));
  expect(window.location.hash).toBe('');
  expect(container.textContent).not.toContain('synthetic-token');
  await enter('#recovery-password', 'Synthetic-new-password');
  await enter('#recovery-confirmation', 'Different-password'); await submit();
  expect(api.resetPassword).not.toHaveBeenCalled();
  expect(container.textContent).toContain('do not match');
  await enter('#recovery-confirmation', 'Synthetic-new-password'); await submit();
  expect(api.resetPassword).toHaveBeenCalledWith('synthetic-token', 'Synthetic-new-password');
  expect(container.textContent).toContain('Sign in again');
  expect(container.querySelector('input[type="password"]')).toBeNull();
  expect(api.login).not.toHaveBeenCalled();
});

test('invalid or expired token leaves a readable error and clears password fields', async () => {
  window.history.replaceState(null, '', '/reset-password#token=expired-synthetic-token');
  api.resetPassword.mockRejectedValue({ response: { data: { detail: 'This reset link is invalid or expired. Request a new link.' } } });
  await act(async () => root.render(<ResetPassword />));
  await enter('#recovery-password', 'Synthetic-new-password'); await enter('#recovery-confirmation', 'Synthetic-new-password'); await submit();
  expect(container.querySelector('[role="alert"]').textContent).toContain('invalid or expired');
  expect(container.querySelector('#recovery-password').value).toBe('');
  expect(container.querySelector('#recovery-confirmation').value).toBe('');
});
