import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import LnD from './LnD';
import { TrainingCatalogue, TrainingCompletion } from '../components/LearningWorkflows';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ MemoryRouter: ({children}) => <>{children}</>, Link: ({to,children}) => <a href={to}>{children}</a>, useSearchParams: () => [new URLSearchParams(), jest.fn()] }));
jest.mock('../components/EmployeePicker', () => () => <div>Employee picker</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container=document.createElement('div'); document.body.appendChild(container); root=createRoot(container);
  useAuth.mockReturnValue({user:{role:'employee',employee_id:'staff'}});
  api.getTrainingRequests.mockResolvedValue({data:[]}); api.getTrainingProgrammes.mockResolvedValue({data:[]});
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render=async element => { await act(async () => root.render(<MemoryRouter>{element}</MemoryRouter>)); };
const click=async text => { const target=[...container.querySelectorAll('button')].find(b=>b.textContent===text); expect(target).toBeTruthy(); await act(async()=>target.click()); };
const change=async(input,value)=>{ await act(async()=>{ Object.getOwnPropertyDescriptor(input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(input,value); input.dispatchEvent(new Event('change',{bubbles:true})); input.dispatchEvent(new Event('input',{bubbles:true})); }); };
const submit=async form=>{ await act(async()=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))); };
const training=extra=>({id:'training',employee_id:'staff',employee_name:'Synthetic Ada',training_name:'Agreed learning',status:'Approved',...extra});
test('empty learning has no fabricated records and preserves IDP and skills navigation',async()=>{
 await render(<LnD/>); expect(container.textContent).toContain('No learning records'); expect(container.textContent).toContain('IDP Plans'); expect(container.textContent).toContain('Skills Matrix');
});
test('employee list uses authorized names and capability flags rather than role assumptions',async()=>{
 api.getTrainingRequests.mockResolvedValue({data:[training()]}); await render(<LnD/>);
 expect(container.textContent).toContain('Synthetic Ada'); expect(container.textContent).toContain('Agreed learning'); expect(container.textContent).not.toContain('Verify requirements and completion');
});
test('completed filter shows historical completion without pending requests',async()=>{
 api.getTrainingRequests.mockResolvedValue({data:[training({id:'complete',status:'Completed',training_name:'Finished course'}),training({id:'pending',status:'Pending_Manager_Approval',training_name:'Pending course'})]});
 await render(<LnD/>); await click('Assigned learning & history'); await change(container.querySelector('select'),'completed'); expect(container.textContent).toContain('Finished course'); expect(container.textContent).not.toContain('Pending course');
});
test('missing employee link cannot fall back to account ID when requesting',async()=>{
 useAuth.mockReturnValue({user:{id:'account-id',role:'employee'}}); await render(<LnD/>); await click('+ Request Training'); expect(container.querySelector('[data-testid="submit-training-btn"]').disabled).toBe(true);
});
test('loading failure and retry recover cleanly',async()=>{
 api.getTrainingRequests.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({data:[]}); await render(<LnD/>); expect(container.querySelector('[role="alert"]')).toBeTruthy(); await click('Retry'); expect(container.querySelector('[role="alert"]')).toBeNull();
});
test('catalogue ordinary staff cannot create or assign programmes',async()=>{
 api.getTrainingProgrammes.mockResolvedValue({data:[{id:'course',title:'Published course',kind:'Course',status:'Published'}]}); api.createTrainingRequest.mockResolvedValue({}); const updated=jest.fn();
 await render(<TrainingCatalogue user={{role:'employee',employee_id:'staff'}} onUpdated={updated}/>); expect(container.textContent).not.toContain('Create training catalogue item (HR)'); await click('Request this training'); expect(api.createTrainingRequest).toHaveBeenCalledWith({employee_id:'staff',programme_id:'course',business_justification:'Requested participation in published training'}); expect(updated).toHaveBeenCalled();
});
test('HR can configure catalogue and assignment requires an employee',async()=>{
 api.getTrainingProgrammes.mockResolvedValue({data:[{id:'course',title:'Published course',kind:'Course',status:'Published'}]}); await render(<TrainingCatalogue user={{role:'hr_admin'}} onUpdated={jest.fn()}/>);
 expect(container.textContent).toContain('Create training catalogue item (HR)'); expect([...container.querySelectorAll('button')].find(b=>b.textContent==='Assign to employee').disabled).toBe(true);
});
test('owner submits evidence for verification and cannot claim a verified final status',async()=>{
 api.completeTraining.mockResolvedValue({}); const updated=jest.fn(); await render(<TrainingCompletion training={training({can_submit_completion:true})} onUpdated={updated}/>);
 await change(container.querySelector('input[type="date"]'),'2026-10-01'); await change(container.querySelector('textarea'),'Attended agreed sessions'); await submit(container.querySelector('form'));
 expect(api.completeTraining).toHaveBeenCalledWith('training',{action:'submit',completed_on:'2026-10-01',evidence:'Attended agreed sessions'}); expect(updated).toHaveBeenCalled(); expect(container.textContent).not.toContain('Verify requirements and completion');
});
test('completion evidence selector excludes documents without download permission',async()=>{
 api.getEmployeeDocuments.mockResolvedValue({data:[{id:'private',title:'Hidden document',download_allowed:false},{id:'allowed',title:'Approved certificate',download_allowed:true}]});
 await render(<TrainingCompletion training={training({can_submit_completion:true,evidence_required:true})} onUpdated={jest.fn()}/>); await click('Load authorized documents'); expect(container.textContent).toContain('Approved certificate'); expect(container.textContent).not.toContain('Hidden document'); expect(container.querySelector('select').required).toBe(true);
});
test('HR verification and return use separate audited actions',async()=>{
 api.completeTraining.mockResolvedValue({}); await render(<TrainingCompletion training={training({can_verify_completion:true})} onUpdated={jest.fn()}/>); await click('Verify requirements and completion'); expect(api.completeTraining).toHaveBeenCalledWith('training',{action:'verify',requirements_met:true});
 await change(container.querySelector('input'),'Additional evidence needed'); await click('Return completion evidence'); expect(api.completeTraining).toHaveBeenCalledWith('training',{action:'return',reason:'Additional evidence needed'});
});
test('rejected completion leaves the workflow unchanged and shows server reason',async()=>{
 api.completeTraining.mockRejectedValue({response:{data:{detail:'Document is not authorized'}}}); const updated=jest.fn(); await render(<TrainingCompletion training={training({can_verify_completion:true})} onUpdated={updated}/>); await click('Verify requirements and completion'); expect(container.querySelector('[role="alert"]').textContent).toContain('Document is not authorized'); expect(updated).not.toHaveBeenCalled();
});
