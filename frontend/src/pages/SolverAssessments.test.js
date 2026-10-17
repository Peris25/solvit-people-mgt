import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SolverAssessments from './SolverAssessments';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ Link: ({ to, children }) => <a href={to}>{children}</a> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const caps = values => ({ can_assign: false, can_configure: false, can_publish: false, is_solver: true, ...values });
const attempt = values => ({ id: 'attempt', title: 'Synthetic assigned assessment', status: 'Assigned', subject_solver_id: 'one', configuration_version: 1,
  due_at: '2099-10-01T12:00:00Z', parts: {}, answers: {}, revision: 0,
  configuration: { time_limits: { A: 10, B: 15 }, sections: [{ id: 'a', title: 'Part A', part: 'A', questions: [] }, { id: 'b', title: 'Part B', part: 'B', questions: [] }] }, ...values });
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({ user: { id: 'solver-account', role: 'solver' } });
  api.getSolverAssessmentCapabilities.mockResolvedValue({ data: caps() });
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [] });
  api.getSolverAssessmentConfigurations.mockResolvedValue({ data: [] });
  api.getSolverAssessmentOptions.mockResolvedValue({ data: { assessors: [] } }); api.getSolvers.mockResolvedValue({ data: [] });
  api.getSolverDocuments.mockResolvedValue({ data: [] });
  api.getSolverCompetencies.mockResolvedValue({ data: { items: [], legacy_notice: 'Legacy categories are not verified certifications.' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<SolverAssessments />)); };
const click = async text => { const target = [...container.querySelectorAll('button')].find(button => button.textContent === text); expect(target).toBeTruthy(); await act(async () => target.click()); };
const change = async (input, value) => { await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === 'SELECT' ? HTMLSelectElement.prototype : input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('change', { bubbles: true })); input.dispatchEvent(new Event('input', { bubbles: true })); }); };

test('Solver sees an honest empty state without bank or assignment controls', async () => {
  await render(); expect(container.textContent).toContain('No assessments recorded'); expect(container.textContent).not.toContain('Open settings editor');
  expect(api.getSolverAssessmentConfigurations).not.toHaveBeenCalled(); expect(api.getSolvers).not.toHaveBeenCalled();
});

test('HR settings start empty with no invented threshold or question content', async () => {
  useAuth.mockReturnValue({ user: { id: 'hr', role: 'hr_admin' } }); api.getSolverAssessmentCapabilities.mockResolvedValue({ data: caps({ can_configure: true, can_publish: true, can_assign: true, is_solver: false }) });
  await render(); await click('Open settings editor');
  expect(container.textContent).toContain('No live questions, weights or pass marks');
  const passLabel = [...container.querySelectorAll('label')].find(label => label.textContent.includes('Approved pass mark'));
  expect(passLabel.querySelector('input').value).toBe(''); expect(container.textContent).not.toContain('Synthetic choice');
});

test('technical configurator cannot publish or assign through UI capabilities', async () => {
  useAuth.mockReturnValue({ user: { id: 'technical', role: 'line_manager' } });
  api.getSolverAssessmentCapabilities.mockResolvedValue({ data: caps({ can_configure: true, is_solver: false }) });
  api.getSolverAssessmentConfigurations.mockResolvedValue({ data: [{ id: 'draft', title: 'Approved draft', version: 1, status: 'Draft', publication_state: 'Ready', settings: {} }] });
  await render(); expect(container.textContent).toContain('Open settings editor'); expect(container.textContent).not.toContain('Publish approved version'); expect(container.textContent).not.toContain('Assign an approved assessment');
});

test('unstarted Parts A/B disclose no questions or result and Part B is gated', async () => {
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt()] }); await render(); await click('Synthetic assigned assessmentVersion 1 / AssignedDeadline: ' + new Date('2099-10-01T12:00:00Z').toLocaleString());
  expect(container.textContent).toContain('Results will be visible after authorized release');
  const startB = [...container.querySelectorAll('button')].find(button => button.textContent === 'Start Part B'); expect(startB.disabled).toBe(true);
});

test('starting a component sends the current revision and assigned record only', async () => {
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt()] }); api.progressSolverAssessment.mockResolvedValue({ data: attempt({ revision: 1, status: 'InProgress', parts: { A: { started_at: '2099-10-01T10:00:00Z' } } }) });
  await render(); await act(async () => container.querySelector('section button').click()); await click('Start Part A');
  expect(api.progressSolverAssessment).toHaveBeenCalledWith('attempt', 'A', 'start', { revision: 0 });
});

