import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PublicSolverAssessment from './PublicSolverAssessment';
import SolverApplicantInbox from './SolverApplicantInbox';
import PublicSolverApplications from '../components/PublicSolverApplications';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../context/AuthContext');
jest.mock('../services/api');
jest.mock('../components/Layout', () => () => <div>Protected workspace</div>);
global.IS_REACT_ACT_ENVIRONMENT = true;
const bank={version:'test-v1',sections:[{id:'intro',title:'About you',questions:[{id:'name',label:'Name of Applicant',type:'text',required:true},{id:'photos',label:'Photo question',type:'choice',required:true,availability:'awaiting_source_images'}]}]};
let root,container;
beforeEach(() => {
  container=document.createElement('div'); document.body.appendChild(container); root=createRoot(container);
  useAuth.mockReturnValue({user:null});
  api.getPublicSolverQuestionnaire.mockResolvedValue({data:bank}); api.getPublicSolverChallenge.mockResolvedValue({data:{token:'opaque-proof',question:'What is 2 + 3?'}});
  api.submitPublicSolverAssessment.mockResolvedValue({data:{reference:'application-reference'}});
  window.history.replaceState({},'', '/solver-assessments');
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render=async element => { await act(async () => root.render(element)); };
const click=async text => { await act(async () => [...container.querySelectorAll('button')].find(b => b.textContent===text).click()); };
const change=async (node,value) => { await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value); node.dispatchEvent(new Event('input',{bubbles:true})); }); };

test('anonymous applicants see questionnaire without accessing private assessment APIs', async () => {
  await render(<PublicSolverAssessment />);
  expect(container.textContent).toContain('Name of Applicant');
  expect(container.textContent).toContain('awaiting publication');
  expect(api.getSolverAssessmentAttempts).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain('Protected workspace');
});

test('signed-in staff see the same standalone applicant questionnaire', async () => {
  useAuth.mockReturnValue({user:{id:'hr',role:'hr_admin'}});
  await render(<PublicSolverAssessment />); expect(container.textContent).not.toContain('Protected workspace');
  expect(container.textContent).toContain('Name of Applicant');
  window.history.replaceState({},'', '/solver-assessments?new=1');
  await render(<PublicSolverAssessment />); expect(container.textContent).toContain('Name of Applicant');
});

test('submission sends answers and consent, then displays receipt without creating an account', async () => {
  await render(<PublicSolverAssessment />);
  await change(container.querySelector('[aria-label="Name of Applicant"]'),'Synthetic Applicant');
  await change(container.querySelector('[inputmode="numeric"]'),'5');
  await act(async () => container.querySelector('[type="checkbox"]').click());
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(api.submitPublicSolverAssessment).toHaveBeenCalledWith(expect.objectContaining({answers:{name:'Synthetic Applicant'},consent:true,challenge_token:'opaque-proof'}));
  expect(container.textContent).toContain('Assessment received'); expect(container.textContent).toContain('application-reference');
  expect(api.provisionEmployeeAccount).not.toHaveBeenCalled();
});

test('verification refresh preserves answers and submission errors are retryable', async () => {
  api.submitPublicSolverAssessment.mockRejectedValue({response:{data:{detail:'Verification expired'}}});
  await render(<PublicSolverAssessment />);
  await change(container.querySelector('[aria-label="Name of Applicant"]'),'Preserved answer');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Verification expired');
  await click('Refresh verification');
  expect(container.querySelector('[aria-label="Name of Applicant"]').value).toBe('Preserved answer');
});

test('HR can inspect applicant answers without activating a Solver', async () => {
  api.getPublicSolverApplications.mockResolvedValue({data:[{id:'one',full_name:'Synthetic Applicant',status:'Submitted',submitted_at:'2026-11-03T10:00:00Z'}]});
  api.getPublicSolverApplication.mockResolvedValue({data:{id:'one',full_name:'Synthetic Applicant',status:'Submitted',sections:bank.sections,answers:{name:'Synthetic Applicant'},pending_questions:['photos']}});
  await render(<PublicSolverApplications />); await click('View answers');
  expect(container.textContent).toContain('source photo question is pending');
  expect(container.querySelector('[aria-label="Applicant answers"]')).not.toBeNull();
  expect(api.activateSolver).not.toHaveBeenCalled();
});


test('private inbox denies non-HR users before loading applicant records', async () => {
  useAuth.mockReturnValue({ user: { id: 'employee', role: 'employee' } });
  await render(<SolverApplicantInbox />);
  expect(container.textContent).toContain('HR access is required');
  expect(api.getPublicSolverApplications).not.toHaveBeenCalled();
});
