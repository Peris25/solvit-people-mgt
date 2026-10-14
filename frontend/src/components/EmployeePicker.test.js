import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import EmployeePicker from './EmployeePicker';
import * as api from '../services/api';

jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;

test('ambiguous directory identities cannot be selected and labels preserve saved departments', async () => {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container); const onChange = jest.fn();
  api.getEmployeeDirectory.mockResolvedValue({ data: [
    { id: 'ambiguous-storage-id', full_name: 'Ambiguous synthetic record', identity_status: 'ambiguous' },
    { id: 'staff', node_id: 'node-staff', full_name: 'Synthetic staff', department: 'HR_People', department_label: 'HR & People', identity_status: 'resolved' },
  ] });
  try {
    await act(async () => root.render(<EmployeePicker onChange={onChange} />));
    await act(async () => container.querySelector('button').click());
    expect(container.textContent).not.toContain('Ambiguous synthetic record');
    expect(container.textContent).toContain('HR & People');
    await act(async () => container.querySelector('[data-testid="employee-picker-option-staff"]').click());
    expect(onChange.mock.calls[0][0].department).toBe('HR_People');
  } finally { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); }
});
