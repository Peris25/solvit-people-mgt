import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Forms from './Forms';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;

test('schema failure offers retry and an empty schema never allows submission', async () => {
  useAuth.mockReturnValue({ user: { role: 'employee' } });
  api.getForms.mockResolvedValue({ data: [{ id: 'form-31', title: 'Notice', target_role: 'employee' }] });
  api.getFormSchema.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce({ data: { sections: [] } });
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<Forms />));
    await act(async () => container.querySelector('[aria-label="Open Notice"]').click());
    expect(container.querySelector('[role="alert"]').textContent).toContain('could not be loaded');
    expect(container.querySelector('[data-testid="submit-form-btn"]').disabled).toBe(true);
    await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === 'Retry').click());
    expect(api.getFormSchema).toHaveBeenCalledTimes(2);
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.textContent).toContain('This form is not available yet');
    expect(container.querySelector('[data-testid="submit-form-btn"]').disabled).toBe(true);
    expect(container.textContent).not.toContain('FRD');
  } finally { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); }
});

test('delayed peer assignments show loading without a placeholder or submit button', async () => {
  useAuth.mockReturnValue({ user: { role: 'employee', employee_id: 'reviewer' } });
  api.getForms.mockResolvedValue({ data: [{ id: 'form-26', title: '360 Peer Review', target_role: 'employee' }] });
  let resolveTasks;
  api.getPerformanceV3Tasks.mockReturnValue(new Promise(resolve => { resolveTasks = resolve; }));
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<Forms />));
    await act(async () => container.querySelector('[aria-label="Open 360 Peer Review"]').click());
    expect(container.textContent).toContain('Loading peer review');
    expect(container.textContent).not.toContain('placeholder');
    expect(container.querySelector('[data-testid="submit-form-btn"]')).toBeNull();
    expect(api.getFormSchema).not.toHaveBeenCalled();
    await act(async () => resolveTasks({ data: { peers: [{ id: 'task', employee_name: 'Eligible colleague', can_submit: true }], peer_questions: ['Integrity'] } }));
    expect(container.textContent).not.toContain('Loading peer review');
    expect(container.querySelector('[aria-label="Colleague to review"]').textContent).toContain('Eligible colleague');
  } finally { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); }
});

test('generic forms cannot submit until their delayed schema is ready', async () => {
  useAuth.mockReturnValue({ user: { role: 'employee' } });
  api.getForms.mockResolvedValue({ data: [{ id: 'form-31', title: 'Notice of resignation', target_role: 'employee' }] });
  let resolveSchema;
  api.getFormSchema.mockReturnValue(new Promise(resolve => { resolveSchema = resolve; }));
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<Forms />));
    await act(async () => container.querySelector('[aria-label="Open Notice of resignation"]').click());
    expect(container.textContent).toContain('Loading form');
    expect(container.querySelector('[data-testid="submit-form-btn"]').disabled).toBe(true);
    await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    expect(api.submitForm).not.toHaveBeenCalled();
    await act(async () => resolveSchema({ data: { sections: [{ id: 'details', title: 'Details', fields: [{ id: 'reason', label: 'Reason', type: 'text' }] }] } }));
    expect(container.querySelector('[data-testid="field-reason"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="submit-form-btn"]').disabled).toBe(false);
  } finally { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); }
});

test('Form 26 opens the actual colleague selector rather than an unlinked generic form', async () => {
  useAuth.mockReturnValue({ user: { role: 'employee', employee_id: 'reviewer' } });
  api.getForms.mockResolvedValue({ data: [{ id: 'form-26', title: '360 Peer Review', target_role: 'employee' }] });
  api.getFormSchema.mockResolvedValue({ data: { id: 'form-26', title: '360 Peer Review', sections: [], submission_mode: 'assigned_peer_review' } });
  api.getPerformanceV3Tasks.mockResolvedValue({ data: { peers: [{ id: 'task', employee_name: 'Eligible colleague', can_submit: true }], peer_questions: ['Integrity', 'Ownership', 'Teamwork', 'Solutions', 'Timeliness'] } });
  const container = document.createElement('div'); document.body.appendChild(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<Forms />));
    await act(async () => container.querySelector('[aria-label="Open 360 Peer Review"]').click());
    expect(container.querySelector('[aria-label="Colleague to review"]').textContent).toContain('Eligible colleague');
    expect(container.querySelector('[data-testid="submit-form-btn"]')).toBeNull();
    expect(container.textContent).toContain('0–10');
    expect(container.textContent).not.toContain('Rate the colleague on Solvit values (1-5)');
  } finally { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); }
});
