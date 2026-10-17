import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SolverWorkflow from './SolverWorkflow';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
const workflow = values => ({ tasks: [], verification: [], assessments: [], can_manage: false, can_upload: false, ...values });
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getSolverCompetencies.mockResolvedValue({ data: { items: [], legacy_notice: 'Legacy categories are not verified certifications.' } });
  api.getSolverWorkflow.mockResolvedValue({ data: workflow() }); api.getSolverDocuments.mockResolvedValue({ data: [] });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async (accountId = 'account') => { await act(async () => root.render(<SolverWorkflow solverId="one" accountId={accountId} />)); };

test('self view shows truthful empty states without verification or upload controls', async () => {
  await render(); expect(container.textContent).toContain('No assessment results recorded'); expect(container.textContent).toContain('No documents shared');
  expect(container.textContent).not.toContain('Record verification'); expect(container.textContent).not.toContain('Upload Solver document');
});

test('manager can review results and verification but cannot upload HR files', async () => {
  api.getSolverWorkflow.mockResolvedValue({ data: workflow({ can_manage: true, assessments: [{ id: 'result', form_id: 'form-03', score: 8, passed: true }] }) });
  api.reviewSolverAssessment.mockResolvedValue({ data: { reviewed: true } });
  await render(); expect(container.textContent).toContain('Record verification'); expect(container.textContent).not.toContain('Upload Solver document');
  const button = [...container.querySelectorAll('button')].find(item => item.textContent === 'Record review of existing result');
  await act(async () => button.click()); expect(api.reviewSolverAssessment).toHaveBeenCalledWith('one', 'result');
});

test('HR upload defaults to confidential HR-only and documents stay in the Solver context', async () => {
  api.getSolverWorkflow.mockResolvedValue({ data: workflow({ can_manage: true, can_upload: true }) });
  await render(); expect(container.textContent).toContain('Upload Solver document');
  expect(container.querySelector('option[value="hr_only"]').selected).toBe(true);
  expect(api.getSolverDocuments).toHaveBeenCalledWith('one');
});

test('workflow failure has retry and no stale verification actions', async () => {
  api.getSolverWorkflow.mockRejectedValue(new Error('offline')); await render();
  expect(container.querySelector('[role="alert"]')).toBeTruthy(); expect(container.textContent).not.toContain('Record verification');
  expect([...container.querySelectorAll('button')].some(button => button.textContent === 'Retry')).toBe(true);
});

test('account switch hides prior confidential workflow while loading', async () => {
  api.getSolverWorkflow.mockResolvedValue({ data: workflow({ can_manage: true, tasks: [{ id: 'task', title: 'Prior private task' }] }) });
  await render(); expect(container.textContent).toContain('Prior private task');
  api.getSolverWorkflow.mockReturnValue(new Promise(() => {})); await render('other-account');
  expect(container.textContent).not.toContain('Prior private task'); expect(container.textContent).not.toContain('Record verification');
});


test('profile shows documented qualifications even without a framework assignment', async () => {
  api.getSolverCompetencies.mockResolvedValue({ data: { items: [{ id: 'licence', kind: 'Qualification', name: 'Driving licence', status: 'Verified' }], legacy_notice: 'Legacy categories are not verified certifications.' } });
  await render(); expect(container.textContent).toContain('Driving licence'); expect(container.textContent).toContain('Verified');
});
