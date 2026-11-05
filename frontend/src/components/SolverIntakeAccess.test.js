import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SolverIntakeAccess from './SolverIntakeAccess';
import { useAuth } from '../context/AuthContext';
jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
test.each(['hr_admin', 'it_admin'])('%s can open applicant administration', async role => {
  useAuth.mockReturnValue({ user: { role } });
  await act(async () => root.render(<SolverIntakeAccess><div>Private applications</div></SolverIntakeAccess>));
  expect(container.textContent).toContain('Private applications');
});
test.each(['employee', 'line_manager', 'solvers_manager', 'general_manager', 'hr_manager', 'executive', 'solver'])('%s cannot mount the private page', async role => {
  useAuth.mockReturnValue({ user: { role } });
  const page = jest.fn(() => <div>Private applications</div>);
  const Page = page;
  await act(async () => root.render(<SolverIntakeAccess><Page /></SolverIntakeAccess>));
  expect(container.querySelector('[role="alert"]').textContent).toContain('restricted');
  expect(page).not.toHaveBeenCalled();
});
