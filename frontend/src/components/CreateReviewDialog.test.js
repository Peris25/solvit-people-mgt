import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import CreateReviewDialog from './CreateReviewDialog';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT=true;
let container,root;
const employees=[{id:'staff',full_name:'Synthetic Active',lifecycle_state:'Active'},{id:'new',full_name:'Synthetic New',lifecycle_state:'Onboarding'},{id:'probation',full_name:'Synthetic Probation',lifecycle_state:'Probation'}];
beforeEach(()=>{container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.resetAllMocks();});
const change=async(label,value)=>{await act(async()=>{const input=container.querySelector(`[aria-label="${label}"]`);Object.getOwnPropertyDescriptor(input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));});};
const dates=async()=>{for(const [label,value] of [['Review start','2099-01-01'],['Employee submission deadline','2099-01-07'],['Manager submission deadline','2099-01-14'],['HR completion deadline','2099-01-28']])await change(label,value);};
const submit=async()=>act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));

test('one popup sends selected employee, type, all dates and explicit scoring approval',async()=>{
 const saved=jest.fn();api.createReview.mockResolvedValue({data:{id:'review'}});
 await act(async()=>root.render(<CreateReviewDialog employees={employees} onClose={jest.fn()} onCreated={saved}/>));
 await change('Review employee','staff');await dates();await change('Review scoring policy','handbook_frd');
 await act(async()=>container.querySelector('input[type="checkbox"]').click());await submit();
 expect(api.createReview).toHaveBeenCalledWith({employee_id:'staff',cycle_type:'Year_End',cycle_year:2099,starts_on:'2099-01-01',self_due_on:'2099-01-07',manager_due_on:'2099-01-14',review_due_on:'2099-01-28',policy:'handbook_frd',policy_confirmed:true});
 expect(api.configureReviewCycle).not.toHaveBeenCalled();expect(saved).toHaveBeenCalledTimes(1);
});

test('probation filters employees and submits month without weighted scoring settings',async()=>{
 api.createReview.mockResolvedValue({data:{id:'probation-review'}});
 await act(async()=>root.render(<CreateReviewDialog employees={employees} onClose={jest.fn()} onCreated={jest.fn()}/>));
 await change('Review type','Probation');
 expect(container.querySelector('[aria-label="Review employee"]').textContent).not.toContain('Synthetic Active');
 expect(container.querySelector('[aria-label="Review employee"]').textContent).toContain('Synthetic New');
 expect(container.querySelector('[aria-label="Review scoring policy"]')).toBeNull();
 await change('Review employee','new');await change('Probation review month','2');await dates();await submit();
 expect(api.createReview).toHaveBeenCalledWith(expect.objectContaining({employee_id:'new',cycle_type:'Probation',review_month:2}));
 expect(api.createReview.mock.calls[0][0].policy).toBeUndefined();
});

test('server validation keeps populated popup open and never announces false success',async()=>{
 const saved=jest.fn();api.createReview.mockRejectedValue({response:{data:{detail:'Assign a valid line manager'}}});
 await act(async()=>root.render(<CreateReviewDialog employees={employees} onClose={jest.fn()} onCreated={saved}/>));
 await change('Review employee','staff');await dates();await submit();
 expect(container.querySelector('[role="alert"]').textContent).toContain('Assign a valid line manager');
 expect(container.querySelector('[aria-label="Review employee"]').value).toBe('staff');expect(saved).not.toHaveBeenCalled();
});
