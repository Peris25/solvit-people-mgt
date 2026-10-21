import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Employees from './Employees';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'hr_admin' } }) }));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
jest.mock('../components/EmployeePicker', () => () => <div />);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('demo generation is unavailable even in development and removal requires confirmation', async () => {
  api.getEmployees.mockResolvedValue({ data: [{ id: 'extra', full_name: 'Example Employee' }] });
  api.getAllMastersSettings.mockResolvedValue({ data: {} });
  const environment = process.env.NODE_ENV;
  try {
    process.env.NODE_ENV = 'development';
    await act(async () => root.render(<Employees />));
  } finally { process.env.NODE_ENV = environment; }
  expect(container.textContent).not.toMatch(/generate demo employees/i);
  const button = [...container.querySelectorAll('button')].find(b => b.textContent === 'Remove');
  await act(async () => button.click());
  expect(api.removeEmployee).not.toHaveBeenCalled();
  expect(container.querySelector('[role="dialog"]').textContent).toContain('Example Employee');
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === 'Cancel').click());
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  await act(async () => button.click());
  api.removeEmployee.mockResolvedValue({ data: { status: 'removed' } });
  await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === 'Remove employee').click());
  expect(api.removeEmployee).toHaveBeenCalledWith('extra', 'Example Employee');
});

test('existing employee mode allows unknown start date and role level', async () => {
  api.getEmployees.mockResolvedValue({ data: [] });
  api.getAllMastersSettings.mockResolvedValue({ data: {} });
  await act(async () => root.render(<Employees />));
  await act(async () => container.querySelector('[data-testid="add-employee-btn"]').click());
  expect(container.querySelector('input[type="date"]').required).toBe(true);
  await act(async () => container.querySelector('form input[type="checkbox"]').click());
  expect(container.querySelector('input[type="date"]').required).toBe(false);
  expect(container.querySelector('input[type="date"]').value).toBe('');
  expect(container.querySelector('[data-testid="employee-role_level"]').value).toBe('');
});

test.each([
  ['HR & People', false, false], ['HR_People', false, false],
  ['Retired Department', false, false], [undefined, false, false],
  ['HR & People', true, false], ['HR & People', false, true],
])('preserves or deliberately changes department %s (load failure %s, change %s)', async (department, loadFailure, change) => {
  api.getEmployees.mockResolvedValue({ data: [{ id: 'jessica', full_name: 'Jessica Mining',
    department, work_email: 'jessica@example.test', role_title: 'HR', start_date: '2025-01-01',
    line_manager_id: 'manager-id', lifecycle_state: 'Active', role_level: 'L2' }] });
  api.getAllMastersSettings.mockResolvedValue({ data: { workforce: { departments: [
    { name: 'Operations', active: true }, { name: 'HR & People', active: true },
    { name: 'Inactive', active: false },
  ] } } });
  if (loadFailure) api.getAllMastersSettings.mockRejectedValue(new Error('Unavailable'));
  api.updateEmployee.mockResolvedValue({ data: {} });
  await act(async () => root.render(<Employees />));
  expect(container.textContent).not.toMatch(/generate demo employees/i);
  const edit = [...container.querySelectorAll('button')].find(b => b.textContent === 'Edit');
  await act(async () => edit.click());
  const select = container.querySelector('[data-testid="employee-department"]');
  expect(select.value).toBe(department || '');
  expect([...select.options].map(o => o.value)).toContain('HR & People');
  expect([...select.options].map(o => o.value)).not.toContain('Inactive');
  if (loadFailure) expect(container.textContent).toContain('Departments could not be loaded');
  if (change) {
    await act(async () => { select.value = 'Operations'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  }
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.updateEmployee).toHaveBeenCalledWith('jessica', expect.objectContaining({ full_name: 'Jessica Mining' }));
  expect(api.updateEmployee.mock.calls[0][1]).not.toHaveProperty('line_manager_id');
  expect(api.updateEmployee.mock.calls[0][1]).not.toHaveProperty('work_email');
  if (change) expect(api.updateEmployee.mock.calls[0][1].department).toBe('Operations');
  else expect(api.updateEmployee.mock.calls[0][1]).not.toHaveProperty('department');
});
