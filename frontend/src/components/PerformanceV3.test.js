import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PerformanceV3Panel, { V3CycleDialog } from './PerformanceV3Panel';
import PerformanceV3Review from './PerformanceV3Review';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getPerformanceV3Tasks.mockResolvedValue({ data: { peers: [], alignment: [], questions: [], peer_questions: [] } });
  api.getPerformanceV3Setup.mockResolvedValue({ data: { employees: [], roles: [], reviewers: [], reviews: [], cycles: [] } });
  api.getPerformanceV3Evidence.mockResolvedValue({ data: [] });
  api.performanceV3Action.mockResolvedValue({ data: { id: 'cycle' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async element => { await act(async () => root.render(element)); };
const click = async label => { await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === label).click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };
const review = values => ({ id: 'review', version: 'v1', workflow_version: 3, status: 'Self_Draft', starts_on: '2099-11-01', self_due_on: '2099-11-07', manager_due_on: '2099-11-14', review_due_on: '2099-11-28', section_a_kpis: [{ id: 'quality', objective: 'Quality', metric: 'Verified report', target: 'Agreed rubric', direction: 'Rated', weight: 100 }], ...values });

test('employees see only their own assigned tasks and cannot open HR preparation', async () => {
  await render(<PerformanceV3Panel user={{ role: 'employee', employee_id: 'staff' }} onUpdated={jest.fn()} />);
  expect(api.getPerformanceV3Setup).not.toHaveBeenCalled();
  expect(container.textContent).toContain('No peer or Alignment tasks are assigned');
  expect(container.textContent).not.toContain('Assign approved KPIs');
});

test('HR creates reviews in one popup with fixed policy and calculated dates', async () => {
  await render(<V3CycleDialog employees={[{ id: 'staff', name: 'Synthetic employee' }]} questions={[]} onClose={jest.fn()} onCreated={jest.fn()} />);
  expect(container.querySelector('[role="dialog"]')).not.toBeNull();
  const start = container.querySelector('input[type="date"]'); await change(start, '2099-11-01');
  expect(container.textContent).toContain('2099-11-07'); expect(container.textContent).toContain('2099-11-14');
  expect(container.textContent).toContain('2099-11-28'); expect(container.textContent).toContain('50%');
  expect(container.querySelector('[aria-label="Review employee"]')).not.toBeNull();
  expect(container.textContent).not.toContain('60 / 25 / 15');
});

test('employee saves a partial assessment without shifting empty value slots', async () => {
  const updated = jest.fn(); await render(<PerformanceV3Review review={review({ can_self_assess: true })} onUpdated={updated} />);
  await click('Save draft');
  expect(api.performanceV3Action).toHaveBeenCalledWith('reviews', 'review', 'self', expect.objectContaining({ expected_version: 'v1', submit: false,
    assessment: expect.objectContaining({ values: Array(5).fill({ score: '', example: '' }), accomplishments: ['', '', ''] }) }));
  expect(updated).toHaveBeenCalled();
});

test('failed submission retains input and never reports success', async () => {
  api.performanceV3Action.mockRejectedValue({ response: { data: { detail: 'Complete all five values' } } });
  await render(<PerformanceV3Review review={review({ can_self_assess: true })} onUpdated={jest.fn()} />);
  const input = container.querySelector('textarea'); await change(input, 'My preserved work');
  await click('Submit to line manager');
  expect(container.querySelector('[role="alert"]').textContent).toContain('Complete all five values');
  expect(input.value).toBe('My preserved work'); expect(container.querySelector('[role="status"]')).toBeNull();
});

test('manager gets confirmation inputs while final scores remain calculated', async () => {
  await render(<PerformanceV3Review review={review({ can_manage: true, status: 'Self_Submitted', self_assessment: { actuals: { quality: { actual: 1, evidence: 'Verified report' } }, values: [], accomplishments: [], challenge: '', do_differently: '', support: '' } })} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('Line manager assessment');
  expect(container.textContent).toContain('Confirmed actual');
  expect(container.textContent).not.toContain('Release review to employee');
});

test('HR cannot release from the interface before the meeting is completed', async () => {
  await render(<PerformanceV3Review review={review({ can_hr_review: true, status: 'HR_Reviewed' })} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('HR: meeting arranged');
  expect(container.textContent).not.toContain('Release review to employee');
});

test('released employee review offers acknowledgement and written dispute', async () => {
  await render(<PerformanceV3Review review={review({ scores_released: true, status: 'Completed', overall_score: 1.5, rating: 'Met', nine_box_placement: 'Core_Contributor', ack_due_on: '2099-12-05' })} onUpdated={jest.fn()} />);
  await click('Acknowledge review');
  expect(api.performanceV3Action).toHaveBeenCalledWith('reviews', 'review', 'acknowledge', { expected_version: 'v1', confirmed: true });
  expect(container.textContent).toContain('Written dispute to HR');
});
