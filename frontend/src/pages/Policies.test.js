import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import Policies from './Policies';
import * as api from '../services/api';
import {useAuth} from '../context/AuthContext';
jest.mock('../services/api');jest.mock('../context/AuthContext');
let mockPolicySearch='';
jest.mock('react-router-dom',()=>({useSearchParams:()=>[new URLSearchParams(mockPolicySearch)]}));
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
beforeEach(()=>{mockPolicySearch='';container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);useAuth.mockReturnValue({user:{id:'staff',role:'employee'}});api.getPolicies.mockResolvedValue({data:[]});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.resetAllMocks();});
const render=()=>act(async()=>root.render(<Policies/>));

test('published policy files are shown to the authorized employee',async()=>{
 api.getPolicies.mockResolvedValue({data:[{id:'handbook',title:'Synthetic handbook',status:'Active',category:'Other',version:'2',file_name:'handbook.pdf',has_attachment:true,acknowledgement_available:true}]});
 await render();await act(async()=>container.querySelector('[data-testid="policy-handbook"]').click());
 expect(container.textContent).toContain('handbook.pdf');
 expect(container.querySelector('[data-testid="ack-signature"]').disabled).toBe(false);
});

test('unavailable library shows retry instead of a false empty category',async()=>{
 api.getPolicies.mockResolvedValue({data:null,_serverError:true});await render();
 expect(container.querySelector('[role="alert"]').textContent).toContain('Retry documents');
 expect(container.textContent).not.toContain('0 documents');
});

test('switching from HR to employee immediately hides the previous policies',async()=>{
 useAuth.mockReturnValue({user:{id:'hr',role:'hr_admin'}});
 api.getPolicies.mockResolvedValueOnce({data:[{id:'draft',title:'Private HR draft',status:'Draft',category:'Other'}]});
 await render();expect(container.textContent).toContain('Private HR draft');
 useAuth.mockReturnValue({user:{id:'staff',role:'employee'}});let finish;
 api.getPolicies.mockReturnValue(new Promise(resolve=>{finish=resolve;}));await render();
 expect(container.textContent).not.toContain('Private HR draft');
 await act(async()=>finish({data:[]}));
});

test('HR can choose the policy audience and employees cannot publish',async()=>{
 await render();expect(container.querySelector('[data-testid="add-policy-btn"]')).toBeNull();
 useAuth.mockReturnValue({user:{id:'hr',role:'hr_admin'}});await render();
 await act(async()=>container.querySelector('[data-testid="add-policy-btn"]').click());
 expect(container.querySelector('#policy-audience').value).toBe('employees');
});

test('a policy notification opens its exact authorized document',async()=>{
 mockPolicySearch='policy=handbook';
 api.getPolicies.mockResolvedValue({data:[{id:'handbook',title:'Synthetic handbook',status:'Active',category:'Other',version:'2',content:'Approved source',acknowledgement_available:true}]});
 await render();expect(container.querySelector('[data-testid="ack-signature"]')).not.toBeNull();
 expect(container.textContent).toContain('Approved source');
});
