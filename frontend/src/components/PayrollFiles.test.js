import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PayrollFiles from './PayrollFiles';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getPayrollFiles.mockResolvedValue({ data: [] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async () => { await act(async () => root.render(<PayrollFiles />)); };
const choose = async file => { await act(async () => { const input = container.querySelector('input[type="file"]'); Object.defineProperty(input, 'files', { configurable: true, value: [file] }); input.dispatchEvent(new Event('change', { bubbles: true })); }); };
const submit = async () => { await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };

test('provides an explicit upload action without uploading on selection', async () => {
  await render();
  expect(container.textContent).toContain('No payroll files uploaded yet');
  await choose(new File(['synthetic'], 'payroll.xlsx'));
  expect(api.uploadPayrollFile).not.toHaveBeenCalled();
  api.uploadPayrollFile.mockResolvedValue({ data: { id: 'private-file' } });
  await submit();
  expect(api.uploadPayrollFile.mock.calls[0][0].get('file').name).toBe('payroll.xlsx');
  expect(container.textContent).toContain('No employee or payroll records were changed');
});
test('rejects other formats before sending and shows scanner failures clearly', async () => {
  await render(); await choose(new File(['bad'], 'payroll.xlsm')); await submit();
  expect(api.uploadPayrollFile).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]').textContent).toContain('.xlsx');
  await choose(new File(['synthetic'], 'payroll.xlsx'));
  api.uploadPayrollFile.mockRejectedValue({ response: { data: { detail: 'Scanner unavailable' } } });
  await submit(); expect(container.querySelector('[role="alert"]').textContent).toContain('Scanner unavailable');
});
test('unpublished files have no usable download button', async () => {
  api.getPayrollFiles.mockResolvedValue({ data: [{ id: 'pending', file_name: 'payroll.xlsx', uploaded_at: '2026-11-04T08:00:00Z', status: 'Needs administrator review', download_allowed: false }] });
  await render();
  expect([...container.querySelectorAll('button')].find(b => b.textContent === 'Download').disabled).toBe(true);
  expect(container.textContent).not.toContain('stored_path');
});
