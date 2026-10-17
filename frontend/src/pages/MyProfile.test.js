import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeeProfile from './EmployeeProfile';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ useParams: () => ({ id: 'forged-other' }), useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const user = { id: 'account', employee_id: 'staff', role: 'employee' };
const profile = () => ({ employee: { id: 'staff', full_name: 'Synthetic Ada', department: 'HR & People', role_title: 'Coordinator', line_manager_id: 'boss', line_manager_name: 'Synthetic Manager', personal_email: 'personal@example.com', profile_photo_url: 'https://unapproved.invalid/photo' }, timeline: [] });
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user, changePassword: jest.fn().mockResolvedValue({}), logout: jest.fn() });
  api.getMyProfile.mockResolvedValue({ data: profile() });
  api.getMyProfileChanges.mockResolvedValue({ data: [] });
  api.getProfileChangeInbox.mockResolvedValue({ data: [] });
  api.getEmployeeDocuments.mockResolvedValue({ data: [] });
  api.getDocumentCategories.mockResolvedValue({ data: { categories: [] } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<EmployeeProfile selfService />)); };
const click = async text => { const button = [...container.querySelectorAll('button')].find(b => b.textContent === text); expect(button).toBeTruthy(); await act(async () => button.click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };

test('uses the own-profile endpoint, preserves manager/department and keeps photos as placeholders', async () => {
  await render(); expect(api.getMyProfile).toHaveBeenCalledWith(); expect(api.getEmployeeProfile).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Synthetic Manager'); expect(container.textContent).toContain('HR & People');
  expect(container.textContent).toContain('personal@example.com'); expect(container.querySelector('img')).toBeNull();
});

test('permitted fields create a request, never directly update employee or restricted fields', async () => {
  api.requestProfileChange.mockResolvedValue({ data: { id: 'change', status: 'Pending_HR' } });
  await render(); await click('Profile changes');
  const select = container.querySelector('#profile-change-field');
  for (const field of ['department', 'role_title', 'line_manager_id', 'work_email']) expect([...select.options].map(option => option.value)).not.toContain(field);
  await change(container.querySelector('[aria-label="Requested value"]'), '+254700000001');
  await act(async () => container.querySelector('[data-testid="profile-changes"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.requestProfileChange).toHaveBeenCalledWith({ phone_number: '+254700000001' });
  expect(api.updateEmployee).not.toHaveBeenCalled();
  expect(container.textContent).toContain('saved profile remains unchanged until approval');
});

test('request failures show an error and retain input', async () => {
  api.requestProfileChange.mockRejectedValue({ response: { data: { detail: 'An existing profile change is awaiting review' } } });
  await render(); await click('Profile changes'); await change(container.querySelector('[aria-label="Requested value"]'), '+254700000001');
  await act(async () => container.querySelector('[data-testid="profile-changes"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.textContent).toContain('awaiting review');
  expect(container.querySelector('[aria-label="Requested value"]').value).toBe('+254700000001');
});

test('account security reuses the existing password flow and checks confirmation', async () => {
  const changePassword = jest.fn().mockResolvedValue({}); useAuth.mockReturnValue({ user, changePassword, logout: jest.fn() });
  await render(); await click('Account security');
  await change(container.querySelector('#required-current-password'), 'Existing-local-password-2026');
  await change(container.querySelector('#required-new-password'), 'New-local-password-2026');
  await change(container.querySelector('#required-confirm-password'), 'Different-local-password');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(changePassword).not.toHaveBeenCalled(); expect(container.textContent).toContain('do not match');
  await change(container.querySelector('#required-confirm-password'), 'New-local-password-2026');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(changePassword).toHaveBeenCalledWith('Existing-local-password-2026', 'New-local-password-2026');
});

test('documents use the resolved employee ID and explain conservative visibility', async () => {
  await render(); await click('Documents');
  expect(api.getEmployeeDocuments).toHaveBeenCalledWith('staff');
  expect(container.textContent).toContain('Only explicitly shared documents');
  expect(container.querySelector('[data-testid="upload-doc-btn"]')).toBeNull();
});

test('account switching hides previous profile and request data during loading', async () => {
  await render(); let resolve;
  api.getMyProfile.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { ...user, id: 'second' } });
  await render(); expect(container.textContent).not.toContain('Synthetic Ada');
  await act(async () => resolve({ data: { employee: { id: 'second', full_name: 'Synthetic Ben' } } }));
  expect(container.textContent).toContain('Synthetic Ben'); expect(container.textContent).not.toContain('Synthetic Ada');
});

test('an unlinked account gets a useful error and can still change its password', async () => {
  api.getMyProfile.mockResolvedValue({ data: null }); await render();
  expect(container.textContent).toContain('HR may need to verify');
  expect(container.querySelector('#required-current-password')).toBeTruthy();
});

test('HR uses the review inbox and bank approval remains pending Finance', async () => {
  useAuth.mockReturnValue({ user: { ...user, employee_id: 'hr', role: 'hr_admin' } });
  api.getMyProfile.mockResolvedValue({ data: { employee: { id: 'hr', full_name: 'Synthetic HR' } } });
  api.getProfileChangeInbox.mockResolvedValue({ data: [{ id: 'change', employee_id: 'staff', employee_name: 'Synthetic Ada', status: 'Pending_HR', changes: { bank_account_number: '001234' } }] });
  api.reviewProfileChange.mockResolvedValue({ data: { id: 'change', status: 'Pending_Finance' } });
  await render(); await click('Profile changes'); await click('HR approve');
  expect(api.reviewProfileChange).toHaveBeenCalledWith('change', 'Approve', '');
  expect(container.textContent).toContain('Pending_Finance');
});

test('document loading failure is not presented as an empty successful document list', async () => {
  api.getEmployeeDocuments.mockResolvedValue({ data: null });
  await render(); await click('Documents');
  expect(container.textContent).toContain('Documents are unavailable');
  expect(container.textContent).not.toContain('No documents uploaded yet.');
});
