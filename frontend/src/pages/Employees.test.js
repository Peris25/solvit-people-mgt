import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Employees from './Employees';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'hr_manager' } }) }));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
jest.mock('../components/EmployeePicker', () => () => <div />);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

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
