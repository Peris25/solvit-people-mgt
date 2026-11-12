import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeProfile from './EmployeeProfile';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ useParams: () => ({ id: 'staff' }), useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getEmployeeProfile.mockResolvedValue({ data: { employee: { id: 'staff', full_name: 'Synthetic staff',
    bank_name: 'Synthetic bank', bank_account_number: '000123', next_of_kin: { name: 'Synthetic contact', relationship: 'Sibling' } } } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });

test.each(['hr_admin', 'hr_manager', 'general_manager'])('%s sees a pencil in each editable card header and a separate bank card', async role => {
  useAuth.mockReturnValue({ user: { id: 'hr', role } });
  await act(async () => root.render(<EmployeeProfile />));
  const labels = ['Personal & statutory', 'Employment', 'Contacts & personal information', 'Bank & payment'];
  labels.forEach(title => {
    const button = container.querySelector(`[aria-label="Edit ${title}"]`);
    expect(button).not.toBeNull();
    expect(button.parentElement.textContent).toContain(title.charAt(0).toUpperCase() + title.slice(1).replace('statutory', 'Statutory'));
    expect(button.querySelector('svg')).not.toBeNull();
    expect(button.textContent).toBe('');
  });
  expect(container.textContent).not.toContain('Edit statutory information');
  expect(container.textContent).toContain('Synthetic contact · Sibling');
  expect(container.textContent).not.toContain('{"name"');
  await act(async () => container.querySelector('[aria-label="Edit Bank & payment"]').click());
  expect(container.querySelector('dialog')).not.toBeNull();
  expect(container.querySelector('[aria-label="Bank account number"]').value).toBe('000123');
});

test.each(['employee', 'line_manager', 'finance', 'it_admin'])('%s does not receive HR card edit controls', async role => {
  useAuth.mockReturnValue({ user: { id: 'account', role } });
  await act(async () => root.render(<EmployeeProfile />));
  expect(container.querySelector('[aria-label^="Edit "]')).toBeNull();
  expect(api.updateEmployee).not.toHaveBeenCalled();
});
