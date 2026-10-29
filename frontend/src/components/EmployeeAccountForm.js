import React, { useState } from 'react';
import EmployeePicker from './EmployeePicker';
import * as api from '../services/api';

export default function EmployeeAccountForm({ onSaved, selectedEmployees = [], onClearSelection, onBusyChange }) {
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [results, setResults] = useState([]);
  const batch = [...new Map(selectedEmployees.filter(employee => employee.id).map(employee => [employee.id, employee])).values()].slice(0, 50);

  const save = async (event) => {
    event.preventDefault();
    if (!employeeId && !batch.length) { setMessage('Select an employee.'); return; }
    if (batch.length && password.length < 12) { setMessage('Enter an initial password of at least 12 characters.'); return; }
    setBusy(true); setMessage(''); setResults([]); onBusyChange?.(true);
    try {
      if (batch.length) {
        const outcomes = [];
        for (const employee of batch) {
          setMessage(`Saving ${outcomes.length + 1} of ${batch.length}...`);
          try {
            const response = await api.provisionEmployeeAccount({ employee_id: employee.id, initial_password: password });
            if (!response.data?.id) {
              outcomes.push({ id: employee.id, name: employee.full_name, status: 'Needs review', detail: response.status === 401 ? 'Session expired; sign in again.' : 'Account was not confirmed. Recheck login readiness before retrying.' });
              setResults([...outcomes]);
              break;
            }
            outcomes.push({ id: employee.id, name: employee.full_name, status: response.data.created ? 'Created' : 'Linked', detail: response.data.created ? 'Change password at first sign-in' : 'Existing password and role preserved' });
          } catch (error) {
            const detail = error.response?.data?.detail;
            outcomes.push({ id: employee.id, name: employee.full_name, status: 'Needs review', detail: typeof detail === 'string' ? detail : 'Recheck the employee link before retrying.' });
          }
          setResults([...outcomes]);
        }
        const created = outcomes.filter(row => row.status === 'Created').length;
        const linked = outcomes.filter(row => row.status === 'Linked').length;
        setMessage(`${created} created; ${linked} linked; ${batch.length - created - linked} need review or remain unprocessed. Recheck employee logins before retrying.`);
        if (created || linked) onSaved?.();
        return;
      }
      const result = await api.provisionEmployeeAccount({ employee_id: employeeId, initial_password: password || undefined });
      if (!result.data?.id) throw new Error('Account could not be provisioned.');
      setPassword('');
      setMessage(result.data.created ? 'Account created. Share initial credentials through an approved secure channel.' : 'Existing account linked. Password and role preserved.');
      onSaved?.();
    } catch (error) {
      setPassword('');
      const detail = error.response?.data?.detail;
      setMessage(typeof detail === 'string' ? detail : 'Account could not be provisioned. Check the employee link and password requirements.');
    } finally { setPassword(''); setBusy(false); onBusyChange?.(false); }
  };

  return (
    <form data-testid="employee-account-form" onSubmit={save} style={{ padding: '16px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ fontWeight: 700, fontSize: '12px', marginBottom: '8px' }}>Employee login account</div>
      {batch.length ? <div>
        <p>Review these {batch.length} employees before creating their login access. New accounts receive the Employee role and must change their password before using the portal.</p>
        <ul>{batch.map(employee => <li key={employee.id}>{employee.full_name} — {employee.work_email}</li>)}</ul>
        <button type="button" disabled={busy} onClick={onClearSelection}>Choose one employee instead</button>
      </div> : <EmployeePicker testId="account-employee-picker" value={employeeId} disabled={busy}
        onChange={employee => { setEmployeeId(employee.id); setPassword(''); setMessage(''); }} />}
      <label style={{ display: 'block', fontSize: '12px', marginTop: '10px' }}>
        Initial password (new accounts only)
        <input data-testid="account-initial-password" type="password" autoComplete="new-password" value={password}
          disabled={busy} required={!!batch.length} minLength={12} onChange={event => setPassword(event.target.value)}
          style={{ display: 'block', padding: '8px', marginTop: '4px', width: '100%', boxSizing: 'border-box' }} />
      </label>
      <div style={{ fontSize: '11px', margin: '8px 0', color: '#525252' }}>New accounts receive the Employee role. Existing accounts keep their password and role. Use at least 12 characters and avoid common passwords.</div>
      <button data-testid="provision-account" type="submit" disabled={busy || (!employeeId && !batch.length)}
        style={{ padding: '8px 14px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer' }}>
        {busy ? 'Saving...' : batch.length ? `Create or link ${batch.length} employee accounts` : 'Create or link account'}
      </button>
      {message && <div role="status" style={{ marginTop: '8px', fontSize: '12px' }}>{message}</div>}
      {!!results.length && <ul aria-label="Account setup results">{results.map(row => <li key={row.id}>{row.name}: {row.status} — {row.detail}</li>)}</ul>}
    </form>
  );
}
