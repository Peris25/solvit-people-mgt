import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import KpiTemplate from './KpiTemplate';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container, updated;
const template = { name: 'Standard KPIs', version: 'v1', goals: [1,2,3].map(i => ({ objective: `Objective ${i}`, metric: 'Measurement', target: 'Approved target' })) };
const review = { id: 'review', employee_name: 'Synthetic Staff', cycle_type: 'Year_End', cycle_year: 2026, workflow_version: 1, status: 'Draft', section_a_kpis: [] };
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  updated = jest.fn().mockResolvedValue(); api.getKpiTemplate.mockResolvedValue({ data: template });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async reviews => { await act(async () => root.render(<KpiTemplate reviews={reviews || [review]} onUpdated={updated} />)); };
const click = async text => { await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === text).click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); }); };
const submit = async index => { await act(async () => container.querySelectorAll('form')[index].dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };

test('saved standard KPIs apply only to selected empty reviews and report skips', async () => {
  api.applyKpiTemplate.mockResolvedValue({ data: { applied: ['review'], skipped: [{ review_id: 'own-review', reason: 'Another HR must assign your KPIs' }] } });
  await render([review, { ...review, id: 'own-review', employee_name: 'Synthetic HR' }, { ...review, id: 'locked', status: 'Self_Submitted' }, { ...review, id: 'existing', section_a_kpis: [{ id: 'preserved' }] }, { ...review, id: 'probation', cycle_type: 'Probation' }]);
  expect(container.querySelectorAll('input[type="checkbox"]').length).toBe(2);
  await change(container.querySelector('input[type="date"]'), '2026-11-20');
  await click('Select all eligible reviews'); await submit(1);
  expect(api.applyKpiTemplate).toHaveBeenCalledWith({ review_ids: ['review', 'own-review'], version: 'v1', due_on: '2026-11-20' });
  expect(container.textContent).toContain('1 reviews updated; 1 skipped.');
  expect(container.textContent).toContain('Another HR must assign your KPIs');
  expect(updated).toHaveBeenCalledTimes(1);
});

test('editing the template disables apply until versioned save succeeds', async () => {
  await render();
  await change(container.querySelector('[aria-label="Objective KPI 1"]'), 'Updated objective');
  await change(container.querySelector('input[type="date"]'), '2026-11-20'); await click('Select all eligible reviews');
  expect([...container.querySelectorAll('button')].find(b => b.textContent === 'Apply KPIs to 1 reviews').disabled).toBe(true);
  api.saveKpiTemplate.mockResolvedValue({ data: { ...template, version: 'v2', goals: [{ ...template.goals[0], objective: 'Updated objective' }, ...template.goals.slice(1)] } });
  await submit(0);
  expect(api.saveKpiTemplate).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 'v1' }));
  expect([...container.querySelectorAll('button')].find(b => b.textContent === 'Apply KPIs to 1 reviews').disabled).toBe(false);
});

test('new template starts with three blank KPIs and no fabricated targets', async () => {
  api.getKpiTemplate.mockResolvedValue({ data: null }); await render([]);
  expect(container.querySelector('[aria-label="Target KPI 1"]').value).toBe('');
  expect(container.querySelectorAll('fieldset').length).toBe(3);
  expect(container.textContent).toContain('No empty reviews are available');
  await click('Add KPI'); await click('Add KPI');
  expect(container.querySelectorAll('fieldset').length).toBe(5);
  expect([...container.querySelectorAll('button')].find(b => b.textContent === 'Add KPI').disabled).toBe(true);
});

test('server failure is visible without claiming KPIs were applied', async () => {
  api.applyKpiTemplate.mockRejectedValue({ response: { data: { detail: 'The template changed. Reload before applying.' } } });
  await render(); await change(container.querySelector('input[type="date"]'), '2026-11-20'); await click('Select all eligible reviews'); await submit(1);
  expect(container.querySelector('[role="alert"]').textContent).toContain('The template changed');
  expect(updated).not.toHaveBeenCalled(); expect(container.textContent).not.toContain('reviews updated;');
});
