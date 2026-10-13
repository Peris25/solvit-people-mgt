import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeProfile from './EmployeeProfile';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'hr_admin' } }) }));
jest.mock('react-router-dom', () => ({ useParams: () => ({ id: 'jessica' }), useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

test.each([
  ['manager-id', 'Martin Karanja Kiarie', 'Martin Karanja Kiarie'],
  ['missing-id', null, 'Manager not found'],
  [null, null, '\u2014'],
])('renders manager %s safely and retains the overview', async (id, name, expected) => {
  api.getEmployeeProfile.mockResolvedValue({ data: { employee: {
    id: 'jessica', full_name: 'Jessica Mining', department: 'HR & People',
    line_manager_id: id, line_manager_name: name, lifecycle_state: 'Active',
  }, timeline: [] } });
  await act(async () => root.render(<EmployeeProfile />));
  expect(container.textContent).toContain(expected);
  expect(container.textContent).toContain('Jessica Mining');
  expect(container.textContent).toContain('Personal & Statutory');
  await act(async () => container.querySelector('[data-testid="profile-tab-timeline"]').click());
  expect(container.textContent).toContain('No timeline events');
});
