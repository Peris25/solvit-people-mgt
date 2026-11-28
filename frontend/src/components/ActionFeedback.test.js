import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import ActionButton from './ActionButton';
import FormValidationFeedback from './FormValidationFeedback';
import ErrorToast from './ErrorToast';
jest.mock('react-router-dom',()=>({useLocation:()=>({key:'screen'})}));
global.IS_REACT_ACT_ENVIRONMENT=true;
let root,container;
beforeEach(()=>{container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();});
const render=async node=>{await act(async()=>root.render(node));};
test('blocked action explains its exact prerequisite through visible associated text',async()=>{
 await render(<ActionButton disabled disabledReason="Add four more colleagues before submitting.">Submit</ActionButton>);
 const button=container.querySelector('button');expect(button.disabled).toBe(true);
 expect(document.getElementById(button.getAttribute('aria-describedby')).textContent).toContain('four more colleagues');
 await render(<ActionButton disabled={false} disabledReason="Add four more colleagues before submitting.">Submit</ActionButton>);
 expect(container.querySelector('.action-feedback-reason')).toBeNull();expect(container.querySelector('button').disabled).toBe(false);
});
test('native form validation names missing fields, focuses the first, and clears corrected errors without stealing focus',async()=>{
 await render(<><FormValidationFeedback/><form onSubmit={event=>event.preventDefault()}><label>Work email<input type="email" required/></label><label><span>Reason for request</span><textarea required/></label><button>Send request</button></form></>);
 await act(async()=>{expect(container.querySelector('form').checkValidity()).toBe(false);});
 expect(container.querySelector('[role="alert"]').textContent).toContain('Complete Work email.');
 expect(container.querySelector('[role="alert"]').textContent).toContain('Complete Reason for request.');
 expect(document.activeElement).toBe(container.querySelector('input'));
 const input=container.querySelector('input'),reason=container.querySelector('textarea');
 await act(async()=>{input.value='invalid';input.dispatchEvent(new Event('input',{bubbles:true}));});
 expect(container.querySelector('[role="alert"]').textContent).toContain('valid email address');
 await act(async()=>{reason.focus();reason.value='A reason';reason.dispatchEvent(new Event('input',{bubbles:true}));});
 expect(document.activeElement).toBe(reason);
 expect(container.querySelector('[role="alert"]').textContent).not.toContain('Complete Reason for request.');
 await act(async()=>{input.value='person@example.test';input.dispatchEvent(new Event('input',{bubbles:true}));});
 expect(container.querySelector('[role="alert"]')).toBeNull();
});
test('required radio groups have one useful message rather than an error for each option',async()=>{
 await render(<><FormValidationFeedback/><form><fieldset><legend>Integrity score</legend>{[0,1,2].map(value=><label key={value}><input type="radio" required name="integrity" value={value}/>{value}</label>)}</fieldset><button>Submit</button></form></>);
 await act(async()=>{expect(container.querySelector('form').checkValidity()).toBe(false);});
 expect(container.querySelectorAll('.form-validation-summary li')).toHaveLength(1);
 expect(container.querySelector('[role="alert"]').textContent).toContain('Complete Integrity score.');
});
test('action error remains readable until dismissed and does not show internal URLs or status codes',async()=>{
 await render(<ErrorToast/>);
 await act(async()=>window.dispatchEvent(new CustomEvent('solvit:server-error',{detail:{message:'Enter a decision reason before approving.',status:500,url:'/internal/private'}})));
 expect(container.querySelector('[role="alert"]').textContent).toContain('decision reason');
 expect(container.textContent).not.toContain('/internal/private');expect(container.textContent).not.toContain('500');
 await act(async()=>container.querySelector('[aria-label="Dismiss action message"]').click());expect(container.querySelector('[role="alert"]')).toBeNull();
});
