import React, { useState } from 'react';
import EmployeePicker from './EmployeePicker';
import * as api from '../services/api';

export default function EmployeeAccountForm({ onSaved }) {
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const save = async (event) => {
    event.preventDefault();
    if (!employeeId) { setMessage('Select an employee.'); return; }
    setBusy(true); setMessage('');
    try {
      const result = await api.provisionEmployeeAccount({ employee_id: employeeId, initial_password: password || undefined });
      if (!result.data?.id) throw new Error('Account could not be provisioned.');
      setPassword('');
      setMessage(result.data.created ? 'Account created. Share initial credentials through an approved secure channel.' : 'Existing account linked. Password and role preserved.');
      onSaved?.();
    } catch (error) {
      setPassword('');
      const detail = error.response?.data?.detail;
      setMessage(typeof detail === 'string' ? detail : 'Account could not be provisioned. Check the employee link and password requirements.');
    } finally { setBusy(false); }
  };

  return (
    <form data-testid="employee-account-form" onSubmit={save} style={{ padding: '16px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ fontWeight: 700, fontSize: '12px', marginBottom: '8px' }}>Employee login account</div>
      <EmployeePicker testId="account-employee-picker" value={employeeId} disabled={busy}
        onChange={employee => { setEmployeeId(employee.id); setPassword(''); setMessage(''); }} />
      <label style={{ display: 'block', fontSize: '12px', marginTop: '10px' }}>
        Initial password (new accounts only)
        <input data-testid="account-initial-password" type="password" autoComplete="new-password" value={password}
          disabled={busy} onChange={event => setPassword(event.target.value)}
          style={{ display: 'block', padding: '8px', marginTop: '4px', width: '100%', boxSizing: 'border-box' }} />
      </label>
      <div style={{ fontSize: '11px', margin: '8px 0', color: '#525252' }}>New accounts receive the Employee role. Existing accounts keep their password and role. Use at least 12 characters and avoid common passwords.</div>
      <button data-testid="provision-account" type="submit" disabled={busy || !employeeId}
        style={{ padding: '8px 14px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer' }}>
        {busy ? 'Saving...' : 'Create or link account'}
      </button>
      {message && <div role="status" style={{ marginTop: '8px', fontSize: '12px' }}>{message}</div>}
    </form>
  );
}
