import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PublicSolverApply from './PublicSolverApply';
import * as api from '../services/api';

jest.mock('../services/api');
jest.mock('react-router-dom', () => ({ useParams: () => ({ rid: 'synthetic-requisition' }) }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(async () => {
  container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  api.solverIntakePublic.mockResolvedValue({ data: { found: true, status: 'Open', title: 'Synthetic vacancy', counties: ['Nairobi City'] } });
  api.solverIntakeChallenge.mockResolvedValue({ data: { token: 'synthetic', question: '2 + 3?' } });
  await act(async () => root.render(<PublicSolverApply />));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });

test('CV is visibly mandatory and submitting without one never calls the API', async () => {
  expect(container.textContent).not.toContain('(optional)');
  expect(container.querySelector('[data-testid="f-cv"]').required).toBe(true);
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(container.textContent).toContain('Please attach your CV to submit an application.');
  expect(api.solverIntakeApply).not.toHaveBeenCalled();
});

test('an invalid replacement clears the previously selected valid CV', async () => {
  const input = container.querySelector('[data-testid="f-cv"]');
  const choose = async file => {
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })));
  };
  await choose(new File(['synthetic'], 'cv.pdf', { type: 'application/pdf' }));
  expect(container.textContent).toContain('selected: cv.pdf');
  await choose(new File(['synthetic'], 'invalid.exe', { type: 'application/octet-stream' }));
  expect(container.textContent).toContain('no file selected');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.solverIntakeApply).not.toHaveBeenCalled();
});
