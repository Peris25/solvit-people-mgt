import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
let mockEmployeeModuleLoads = 0;
let mockAuthProviderMounts = 0;
// CRA's older Jest resolver cannot resolve react-router's /dom export.
// The same declarative router is exported from its root entry.
jest.mock('react-router-dom', () => { global.TextEncoder = require('util').TextEncoder; return jest.requireActual('react-router'); });
jest.mock('./context/AuthContext', () => ({ AuthProvider: ({ children }) => { mockAuthProviderMounts += 1; return children; } }));
jest.mock('./context/ThemeContext', () => ({ ThemeProvider: ({ children }) => children }));
jest.mock('./context/NotificationContext', () => ({ NotificationProvider: ({ children }) => children }));
jest.mock('./components/Layout', () => { const { Outlet } = require('react-router-dom'); return () => <Outlet />; });
jest.mock('./pages/Login', () => () => <div>Login screen</div>);
jest.mock('./pages/Employees', () => { mockEmployeeModuleLoads += 1; return () => <div>Employee screen</div>; });
jest.mock('./services/api', () => ({ getPublicSolverQuestionnaire: () => Promise.resolve({ data: { version: 'test', sections: [] } }), getPublicSolverChallenge: () => Promise.resolve({ data: { token: 'test', question: 'Synthetic verification' } }) }));

global.IS_REACT_ACT_ENVIRONMENT = true;
test('login does not load employee module; navigation loads and renders it on demand', async () => {
  const container=document.createElement('div'); document.body.appendChild(container);
  const root=createRoot(container);
  window.history.replaceState({}, '', '/login');
  try {
    await act(async () => root.render(<App />));
    expect(container.textContent).toContain('Login screen');
    expect(mockEmployeeModuleLoads).toBe(0);
    await act(async () => { window.history.pushState({}, '', '/employees'); window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(container.textContent).toContain('Employee screen');
    expect(mockEmployeeModuleLoads).toBe(1);
  } finally { await act(async () => root.unmount()); container.remove(); window.history.replaceState({}, '', '/'); }
});


test('standalone applicant URL never mounts portal authentication or private navigation', async () => {
  const container=document.createElement('div'); document.body.appendChild(container); const root=createRoot(container);
  window.history.replaceState({}, '', '/solver-assessments'); mockAuthProviderMounts=0;
  try {
    await act(async () => root.render(<App />));
    expect(mockAuthProviderMounts).toBe(0);
    expect(container.textContent).toContain('Motor Vehicle Solver Assessment');
    expect(container.textContent).not.toContain('Assign an approved assessment');
    expect(container.textContent).not.toContain('Assessment oversight');
  } finally { await act(async () => root.unmount()); container.remove(); window.history.replaceState({}, '', '/'); }
});
