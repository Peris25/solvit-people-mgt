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
  api.performanceV3Action.mockResolvedValue({ data: { id: 'review' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async element => { await act(async () => root.render(element)); };
const click = async label => { await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent === label).click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };
const review = values => ({ id: 'review', version: 'v1', workflow_version: 3, status: 'Self_Draft', starts_on: '2099-11-01', self_due_on: '2099-11-07', manager_due_on: '2099-11-14', review_due_on: '2099-11-28', section_a_kpis: [{ id: 'quality', objective: 'Quality', metric: 'Verified report', target: 'Agreed rubric', direction: 'Rated', weight: 100 }], ...values });

test('send preflight shows exact corrections and selects only ready employees', async () => {
  await render(<V3CycleDialog employees={[{id:'ready',name:'Ready employee',review_ready:true,review_issues:[]},{id:'blocked',name:'Needs manager',review_ready:false,review_issues:['Selected Line Manager not found.']}]} onClose={jest.fn()} onCreated={jest.fn()} />);
  expect(container.textContent).toContain('Selected Line Manager not found.');
  expect(container.querySelector('input[value="blocked"]').disabled).toBe(true);
  await click('Select all ready employees');
  expect([...container.querySelectorAll('.pv-employee-picker input:checked')].map(input => input.value)).toEqual(['ready']);
  expect(container.textContent).toContain('1 ready to send; 1 need corrections');
  expect(api.performanceV3Action).not.toHaveBeenCalled();
});

test('employee checkboxes toggle individually and support selecting and clearing all', async () => {
  await render(<V3CycleDialog employees={[{id:'one',name:'Employee One'},{id:'two',name:'Employee Two'}]} onClose={jest.fn()} onCreated={jest.fn()} />);
  const one = container.querySelector('.pv-employee-picker input[value="one"]');
  const two = container.querySelector('.pv-employee-picker input[value="two"]');
  await act(async () => one.click());
  await act(async () => two.click());
  await act(async () => one.click());
  expect(one.checked).toBe(false); expect(two.checked).toBe(true);
  expect(container.textContent).toContain('1 of 2 employees selected');
  await click('Select all listed employees');
  expect(one.checked && two.checked).toBe(true);
  await click('Clear selection');
  expect(one.checked || two.checked).toBe(false);
  expect(api.performanceV3Action).not.toHaveBeenCalled();
});

test('HR sees employee status and probation routing without treating probation as an Annual assignment', async () => {
  await render(<V3CycleDialog employees={[{id:'probation',name:'Probation employee',employment_status:'Onboarding',expected_kpi_scope:'Probation',review_ready:false,review_issues:['Employee is in onboarding or probation. Use Create probation review, not the Annual cycle.']}]} onClose={jest.fn()} onCreated={jest.fn()} />);
  expect(container.textContent).toContain('Status: Onboarding');
  expect(container.textContent).toContain('Probation KPIs');
  expect(container.textContent).toContain('Use probation review');
  expect(container.querySelector('.pv-employee-picker input').disabled).toBe(true);
  expect(api.performanceV3Action).not.toHaveBeenCalled();
});

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
  expect(container.querySelector('.pv-employee-picker')).not.toBeNull();
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

test('manager scores sit beside the read-only employee results and flag a differing score', async () => {
  await render(<PerformanceV3Review review={review({ can_manage: true, status: 'Self_Submitted', self_assessment: { actuals: { quality: { actual: 1, evidence: 'Verified report' } }, values: [], accomplishments: [], challenge: '', do_differently: '', support: '' } })} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('Manager score');
  expect(container.textContent).toContain('Employee’s actual');
  expect(container.querySelector('[aria-label="Manager score for Quality"]')).not.toBeNull();
  expect(container.textContent).not.toContain('Release review to employee');
});

test('HR cannot release from the interface before the meeting is completed', async () => {
  await render(<PerformanceV3Review review={review({ can_hr_review: true, status: 'HR_Reviewed' })} onUpdated={jest.fn()} />);
  expect(container.textContent).toContain('HR: meeting arranged');
  expect(container.textContent).not.toContain('Release review to employee');
});

test('employee KPI fields have the five scores and no evidence input or fetch', async () => {
  await render(<PerformanceV3Review review={review({can_self_assess:true})} onUpdated={jest.fn()} />);
  const score=container.querySelector('.pv-self-kpi-table select');
  expect([...score.options].map(option=>option.textContent)).toEqual(['Choose','1.0','1.5','2.0','2.5','3.0']);
  expect(container.textContent).not.toContain('Evidence / result explanation');
  expect(api.getPerformanceV3Evidence).not.toHaveBeenCalled();
});

test('manager score differences are flagged and contribute to the weighted average', async () => {
  await render(<PerformanceV3Review review={review({can_manage:true,status:'Self_Submitted',self_assessment:{actuals:{quality:{actual:1,self_score:1}},values:[],accomplishments:[]}})} onUpdated={jest.fn()} />);
  await change(container.querySelector('[aria-label="Manager score for Quality"]'),'2');
  expect(container.textContent).toContain('Differs from self-score');
  expect(container.querySelector('.pv-section-a-total strong').textContent).toBe('2.00');
  expect(container.querySelector('[aria-label="Comment for Quality"]').required).toBe(true);
});

test('released values show signed gaps and HR-only retention stays hidden', async () => {
  await render(<PerformanceV3Review review={review({scores_released:true,status:'Completed',peer_summary:{response_count:3,averages:[7.5,8,8,8,8],gaps:[2.5,0,0,0,0],dimension_scores:[2.25,2,2,2,2],score:2.05,retention_average:10}})} onUpdated={jest.fn()} />);
  expect(container.querySelector('.pv-gap-flagged').textContent).toBe('+2.5');
  expect(container.textContent).toContain('2.25');
  expect(container.textContent).not.toContain('HR-only retention signal');
});

test('released employee review offers acknowledgement and written dispute', async () => {
  await render(<PerformanceV3Review review={review({ scores_released: true, status: 'Completed', overall_score: 1.5, rating: 'Met', nine_box_placement: 'Core_Contributor', ack_due_on: '2099-12-05' })} onUpdated={jest.fn()} />);
  await click('Acknowledge review');
  expect(api.performanceV3Action).toHaveBeenCalledWith('reviews', 'review', 'acknowledge', { expected_version: 'v1', confirmed: true });
  expect(container.textContent).toContain('Written dispute to HR');
});


test('Create Review groups four Alignment questions under each approved pillar', async () => {
  const questions = Array.from({ length: 12 }, (_, i) => ({ id: `q${i + 1}`, pillar: Math.floor(i / 4) + 1, text: `Approved question ${i + 1}` }));
  await render(<V3CycleDialog employees={[]} questions={questions} onClose={jest.fn()} onCreated={jest.fn()} />);
  for (const title of ['Environment', 'Values Alignment', 'Rewards & Recognition']) {
    const section = container.querySelector(`section[aria-label="${title}"]`);
    expect(section.querySelectorAll('li')).toHaveLength(4);
  }
  expect(container.textContent).toContain('1 = Strongly Disagree');
  expect(container.textContent).toContain('5 = Strongly Agree');
});


test('employee self-score guide is linked to the score control', async () => {
  await render(<PerformanceV3Review review={review({ can_self_assess: true })} onUpdated={jest.fn()} />);
  const guide = container.querySelector('#self-kpi-score-guide');
  expect(guide.textContent).toContain('1.0 = met or beat target');
  expect(guide.textContent).toContain('3.0 = 60% or less');
  expect(container.querySelector('select[aria-describedby="self-kpi-score-guide"]')).not.toBeNull();
});

test('HR peer progress shows counts and shortfalls without reviewer pairings', async () => {
  api.getPerformanceV3Setup.mockResolvedValue({ data: { employees: [], roles: [], reviewers: [], reviews: [], cycles: [{ id: 'cycle', cycle_type: 'Year_End', cycle_year: 2026, status: 'Open' }], peer_progress: [{ employee_id: 'staff', employee_name: 'Synthetic staff', cycle_id: 'cycle', received: 2, chosen: 5, submitted: 1, below_received_minimum: true, below_chosen_minimum: false, below_submitted_minimum: true }] } });
  await render(<PerformanceV3Panel user={{ role: 'hr_admin', employee_id: 'hr' }} onUpdated={jest.fn()} />);
  const section = container.querySelector('[aria-label="Anonymous peer review progress"]');
  expect(section.textContent).toContain('Synthetic staff');
  expect(section.querySelectorAll('tbody tr')).toHaveLength(1);
  expect(section.querySelectorAll('.pv-score-gap')).toHaveLength(2);
  expect([...section.querySelectorAll('th')].map(e => e.textContent)).toEqual(['Employee','Cycle','Received','Chosen to review','Submitted','Synthetic staff']);
});


const submitCycleForm = async () => { await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };
test('send all requires a confirmed Open cycle and leaves a visible receipt until Done', async () => {
  const created = jest.fn();
  api.performanceV3Action.mockImplementation((kind, id, action) => Promise.resolve({ data: action === 'create' ? { id: 'cycle' } : { id: 'cycle', status: 'Open' } }));
  await render(<V3CycleDialog employees={[{id:'staff',name:'Synthetic staff'},{id:'other',name:'Synthetic other'}]} onClose={jest.fn()} onCreated={created} />);
  await click('Select all listed employees');
  expect(container.textContent).toContain('2 of 2 employees selected');
  await submitCycleForm();
  expect(api.performanceV3Action).toHaveBeenLastCalledWith('cycles','cycle','open',{employee_ids:['staff','other']});
  expect(container.textContent).toContain('Reviews are available for 2 selected employees.');
  expect(created).not.toHaveBeenCalled();
  expect(container.querySelector('form')).toBeNull();
  await act(async () => document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })));
  expect(document.activeElement.textContent).toBe('Done - view tracker');
  await click('Done - view tracker');
  expect(created).toHaveBeenCalledWith({count:2,cycleId:'cycle'});
});

