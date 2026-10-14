import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Employees from './Employees';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'hr_manager' } }) }));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
jest.mock('../components/EmployeePicker', () => () => <div />);
global.IS_REACT_ACT_ENVIRONMENT = true;

test.each(['FTE', 'Full-Time', 'Consultant', 'Legacy Type'])('unchanged legacy type %s, imported level and status remain unchanged', async employment => {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  api.getEmployees.mockResolvedValue({ data: [{ id: 'staff', full_name: 'Synthetic staff', department: 'HR_People',
    employment_type: employment, job_level: 'Legacy Level', status: 'active', line_manager_id: 'boss',
    work_email: 'staff@example.com', role_title: 'Synthetic title', start_date: '2025-01-01' }] });
  api.getAllMastersSettings.mockResolvedValue({ data: { workforce: { departments: [{ name: 'HR & People' }] } } });
  api.updateEmployee.mockResolvedValue({ data: {} });
  try {
    await act(async () => root.render(<Employees />));
    await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === 'Edit').click());
    expect(container.querySelector('[data-testid="employee-employment_type"]').value).toBe(employment);
    expect(container.querySelector('[data-testid="employee-role_level"]').value).toBe('Legacy Level');
    expect(container.querySelector('[data-testid="employee-lifecycle_state"]').value).toBe('active');
    expect(container.querySelector('[data-testid="employee-department"]').value).toBe('HR_People');
    await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    const update = api.updateEmployee.mock.calls[0][1];
    for (const key of ['employment_type', 'role_level', 'lifecycle_state', 'department', 'line_manager_id']) {
      expect(update).not.toHaveProperty(key);
    }
    expect(update.job_level).toBe('Legacy Level');
  } finally { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); }
});
