import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Forms from './Forms';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const forms = ['employee', 'line_manager', 'solver', 'hr_admin', 'hr_manager'].map(target_role => ({
  id: target_role, target_role, title: `${target_role} form`,
}));
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getForms.mockResolvedValue({ data: forms });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });

test.each([
  ['employee', ['employee']], ['line_manager', ['employee', 'line_manager']], ['solver', ['solver']],
  ['hr_admin', forms.map(form => form.id)], ['hr_manager', forms.map(form => form.id)],
])('%s sees only permitted cards, filters and counts', async (role, expected) => {
  useAuth.mockReturnValue({ user: { id: 'account', role } });
  await act(async () => root.render(<Forms />));
  expect(container.querySelectorAll('[data-testid^="form-"]').length).toBe(expected.length);
  forms.forEach(form => expect(Boolean(container.querySelector(`[data-testid="form-${form.id}"]`))).toBe(expected.includes(form.id)));
  expect(container.textContent).toContain(`${expected.length} form schemas`);
  const filters = [...container.querySelectorAll('button')].map(button => button.textContent);
  forms.forEach(form => expect(filters.some(label => label.startsWith(form.target_role.replaceAll('_', ' ')))).toBe(expected.includes(form.id)));
  expect(filters.some(label => label.startsWith('All'))).toBe(expected.length > 1);
});

test('switching from HR to employee discards prior categories and ignores a late HR response', async () => {
  let resolveOld;
  api.getForms.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
  useAuth.mockReturnValue({ user: { id: 'hr', role: 'hr_admin' } });
  await act(async () => root.render(<Forms />));
  useAuth.mockReturnValue({ user: { id: 'staff', role: 'employee' } });
  await act(async () => root.render(<Forms />));
  await act(async () => resolveOld({ data: forms }));
  expect(container.querySelectorAll('[data-testid^="form-"]').length).toBe(1);
  expect(container.querySelector('[data-testid="form-employee"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="form-hr_admin"]')).toBeNull();
});
