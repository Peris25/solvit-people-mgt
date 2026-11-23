import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import ProbationReview from './ProbationReview';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
const review=extra=>({id:'probation',workflow_version:1,manager_led_probation:true,review_month:3,status:'Draft',probation_version:'v1',section_a_kpis:[{id:'quality',objective:'Quality',target:'Approved rubric',weight:100,direction:'Rated'}],...extra});
beforeEach(()=>{container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);api.submitReviewAssessment.mockResolvedValue({data:{id:'probation'}});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.resetAllMocks();});
const render=async props=>act(async()=>root.render(<ProbationReview review={review(props)} onUpdated={jest.fn()}/>));
const change=async(input,value)=>act(async()=>{Object.getOwnPropertyDescriptor(input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('change',{bubbles:true}));input.dispatchEvent(new Event('input',{bubbles:true}));});
const input=label=>container.querySelector(`[aria-label="${label}"]`);
const button=label=>[...container.querySelectorAll('button')].find(button=>button.textContent===label);

test('probation employee waits for the manager and never sees a self-scoring form',async()=>{
 await render({can_self_assess:false});
 expect(container.textContent).toContain('employee does not self-score');
 expect(container.querySelector('form')).toBeNull();
 expect(container.querySelector('input[type="number"]')).toBeNull();
});

test('manager enters monthly evidence and decimal scores then submits the staged assessment',async()=>{
 await render({can_manage:true});
 for(const [label,value] of [['Month 2 actual for Quality','Verified Month 2'],['Month 3 actual for Quality','Verified Month 3'],['Manager score for Quality','1.55'],['Evidence for Quality','Verified source'],['Overall assessment','Overall assessment'],['Strengths observed','Strengths'],['Development areas and support proposed','Weekly coaching']])await change(input(label),value);
 for(const name of ['Integrity','Hard Work & Ownership','Teamwork & Decency','Solution Orientation','Timeliness']){await change(input(`Probation value score for ${name}`),'1.5');await change(input(`Probation value evidence for ${name}`),'Observed example');}
 await change(container.querySelector('select'),'Confirm');
 await act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 const [id,stage,data]=api.submitReviewAssessment.mock.calls[0];
 expect([id,stage]).toEqual(['probation','manager']);
 expect(data.submit).toBe(true);expect(data.expected_version).toBe('v1');
 expect(data.kpis.quality.score).toBe('1.55');expect(data.values).toHaveLength(5);
 expect(api.createReview).not.toHaveBeenCalled();
});

test('resaving a returned draft excludes computed metadata from the request',async()=>{
 await render({can_manage:true,probation_manager_draft:{kpis:{quality:{m2:'Draft result'}},values:[],summary:'Draft',strengths:'',development_actions:'',recommendation:'',basis:'Months 2–3 combined',section_a_score:null,section_b_score:null}});
 await act(async()=>button('Save manager draft').click());
 const payload=api.submitReviewAssessment.mock.calls[0][2];
 expect(payload.submit).toBe(false);expect(payload.kpis.quality.m2).toBe('Draft result');
 expect(payload.basis).toBeUndefined();expect(payload.section_a_score).toBeUndefined();
});

test('HR outcome controls are unavailable before meeting completion',async()=>{
 await render({can_hr_review:true,status:'Manager_Submitted',probation_assessment_submitted:true});
 expect(container.textContent).toContain('HR approval is available after');
 expect(button('Approve probation outcome')).toBeUndefined();
 expect(button('Release probation outcome to employee')).toBeUndefined();
});

test('HR can approve after a completed meeting and must release separately',async()=>{
 await render({can_hr_review:true,status:'Manager_Submitted',meeting_completed_at:'2026-11-23T09:00:00Z',probation_meeting:{discussion:'Meeting held',agreed_actions:'Coaching'}});
 expect(button('Approve probation outcome')).toBeTruthy();expect(button('Release probation outcome to employee')).toBeUndefined();
 await render({can_hr_review:true,status:'HR_Reviewed',meeting_completed_at:'2026-11-23T09:00:00Z',probation_outcome:{outcome:'Confirm'}});
 expect(button('Release probation outcome to employee')).toBeTruthy();
});

test('employee can acknowledge receipt without agreeing with the scores',async()=>{
 await render({status:'Completed',can_probation_acknowledge:true});
 expect(container.textContent).toContain('does not mean you agree');
 expect(button('Acknowledge probation review').disabled).toBe(true);
 await act(async()=>container.querySelector('input[type="checkbox"]').click());
 await change(container.querySelector('textarea'),'Received; I disagree with a rating');
 await act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 expect(api.submitReviewAssessment).toHaveBeenCalledWith('probation','acknowledge',expect.objectContaining({acknowledged:true,comments:'Received; I disagree with a rating'}));
});
