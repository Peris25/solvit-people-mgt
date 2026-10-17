import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Documents from './Documents';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../components/EmployeePicker', () => ({ onChange }) => <button onClick={() => onChange({ id: 'staff', full_name: 'Synthetic Ada' })}>Choose synthetic employee</button>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const user = { id: 'account', employee_id: 'self', role: 'employee' };
const file = { id: 'document', employee_id: 'self', file_name: 'Contract.pdf', category: 'Signed Employment Contract', uploaded_at: '2026-10-01', status: 'Available', stored_path: 'PRIVATE', download_allowed: true };
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user });
  api.getMyDocuments.mockResolvedValue({ data: [file] });
  api.getEmployeeDocuments.mockResolvedValue({ data: [] });
  api.getDocumentCategories.mockResolvedValue({ data: { categories: ['Other', 'Signed Employment Contract'] } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); jest.useRealTimers(); });
const render = async () => { await act(async () => root.render(<Documents />)); };
const click = async text => { const button = [...container.querySelectorAll('button')].find(b => b.textContent === text); expect(button).toBeTruthy(); await act(async () => button.click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };

test('employees use the own-document endpoint, with status and no private paths or assignment controls', async () => {
  await render(); expect(api.getMyDocuments).toHaveBeenCalledWith(); expect(api.getEmployeeDocuments).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Contract.pdf'); expect(container.textContent).toContain('Available');
  expect(container.textContent).toContain('separate Policy Library'); expect(container.textContent).not.toContain('PRIVATE');
  expect(container.querySelector('[data-testid="upload-doc-btn"]')).toBeNull(); expect(container.textContent).not.toContain('HR document assignment');
  expect(container.querySelector('a[href*="document"]')).toBeNull();
});

test('empty and error states distinguish unavailable data from no authorized files', async () => {
  api.getMyDocuments.mockResolvedValue({ data: [] }); await render(); expect(container.textContent).toContain('No authorized documents');
  api.getMyDocuments.mockResolvedValue({ data: null });
  useAuth.mockReturnValue({ user: { ...user, id: 'second' } }); await render();
  expect(container.textContent).toContain('Documents are unavailable'); expect(container.textContent).not.toContain('No authorized documents');
  api.getMyDocuments.mockResolvedValue({ data: [] }); await click('Retry'); expect(container.textContent).toContain('No authorized documents');
});

test('HR chooses a saved employee before assigning an upload, preserving private defaults', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } }); await render(); await click('Choose synthetic employee');
  expect(api.getEmployeeDocuments).toHaveBeenCalledWith('staff'); expect(container.textContent).toContain('Managing: Synthetic Ada');
  await act(async () => container.querySelector('[data-testid="upload-doc-btn"]').click());
  const upload = new File(['synthetic'], 'record.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  await act(async () => { const input = container.querySelector('[data-testid="upload-file-input"]'); Object.defineProperty(input, 'files', { configurable: true, value: [upload] }); input.dispatchEvent(new Event('change', { bubbles: true })); });
  api.uploadEmployeeDocument.mockResolvedValue({ data: { id: 'new' } });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  const [employeeId, data] = api.uploadEmployeeDocument.mock.calls[0];
  expect(employeeId).toBe('staff'); expect(data.get('visibility')).toBe('hr_only'); expect(data.get('confidential')).toBe('true');
  expect(data.get('file').name).toBe('record.xlsx');
});

test('upload failures retain the form and show the scanner error', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } }); await render();
  await act(async () => container.querySelector('[data-testid="upload-doc-btn"]').click());
  await act(async () => { const input = container.querySelector('[data-testid="upload-file-input"]'); Object.defineProperty(input, 'files', { value: [new File(['data'], 'file.pdf')] }); input.dispatchEvent(new Event('change', { bubbles: true })); });
  api.uploadEmployeeDocument.mockRejectedValue({ response: { data: { detail: 'Document scanning is unavailable' } } });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.textContent).toContain('Document scanning is unavailable'); expect(container.querySelector('form')).toBeTruthy();
});

test('downloads use the authenticated blob endpoint and handle failures', async () => {
  await render(); api.downloadEmployeeDocument.mockRejectedValue(new Error('denied')); await click('Download');
  expect(api.downloadEmployeeDocument).toHaveBeenCalledWith('document'); expect(container.textContent).toContain('no longer authorized');
});

test('account switching removes prior documents while the next inbox loads', async () => {
  await render(); let resolve; api.getMyDocuments.mockReturnValue(new Promise(r => { resolve = r; }));
  useAuth.mockReturnValue({ user: { ...user, id: 'second' } }); await render(); expect(container.textContent).not.toContain('Contract.pdf');
  await act(async () => resolve({ data: [] })); expect(container.textContent).toContain('No authorized documents');
});

test('HR can change audited metadata without an ownership input', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } });
  api.getMyDocuments.mockResolvedValue({ data: [{ ...file, visibility: 'hr_only', confidential: true }] });
  api.updateEmployeeDocument.mockResolvedValue({ data: { id: 'document' } });
  await render(); await click('Manage');
  await change(container.querySelector('[aria-label="Document title"]'), 'Approved contract title');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.updateEmployeeDocument).toHaveBeenCalledWith('document', expect.objectContaining({ title: 'Approved contract title', visibility: 'hr_only', confidential: true }));
  expect(api.updateEmployeeDocument.mock.calls[0][1].employee_id).toBeUndefined();
});

test('the browser blocks files larger than 20 MB before sending them', async () => {
  useAuth.mockReturnValue({ user: { ...user, role: 'hr_admin' } }); await render();
  await act(async () => container.querySelector('[data-testid="upload-doc-btn"]').click());
  const oversized = new File(['data'], 'big.pdf'); Object.defineProperty(oversized, 'size', { value: 20 * 1024 * 1024 + 1 });
  await act(async () => { const input = container.querySelector('[data-testid="upload-file-input"]'); Object.defineProperty(input, 'files', { value: [oversized] }); input.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.uploadEmployeeDocument).not.toHaveBeenCalled(); expect(container.textContent).toContain('20 MB limit');
});

test('an authorized download creates a temporary browser download and revokes its URL', async () => {
  jest.useFakeTimers();
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = jest.fn().mockReturnValue('blob:synthetic-document'); URL.revokeObjectURL = jest.fn();
  const anchorClick = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  try {
    api.downloadEmployeeDocument.mockResolvedValue({ data: new Blob(['synthetic document']) });
    await render(); await click('Download');
    expect(api.downloadEmployeeDocument).toHaveBeenCalledWith('document'); expect(anchorClick).toHaveBeenCalled();
    await act(async () => jest.advanceTimersByTime(1000));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-document');
  } finally { anchorClick.mockRestore(); URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; }
});