test('a soft send failure retains the selected employees and prepared cycle without claiming success', async () => {
  const created=jest.fn();
  api.performanceV3Action.mockImplementation((kind,id,action)=>Promise.resolve(action==='create'?{data:{id:'prepared'}}:{data:null,_serverError:true,status:500}));
  await render(<V3CycleDialog employees={[{id:'staff',name:'Synthetic staff'}]} onClose={jest.fn()} onCreated={created} />);
  await click('Select all listed employees'); await submitCycleForm();
  expect(container.textContent).toContain('Sending could not be confirmed');
  expect(container.querySelectorAll('.pv-employee-picker input:checked')).toHaveLength(1);
  expect(created).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain('Review requests confirmed');
  api.performanceV3Action.mockResolvedValue({data:{id:'prepared',status:'Open'}});
  await submitCycleForm();
  expect(api.performanceV3Action.mock.calls.filter(call=>call[2]==='create')).toHaveLength(1);
  expect(container.textContent).toContain('Reviews are available for 1 selected employee.');
});


test('HR must select a cycle and explicitly confirm its deletion with a reason', async () => {
  const archived=jest.fn(), created=jest.fn();
  api.performanceV3Action.mockResolvedValue({data:{id:'cycle',status:'Archived'}});
  await render(<V3CycleDialog employees={[]} cycles={[{id:'cycle',cycle_type:'Year_End',cycle_year:2026,starts_on:'2026-11-23',ends_on:'2026-12-20',status:'Open'}]} onClose={jest.fn()} onCreated={created} onArchived={archived} />);
  await change(container.querySelector('select'),'cycle');
  await click('Delete unused cycle');
  expect(api.performanceV3Action).not.toHaveBeenCalled();
  expect(container.querySelector('[aria-label="Delete cycle confirmation"]').textContent).toContain('2026-11-23');
  await change(container.querySelector('[aria-label="Cycle deletion reason"]'),'Wrong cycle settings');
  await click('Confirm delete unused cycle');
  expect(api.performanceV3Action).toHaveBeenCalledWith('cycles','cycle','archive',{reason:'Wrong cycle settings'});
  expect(container.textContent).toContain('Unused cycle deleted');
  expect(created).not.toHaveBeenCalled();
  await click('Done'); expect(archived).toHaveBeenCalledWith({cycleId:'cycle'});
});