test('saving progress sends only the active part answers', async () => {
  const row = attempt({ status: 'InProgress', revision: 2, parts: { A: { started_at: '2099-10-01T10:00:00Z' } }, configuration: { time_limits: { A: 10, B: 15 }, sections: [{ id: 'a', title: 'Part A', part: 'A', questions: [{ id: 'a1', label: 'Synthetic response', type: 'text', required: true }] }, { id: 'b', title: 'Part B', part: 'B', questions: [] }] } });
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [row] }); api.progressSolverAssessment.mockResolvedValue({ data: { ...row, revision: 3 } });
  await render(); await act(async () => container.querySelector('section button').click()); await change(container.querySelector('textarea'), 'Saved actual response'); await click('Save Part A progress');
  expect(api.progressSolverAssessment).toHaveBeenCalledWith('attempt', 'A', 'save', { revision: 2, answers: { a1: 'Saved actual response' } });
});

test('released result is visible without exposing scoring or release controls to Solver', async () => {
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt({ status: 'Released', score: 88, outcome: 'Pass' })] }); await render();
  expect(container.textContent).toContain('88'); expect(container.textContent).not.toContain('Submit assessor scoring'); expect(container.textContent).not.toContain('Release approved result');
});

test('assigned assessor gets score controls but cannot release', async () => {
  useAuth.mockReturnValue({ user: { id: 'assessor', role: 'line_manager' } }); api.getSolverAssessmentCapabilities.mockResolvedValue({ data: caps({ is_solver: false }) });
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt({ status: 'AwaitingScoring', can_score: true })] });
  await render(); await act(async () => container.querySelector('section button').click());
  expect(container.textContent).toContain('Submit assessor scoring'); expect(container.textContent).not.toContain('Release approved result'); expect(container.textContent).not.toContain('Record documented verification');
});

test('loading denial clears records and provides a useful retry', async () => {
  api.getSolverAssessmentCapabilities.mockRejectedValue(new Error('denied')); await render();
  expect(container.querySelector('[role="alert"]')).toBeTruthy(); expect(container.textContent).not.toContain('Synthetic assigned assessment'); expect(container.textContent).toContain('Retry');
});

test('an account change removes prior private attempts immediately', async () => {
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt()] }); await render(); expect(container.textContent).toContain('Synthetic assigned assessment');
  api.getSolverAssessmentCapabilities.mockReturnValue(new Promise(() => {})); useAuth.mockReturnValue({ user: { id: 'other-account', role: 'solver' } }); await render();
  expect(container.textContent).not.toContain('Synthetic assigned assessment');
});

test('successive draft saves create versions of the same bank', async () => {
  useAuth.mockReturnValue({ user: { id: 'hr', role: 'hr_admin' } }); api.getSolverAssessmentCapabilities.mockResolvedValue({ data: caps({ can_configure: true, can_publish: true, can_assign: true, is_solver: false }) });
  api.saveSolverAssessmentConfiguration.mockResolvedValueOnce({ data: { id: 'first-version' } }).mockResolvedValueOnce({ data: { id: 'second-version' } });
  await render(); await click('Open settings editor');
  const title = [...container.querySelectorAll('label')].find(label => label.textContent === 'Assessment title ');
  await change(title.querySelector('input'), 'Approved bank');
  const submit = async () => { await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); };
  await submit(); await submit();
  expect(api.saveSolverAssessmentConfiguration.mock.calls[0][1]).toBeUndefined();
  expect(api.saveSolverAssessmentConfiguration.mock.calls[1][1]).toBe('first-version');
});


test('released section results are shown alongside the overall score', async () => {
  api.getSolverAssessmentAttempts.mockResolvedValue({ data: [attempt({ status: 'Released', score: 88, outcome: 'Pass', section_scores: [{ id: 'a', part: 'A', title: 'Approved section result', points: 4, maximum: 4, percentage: 100 }] })] });
  await render(); await act(async () => container.querySelector('section button').click());
  expect(container.querySelector('[aria-label="Assessment section results"]').textContent).toContain('Approved section result: 4 / 4');
});
