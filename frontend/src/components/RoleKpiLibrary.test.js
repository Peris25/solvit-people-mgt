import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RoleKpiLibrary from './RoleKpiLibrary';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
const row=()=>({role_id:'synthetic-role',name:'Synthetic role',scope:'Annual',goals:[{id:'one',objective:'Objective',metric:'Measure',target:'95%',target_value:95,weight:100,direction:'Higher',unit:'%',data_source:'Verified report',owner:'Synthetic role',group:'',notes:''}],group_weights:{},notes:'',approval_reference:'',source_reference:'Synthetic reference',status:'Draft',version:null,updated_at:null,issues:['Enter approval reference'],has_published_version:false});
beforeEach(()=>{jest.useFakeTimers();container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);api.getRoleKpiLibrary.mockResolvedValue({data:{roles:[row()]}});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.clearAllTimers();jest.useRealTimers();jest.resetAllMocks();});
const render=async()=>{await act(async()=>root.render(<RoleKpiLibrary />));};
const change=async(input,value)=>{await act(async()=>{Object.getOwnPropertyDescriptor(input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));});};
const click=async(text)=>{await act(async()=>[...container.querySelectorAll('button')].find(b=>b.textContent===text).click());};
const saved=(entry,version='v1')=>({data:{...entry,version,status:'Draft',issues:[],updated_at:'2026-11-12T10:00:00Z',has_published_version:false}});

test('HR edits an incomplete draft and it restores after remount',async()=>{
 await render();await change(container.querySelector('[aria-label="Target description 1"]'),'');
 api.saveRoleKpis.mockImplementation((id,body)=>Promise.resolve(saved(body.entry)));
 await click('Save draft');
 expect(api.saveRoleKpis).toHaveBeenCalledWith('synthetic-role',expect.objectContaining({action:'draft',entry:expect.objectContaining({goals:[expect.objectContaining({target:''})]})}));
 expect(container.textContent).toContain('Draft saved.');
 const result=api.saveRoleKpis.mock.calls[0][1].entry;
 api.getRoleKpiLibrary.mockResolvedValue({data:{roles:[saved(result).data]}});
 await act(async()=>root.unmount());root=createRoot(container);await render();
 expect(container.querySelector('[aria-label="Target description 1"]').value).toBe('');
});

test('changes automatically save as drafts after typing stops',async()=>{
 await render();api.saveRoleKpis.mockImplementation((id,body)=>Promise.resolve(saved(body.entry)));
 await change(container.querySelector('[aria-label="Role name"]'),'Updated role');
 await act(async()=>jest.advanceTimersByTime(1300));
 expect(api.saveRoleKpis).toHaveBeenCalledTimes(1);
 expect(api.saveRoleKpis.mock.calls[0][1].action).toBe('draft');
 expect(container.textContent).toContain('Draft saved.');
});

test('approval reference is editable and publication failures retain input',async()=>{
 await render();await change(container.querySelector('[aria-label="KPI approval reference"]'),'MD approval reference');
 api.saveRoleKpis.mockRejectedValue({response:{status:422,data:{detail:'Cannot publish: weights must total 100%.'}}});
 await click('Publish approved KPIs');
 expect(api.saveRoleKpis.mock.calls[0][1].action).toBe('publish');
 expect(container.textContent).toContain('Cannot publish: weights must total 100%.');
 expect(container.querySelector('[aria-label="KPI approval reference"]').value).toBe('MD approval reference');
});

test('concurrent edits are kept and require explicit discard before reload',async()=>{
 await render();await change(container.querySelector('[aria-label="Role name"]'),'My unsaved edit');
 api.saveRoleKpis.mockRejectedValue({response:{status:409,data:{detail:'Another HR user changed this role.'}}});
 await click('Save draft');
 expect(container.querySelector('[aria-label="Role name"]').value).toBe('My unsaved edit');
 expect([...container.querySelectorAll('button')].find(b=>b.textContent==='Save draft').disabled).toBe(true);
 api.getRoleKpiLibrary.mockResolvedValue({data:{roles:[{...row(),name:'Latest role',version:'latest'}]}});
 await click('Discard my edits and load latest');
 expect(container.querySelector('[aria-label="Role name"]').value).toBe('Latest role');
});

test('soft server errors cannot claim a successful save',async()=>{
 await render();api.saveRoleKpis.mockResolvedValue({data:null,_serverError:true});
 await click('Save draft');expect(container.textContent).toContain('Save could not be confirmed');
 expect(container.textContent).not.toContain('Draft saved.');
});


test('typing during a save is not overwritten or falsely reported as saved',async()=>{
 await render();let finish;
 api.saveRoleKpis.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 await change(container.querySelector('[aria-label="Role name"]'),'First edit');
 await click('Save draft');
 const submitted=api.saveRoleKpis.mock.calls[0][1].entry;
 await change(container.querySelector('[aria-label="Role name"]'),'Newer edit');
 await act(async()=>finish(saved(submitted)));
 expect(container.querySelector('[aria-label="Role name"]').value).toBe('Newer edit');
 expect(container.textContent).toContain('Newer edits are not saved yet.');
 api.saveRoleKpis.mockImplementation((id,body)=>Promise.resolve(saved(body.entry,'v2')));
 await act(async()=>jest.advanceTimersByTime(1300));
 expect(api.saveRoleKpis.mock.calls[1][1].expected_version).toBe('v1');
 expect(container.textContent).toContain('Draft saved.');
});
