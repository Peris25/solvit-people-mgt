import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Forms from './Forms';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
jest.mock('../services/api');
jest.mock('../context/AuthContext');
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;

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
