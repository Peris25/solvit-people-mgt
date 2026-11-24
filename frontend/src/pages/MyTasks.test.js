import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import MyTasks from './MyTasks';
import * as api from '../services/api';
import {useAuth} from '../context/AuthContext';
jest.mock('../services/api');jest.mock('../context/AuthContext');
const mockNavigate=jest.fn();jest.mock('react-router-dom',()=>({useNavigate:()=>mockNavigate}));
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
beforeEach(()=>{container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);useAuth.mockReturnValue({user:{id:'staff',role:'employee'}});api.getMyTaskQueue.mockResolvedValue({data:{items:[],count:0,errors:[]}});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.resetAllMocks();});
const render=async()=>act(async()=>root.render(<MyTasks/>));
const click=async text=>act(async()=>[...container.querySelectorAll('button')].find(button=>button.textContent===text).click());

test('one table shows assigned work and workflow actions and opens the correct source',async()=>{
 api.getMyTaskQueue.mockResolvedValue({data:{count:2,errors:[],items:[{id:'task:one',reference:'one',kind:'assigned',title:'Assigned work',status:'Pending',can_complete:true},{id:'review:one',reference:'review',kind:'review',title:'Score employee probation',subject:'Synthetic colleague',path:'/performance?review=review',status:'Draft'}]}});
 await render();expect(container.querySelectorAll('tbody tr')).toHaveLength(2);expect(container.textContent).toContain('2 open tasks');
 await click('Open task');expect(mockNavigate).toHaveBeenCalledWith('/performance?review=review');
 expect(api.getMyFormTasks).not.toHaveBeenCalled();expect(api.getPerformanceV3Tasks).not.toHaveBeenCalled();
});

test('request failure offers retry and never announces zero tasks',async()=>{
 api.getMyTaskQueue.mockRejectedValue(new Error('offline'));await render();
 expect(container.querySelector('[role="alert"]').textContent).toContain('could not load');
 expect(container.textContent).not.toContain('No open tasks');
 api.getMyTaskQueue.mockResolvedValue({data:{items:[],count:0,errors:[]}});await click('Retry tasks');
 expect(container.textContent).toContain('No open tasks assigned to you');
});

test('partial failure keeps available tasks visible without claiming the list is complete',async()=>{
 api.getMyTaskQueue.mockResolvedValue({data:{count:null,errors:['Forms'],items:[{id:'task:one',kind:'assigned',title:'Available work',status:'Pending'}]}});
 await render();expect(container.textContent).toContain('Available work');expect(container.textContent).toContain('may be incomplete');
 expect(container.textContent).not.toContain('No open tasks');
});

test('loading task data is independent of dashboard snapshot and slow unrelated APIs',async()=>{
 let finish;api.getMyTaskQueue.mockReturnValue(new Promise(resolve=>{finish=resolve;}));await render();
 expect(container.textContent).toContain('Loading your assigned tasks');expect(api.getStaffHome).not.toHaveBeenCalled();
 await act(async()=>finish({data:{items:[],count:0,errors:[]}}));expect(container.textContent).toContain('No open tasks');
});

test('returning to the tab refreshes the shared task source',async()=>{
 await render();await act(async()=>window.dispatchEvent(new Event('focus')));expect(api.getMyTaskQueue).toHaveBeenCalledTimes(2);
});

test('completing an ordinary task uses its real reference then reloads the shared queue',async()=>{
 api.getMyTaskQueue.mockResolvedValueOnce({data:{items:[{id:'assigned:one',reference:'one',kind:'assigned',title:'My work',status:'Pending',can_complete:true}],count:1,errors:[]}}).mockResolvedValue({data:{items:[],count:0,errors:[]}});
 api.updateTask.mockResolvedValue({data:{id:'one',status:'Completed'}});
 await render();await click('Mark complete');
 expect(api.updateTask).toHaveBeenCalledWith('one',{status:'Completed'});
 expect(api.getMyTaskQueue).toHaveBeenCalledTimes(2);expect(container.textContent).toContain('No open tasks');
});
