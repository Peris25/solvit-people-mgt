import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import Recognition from './Recognition';
import {useAuth} from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('../components/EmployeePicker', () => () => <div />);
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  useAuth.mockReturnValue({user: {id: 'one', role: 'employee'}});
  api.getRecognitions.mockResolvedValue({data: []}); api.getSolverAwards.mockResolvedValue({data: []});
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<Recognition />)); };
test('ordinary staff load their recognition without requesting restricted Solver awards', async () => {
  api.getRecognitions.mockResolvedValue({data: [{id: 'own', recognition_type: 'Peer', nominee_name: 'My approved recognition', values_demonstrated: [], status: 'Approved'}]});
  await render(); expect(api.getRecognitions).toHaveBeenCalledTimes(1); expect(api.getSolverAwards).not.toHaveBeenCalled();
  expect(container.textContent).toContain('My approved recognition');
});
test('Solver uses only its authorized awards endpoint', async () => {
  useAuth.mockReturnValue({user: {id: 'solver', role: 'solver'}}); await render();
  expect(api.getRecognitions).not.toHaveBeenCalled(); expect(api.getSolverAwards).toHaveBeenCalledTimes(1);
});
test('an unqualified manager denied Solver access still sees authorized recognition', async () => {
  useAuth.mockReturnValue({user: {id: 'manager', role: 'line_manager'}});
  api.getSolverAwards.mockRejectedValue({response: {status: 403}}); await render();
  expect(container.querySelector('[role="alert"]')).toBeNull();
});
test('stale account requests cannot publish previous account recognition', async () => {
  let resolveOld; api.getRecognitions.mockImplementationOnce(() => new Promise(resolve => {resolveOld = resolve;}));
  await render(); useAuth.mockReturnValue({user: {id: 'two', role: 'employee'}}); await render();
  await act(async () => resolveOld({data: [{id: 'private', recognition_type: 'Peer', nominee_name: 'SECRET PREVIOUS ACCOUNT', values_demonstrated: []}]}));
  expect(container.textContent).not.toContain('SECRET PREVIOUS ACCOUNT');
});
test('failed requests show a safe error instead of stale records', async () => {
  api.getRecognitions.mockRejectedValue(new Error('SECRET_INTERNAL')); await render();
  expect(container.querySelector('[role="alert"]').textContent).toContain('could not be loaded'); expect(container.textContent).not.toContain('SECRET_INTERNAL');
});
