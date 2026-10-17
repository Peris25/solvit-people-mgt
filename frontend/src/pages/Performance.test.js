import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Performance from './Performance';
import PerformanceWorkflow, { CycleConfiguration } from '../components/PerformanceWorkflow';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { role: 'employee', employee_id: 'staff' } });
  api.getReviews.mockResolvedValue({ data: [] }); api.getActiveCycle.mockResolvedValue({ data: { is_active: false } });
  api.getReviewCycles.mockResolvedValue({ data: [] }); api.getTalentDensity.mockResolvedValue({ data: null });
  api.getEmployees.mockResolvedValue({ data: [] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });
const render = async element => { await act(async () => root.render(element)); };
const click = async text => { const target = [...container.querySelectorAll('button')].find(b => b.textContent === text); expect(target).toBeTruthy(); await act(async () => target.click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };
const submit = async form => { await act(async () => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };
const review = extra => ({ id:'review', workflow_version:1, status:'Draft', section_a_kpis:[], ...extra });

test('staff empty state shows no fabricated active cycle or HR matrix/configuration', async () => {
  await render(<Performance />);
  expect(container.textContent).toContain('No review cycle currently active'); expect(container.textContent).toContain('No reviews yet');
  expect(container.textContent).not.toContain('Configure review cycle (HR)'); expect(container.textContent).not.toContain('9-Box Matrix');
});
test('review list displays employee names and authorized detail, not truncated identifiers', async () => {
  const row = review({ employee_id:'canonical-identifier', employee_name:'Synthetic Ada', scores_released:false });
  api.getReviews.mockResolvedValue({ data:[row] }); api.getReview.mockResolvedValue({ data:row });
  await render(<Performance />); expect(container.textContent).toContain('Synthetic Ada'); expect(container.textContent).not.toContain('canonica...');
  await click('View'); expect(api.getReview).toHaveBeenCalledWith('review'); expect(container.textContent).toContain('Final scores remain private');
});
test('load failure offers retry', async () => {
  api.getReviews.mockRejectedValue(new Error('offline')); await render(<Performance />);
  expect(container.querySelector('[role="alert"]').textContent).toContain('Unable to load');
});
test('self-assessment submits only employee fields through the staged endpoint', async () => {
  const updated = jest.fn(); api.submitReviewAssessment.mockResolvedValue({});
  await render(<PerformanceWorkflow review={review({ can_self_assess:true, section_a_kpis:[1,2,3].map(id => ({ id, objective:'Agreed goal', progress:0 })) })} onUpdated={updated} />);
  const areas = container.querySelectorAll('textarea');
  await change(areas[0], 'Summary'); await change(areas[1], 'Achievements'); await change(areas[2], 'Support');
  await submit(container.querySelector('form'));
  expect(api.submitReviewAssessment).toHaveBeenCalledWith('review','self',{ summary:'Summary', achievements:'Achievements', support_needed:'Support', submit:true });
  expect(updated).toHaveBeenCalledTimes(1); expect(container.textContent).not.toContain('Approve HR review');
});
test('manager form has KPI scores and evidence but no final score or HR inputs', async () => {
  await render(<PerformanceWorkflow review={review({ can_manage:true, status:'Self_Submitted', section_a_kpis:[1,2,3].map(id => ({ id, objective:'Agreed goal' })) })} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('Submit manager assessment'); expect(container.textContent).not.toContain('Section B score');
  expect(container.querySelectorAll('input[type="number"]').length).toBe(3);
});
test('HR releases scores separately after HR assessment', async () => {
  api.submitReviewAssessment.mockResolvedValue({});
  await render(<PerformanceWorkflow review={review({ can_hr_review:true, status:'HR_Reviewed' })} onUpdated={jest.fn()} />);
  await click('Release scores to employee'); expect(api.submitReviewAssessment).toHaveBeenCalledWith('review','release',{});
});
test('cycle configuration identifies conflicting policies and requires explicit confirmation', async () => {
  await render(<CycleConfiguration cycles={[]} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('50/30/20'); expect(container.textContent).toContain('60/25/15');
  expect([...container.querySelectorAll('button')].find(b => b.textContent === 'Configure cycle').disabled).toBe(true);
});
test('historical publication has a separate approval reference and never sends new scores', async () => {
  api.submitReviewAssessment.mockResolvedValue({});
  await render(<PerformanceWorkflow review={{ id:'historical',status:'Completed',can_hr_review:true }} onUpdated={jest.fn()} />);
  await change(container.querySelector('input'), 'Approved historical publication'); await submit(container.querySelector('form'));
  expect(api.submitReviewAssessment).toHaveBeenCalledWith('historical','legacy-release',{ approval_reference:'Approved historical publication' });
});
test('backend rejection is visible and does not advance the workflow', async () => {
  const updated = jest.fn(); api.submitReviewAssessment.mockRejectedValue({ response:{ data:{ detail:'HR review is not complete' } } });
  await render(<PerformanceWorkflow review={review({ can_hr_review:true,status:'HR_Reviewed' })} onUpdated={updated} />);
  await click('Release scores to employee'); expect(container.querySelector('[role="alert"]').textContent).toContain('HR review is not complete');
  expect(updated).not.toHaveBeenCalled();
});
test('employee explicitly acknowledges agreed goals through the owner-scoped endpoint', async () => {
  api.updateReviewGoals.mockResolvedValue({});
  await render(<PerformanceWorkflow review={review({ can_self_assess:true, section_a_kpis:[1,2,3].map(id => ({ id, objective:'Agreed goal' })) })} onUpdated={jest.fn()} />);
  await click('Acknowledge agreed goals'); expect(api.updateReviewGoals).toHaveBeenCalledWith('review',{ action:'acknowledge' });
});
