import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import StaffDirectory from './StaffDirectory';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({
  MemoryRouter: ({ children }) => children,
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const data = { departments: [
  { name: 'Operations', contact_for: '' }, { name: 'IT Support', contact_for: 'System access and devices' },
  { name: 'Leadership', contact_for: 'Strategy' }, { name: 'Valuation', contact_for: 'Report quality' },
  { name: 'Account Management', contact_for: 'Client relationships' }, { name: 'Human Resources', contact_for: 'Leave queries' },
], employees: [
  { node_id: 'first', full_name: 'Synthetic Ada', role_title: 'Engineer', department: 'IT Support', contact_for: 'System access and devices', work_email: 'ada@example.com', reporting_status: 'resolved', line_manager_name: 'Synthetic boss',
    salary_kes: 'restricted-salary', phone_number: 'restricted-phone', profile_photo_url: 'restricted-photo', medical_notes: 'restricted-medical' },
  { node_id: 'second', full_name: 'Synthetic Ben', role_title: 'Coordinator', department: 'Operations', reporting_status: 'none' },
] };
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'synthetic-user', role: 'employee' } });
  api.getStaffDirectory.mockResolvedValue({ data });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<MemoryRouter><StaffDirectory /></MemoryRouter>)); };
const search = async value => {
  await act(async () => {
    const input = container.querySelector('input');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

test('renders approved contacts, six filters and purpose notes while omitting private fields/photos', async () => {
  await render();
  expect(container.textContent).toContain('Synthetic Ada');
  expect(container.textContent).toContain('Contact for: System access and devices');
  expect(container.querySelector('a[href="mailto:ada@example.com"]')).not.toBeNull();
  expect(container.textContent).not.toContain('restricted-');
  expect(container.querySelector('img')).toBeNull();
  expect(container.querySelectorAll('option')).toHaveLength(7);
  expect(container.querySelector('a[href="/organogram"]')).not.toBeNull();
  expect(container.textContent).toContain('Reporting assignment awaits HR confirmation');
});

test.each(['Ada', 'Engineer', 'IT Support', 'devices'])('searches name/title/department/contact responsibility: %s', async query => {
  await render(); await search(query);
  expect(container.textContent).toContain('Synthetic Ada');
  expect(container.textContent).not.toContain('Synthetic Ben');
});

test('department filter combines with search and shows a clear empty result', async () => {
  await render();
  await act(async () => {
    const select = container.querySelector('select'); select.value = 'Operations';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  expect(container.textContent).toContain('Synthetic Ben');
  expect(container.textContent).not.toContain('Synthetic Ada');
  await search('Engineer');
  expect(container.textContent).toContain('No staff match');
});

test.each(['solver', 'solvers_manager', 'custom_staff'])('denies unsupported role %s without loading staff', async role => {
  useAuth.mockReturnValue({ user: { role } }); await render();
  expect(api.getStaffDirectory).not.toHaveBeenCalled();
  expect(container.textContent).toContain('not available');
});

test.each(['hr_admin', 'line_manager', 'finance', 'it_admin', 'board', 'executive'])('authorized role %s gets public-only directory', async role => {
  useAuth.mockReturnValue({ user: { role } }); await render();
  expect(api.getStaffDirectory).toHaveBeenCalledTimes(1);
  expect(container.textContent).not.toContain('restricted-');
});

test('server denial and malformed responses fail without showing employee cards', async () => {
  api.getStaffDirectory.mockRejectedValue({ response: { data: { detail: 'An eligible full-time employee account is required' } } });
  await render(); expect(container.textContent).toContain('eligible full-time');
  expect(container.querySelector('article')).toBeNull();
});

test('preserves unknown saved departments and displays explicitly returned business phone', async () => {
  api.getStaffDirectory.mockResolvedValue({ data: { departments: data.departments, employees: [{
    node_id: 'legacy', full_name: 'Synthetic legacy', department: 'Saved legacy department', work_phone: '+254 700 000 000', reporting_status: 'none',
  }] } });
  await render();
  expect(container.textContent).toContain('Saved legacy department');
  expect(container.textContent).toContain('Work phone: +254 700 000 000');
  expect(container.querySelectorAll('option')).toHaveLength(8);
});