test('blocked cycle deletion retains the cycle and shows the server reason', async () => {
  api.performanceV3Action.mockRejectedValue({response:{status:409,data:{detail:'Assessment work has started. This cycle cannot be deleted.'}}});
  await render(<V3CycleDialog employees={[]} cycles={[{id:'cycle',cycle_type:'Year_End',cycle_year:2026,starts_on:'2026-11-23',ends_on:'2026-12-20',status:'Open'}]} onClose={jest.fn()} onCreated={jest.fn()} />);
  await change(container.querySelector('select'),'cycle'); await click('Delete unused cycle');
  await change(container.querySelector('[aria-label="Cycle deletion reason"]'),'Wrong cycle settings'); await click('Confirm delete unused cycle');
  expect(container.textContent).toContain('Assessment work has started');
  expect(container.textContent).not.toContain('Unused cycle deleted');
});


test('an earlier cycle is visible for management and cannot be sent through the new workflow', async () => {
  await render(<V3CycleDialog employees={[{id:'staff',name:'Synthetic staff'}]} cycles={[{id:'earlier',cycle_type:'Year_End',cycle_year:2026,starts_on:'2026-11-23',ends_on:'2026-12-20',status:'Configured'}]} onClose={jest.fn()} onCreated={jest.fn()} />);
  expect(container.querySelector('option[value="earlier"]').textContent).toContain('Earlier setup (manage only)');
  await change(container.querySelector('select'),'earlier');
  expect(container.textContent).toContain('This is an earlier cycle setup');
  await click('Select all listed employees');
  expect([...container.querySelectorAll('button')].find(button=>button.textContent==='Create and send reviews').disabled).toBe(true);
  await click('Delete unused cycle');
  expect(container.querySelector('[aria-label="Delete cycle confirmation"]')).not.toBeNull();
  expect(api.performanceV3Action).not.toHaveBeenCalled();
});
