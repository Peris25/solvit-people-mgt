import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import Recruitment from './Recruitment';
import Policies from './Policies';
import Layout from '../components/Layout';
import {useAuth} from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../context/NotificationContext', () => ({useNotifications: () => ({unreadCount:0})}));
jest.mock('react-router-dom', () => ({Outlet: () => <div>Route content</div>, Navigate: () => null, Link: ({children}) => <a>{children}</a>}));
jest.mock('../components/Sidebar', () => ({collapsed,onToggle}) => <button data-testid="navigation-toggle" onClick={() => onToggle(!collapsed)}>{collapsed ? 'Collapsed' : 'Expanded'}</button>);
jest.mock('../components/AIAgent', () => () => null);
jest.mock('../components/FirstLoginTour', () => () => null);
jest.mock('../components/RequiredPasswordChange', () => () => <div>Password required</div>);
jest.mock('./MfaSecurity', () => () => <div>MFA required</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container,root;
beforeEach(() => {
 container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
 useAuth.mockReturnValue({user:{id:'qa',role:'hr_admin'}});
 api.getPolicies.mockResolvedValue({data:[]});
 window.matchMedia=jest.fn().mockReturnValue({matches:false});
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();jest.resetAllMocks();});
const render=async component=>{await act(async()=>root.render(component));};
const click=async element=>{await act(async()=>element.click());};
const textButton=text=>[...container.querySelectorAll('button')].find(x=>x.textContent.includes(text));
const input=async(element,value)=>{await act(async()=>{const proto=element.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(element,value);element.dispatchEvent(new Event('input',{bubbles:true}));});};

test('recruitment shows offer, closed and legacy buckets, and reconciles counts',async()=>{
 api.getRecruitmentPipeline.mockResolvedValue({data:{'Stage 1: Competency Test':{count:1,candidates:[{id:'a',full_name:'A'}]},'Offer Made':{count:1,candidates:[{id:'b',full_name:'Offer candidate'}]},'Rejected':{count:1,candidates:[{id:'c',full_name:'Closed candidate'}]},'Legacy intake':{count:1,candidates:[{id:'d',full_name:'Legacy candidate'}]}}});
 await render(<Recruitment/>);
 expect(container.textContent).toContain('4 total candidates');expect(container.textContent).toContain('1 in closed or accepted stages');
 for(const name of ['Offer candidate','Closed candidate','Legacy candidate'])expect(container.textContent).toContain(name);
 expect(container.querySelectorAll('button').length).toBeGreaterThan(1);
});
test('read-only managers cannot see recruitment transition buttons',async()=>{
 useAuth.mockReturnValue({user:{role:'line_manager'}});api.getRecruitmentPipeline.mockResolvedValue({data:{'Stage 1: Competency Test':{count:1,candidates:[{id:'a',full_name:'A'}]}}});
 await render(<Recruitment/>);expect(textButton('Next')).toBeUndefined();expect(textButton('Reject')).toBeUndefined();
});
test('recruitment load failures show a retryable error',async()=>{
 api.getRecruitmentPipeline.mockRejectedValueOnce(new Error('Private internal detail')).mockResolvedValueOnce({data:{}});
 await render(<Recruitment/>);expect(container.querySelector('[role="alert"]').textContent).toContain('could not be loaded');expect(container.textContent).not.toContain('Private internal detail');
 await click(textButton('Retry'));expect(container.querySelector('[role="alert"]')).toBeNull();
});
test.each([true,false])('navigation starts collapsed only on a narrow viewport: %s',async narrow=>{
 window.matchMedia.mockReturnValue({matches:narrow});await render(<Layout/>);
 expect(container.querySelector('[data-testid="navigation-toggle"]').textContent).toBe(narrow?'Collapsed':'Expanded');
 await click(container.querySelector('[data-testid="navigation-toggle"]'));expect(container.querySelector('[data-testid="navigation-toggle"]').textContent).toBe(narrow?'Expanded':'Collapsed');
});
test('mandatory password and MFA routing remain intact',async()=>{
 useAuth.mockReturnValue({user:{must_change_password:true}});await render(<Layout/>);expect(container.textContent).toContain('Password required');
 useAuth.mockReturnValue({user:{mfa_required:true,mfa_verified:false}});await render(<Layout/>);expect(container.textContent).toContain('MFA required');
});
test('blank policy cannot be acknowledged and card supports keyboard access',async()=>{
 api.getPolicies.mockResolvedValue({data:[{id:'blank',title:'Blank handbook',status:'Active',version:'1',acknowledgement_available:false}]});
 await render(<Policies/>);const card=container.querySelector('[data-testid="policy-blank"]');expect(card.getAttribute('role')).toBe('button');
 await act(async()=>card.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})));
 expect(container.querySelector('[data-testid="acknowledge-btn"]').disabled).toBe(true);expect(container.textContent).toContain('HR must publish readable content');expect(api.acknowledgePolicy).not.toHaveBeenCalled();
});
test('failed policy upload stays open and retries the same draft before publication',async()=>{
 api.createPolicy.mockResolvedValue({data:{id:'saved-draft'}});api.updatePolicy.mockResolvedValue({data:{id:'saved-draft'}});api.uploadPolicyFile.mockRejectedValueOnce(new Error('Scanner unavailable')).mockResolvedValueOnce({data:{}});
 await render(<Policies/>);await click(container.querySelector('[data-testid="add-policy-btn"]'));
 const form=container.querySelector('form');await input(form.querySelector('input[required]'),'Synthetic policy');await input(form.querySelector('textarea[required]'),'Description');
 const file=form.querySelector('input[type="file"]');await act(async()=>{Object.defineProperty(file,'files',{value:[new File(['synthetic'],'policy.pdf',{type:'application/pdf'})]});file.dispatchEvent(new Event('change',{bubbles:true}));});
 await act(async()=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 expect(container.querySelector('form')).not.toBeNull();expect(container.textContent).toContain('saved draft is retained');expect(api.createPolicy).toHaveBeenCalledTimes(1);expect(api.updatePolicy).not.toHaveBeenCalled();
 await act(async()=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 expect(api.createPolicy).toHaveBeenCalledTimes(1);expect(api.updatePolicy).toHaveBeenCalledWith('saved-draft',{status:'Active'});expect(container.querySelector('form')).toBeNull();
});
test('publishing without a file or full text does not create metadata',async()=>{
 await render(<Policies/>);await click(container.querySelector('[data-testid="add-policy-btn"]'));
 await act(async()=>container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 expect(api.createPolicy).not.toHaveBeenCalled();expect(container.textContent).toContain('Attach a readable document');
});
