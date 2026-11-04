import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Organogram from './Organogram';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

jest.mock('../services/api');
jest.mock('../context/AuthContext');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { useAuth.mockReturnValue({ user: { id: 'synthetic', role: 'employee' } }); container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async data => { api.getOrganogram.mockResolvedValue({ data }); await act(async () => root.render(<Organogram />)); };

test('unsupported roles cannot load the organogram through a direct page visit', async () => {
  useAuth.mockReturnValue({ user: { role: 'solver' } });
  await render({ roots: [], total: 0 });
  expect(api.getOrganogram).not.toHaveBeenCalled();
  expect(container.textContent).toContain('not available');
});

test('compact reference role chart is primary and live tree is collapsed initially', async () => {
  await render({ roots: [], total: 0 });
  const chart=container.querySelector('svg[role="img"]');
  expect(chart.getAttribute('viewBox')).toBe('0 0 1024 720');
  expect(chart.textContent).toContain('Executive Director linked laterally');
  expect(chart.textContent).toContain('FINANCE &');
  expect(chart.textContent).toContain('IT SUPPORT');
  expect(container.querySelector('[data-testid="employee-reporting-details"]').open).toBe(false);
});

test('distinct render keys keep conflicting records visible with review notices', async () => {
  await render({ total: 2, issues: 2, roots: [
    { id: 'duplicate', node_id: 'node-first', name: 'Synthetic first', identity_status: 'ambiguous', direct_reports: [] },
    { id: 'duplicate', node_id: 'node-second', name: 'Synthetic second', reporting_status: 'cycle', direct_reports: [] },
  ] });
  expect(container.textContent).toContain('Synthetic first');
  expect(container.textContent).toContain('Synthetic second');
  expect(container.textContent).toContain('Employee identifier needs review');
  expect(container.textContent).toContain('Reporting cycle needs review');
  expect(container.textContent).toContain('saved assignments have not been changed');
});

test('search uses configured department labels and preserves ancestor context', async () => {
  await render({ total: 2, roots: [{ id: 'boss', name: 'Synthetic manager', direct_reports: [
    { id: 'staff', name: 'Synthetic staff', department: 'HR_People', department_label: 'HR & People', direct_reports: [] },
  ] }] });
  const search = container.querySelector('input');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'HR & People');
    search.dispatchEvent(new Event('input', { bubbles: true }));
  });
  expect(container.querySelector('[data-testid="employee-reporting-details"]').open).toBe(true);
  expect(container.textContent).toContain('Synthetic manager');
  expect(container.textContent).toContain('Synthetic staff');
  expect(container.textContent).toContain('HR & People');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, 'no-such-person');
    search.dispatchEvent(new Event('input', { bubbles: true }));
  });
  expect(container.textContent).toContain('No people match your search');
});

test('reporting cards expand and collapse using the keyboard', async () => {
  await render({ total: 2, roots: [{ id: 'boss', name: 'Synthetic manager', direct_reports: [{ id: 'staff', name: 'Synthetic staff', direct_reports: [] }] }] });
  const toggle = container.querySelector('[role="button"]');
  await act(async () => toggle.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
  expect(container.textContent).not.toContain('Synthetic staff');
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  await act(async () => toggle.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true })));
  expect(container.textContent).toContain('Synthetic staff');
});

test('null API data produces a safe load failure', async () => {
  await render(null);
  expect(container.textContent).toContain('could not be loaded');
  expect(container.querySelector('[data-testid="org-empty"]')).toBeNull();
});

test('empty directory retains existing empty state', async () => {
  await render({ total: 0, roots: [] });
  expect(container.querySelector('[data-testid="org-empty"]')).not.toBeNull();
});
