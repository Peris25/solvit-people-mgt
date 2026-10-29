import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

export default function EmployeeLoginReview({ onPrepareAccounts, disabled = false }) {
  const { user } = useAuth();
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!['it_admin', 'hr_admin'].includes(user?.role)) return null;
  const rows = result?.accountId === user.id && result?.role === user.role ? result.rows : null;
  const missing = (rows || []).filter(row => row.employee_id && row.issues.length === 1 && row.issues[0] === 'No login account found').slice(0, 50);
  const review = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const response = await api.getEmployeeLoginReview();
      if (!Array.isArray(response.data)) throw new Error('Unavailable');
      setResult({ accountId: user.id, role: user.role, rows: response.data });
    } catch {
      setError('Could not review employee logins. Please retry.');
    } finally { setBusy(false); }
  };
  return <section aria-label="FTE login readiness" style={{ padding: 16, borderBottom: '1px solid #ddd' }}>
    <h3>FTE login readiness</h3>
    <p>Check saved employee records against login accounts. This review does not create accounts, change roles, reset passwords or send emails.</p>
    <button type="button" disabled={busy || disabled} onClick={review}>{busy ? 'Checking logins...' : 'Check employee logins'}</button>
    {error && <p role="alert">{error}</p>}
    {rows && <>
      {!!missing.length && onPrepareAccounts && <button type="button" disabled={disabled || busy} onClick={() => onPrepareAccounts(missing.map(row => ({ id: row.employee_id, full_name: row.full_name, work_email: row.work_email })))}>Prepare {missing.length} missing employee accounts</button>}
      <p>{rows.length} employee records checked; {rows.filter(row => row.status === 'Needs review').length} need review. “Linked” confirms identity linkage; users still need to satisfy password and MFA requirements where applicable.</p>
      <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', fontSize: 12, textAlign: 'left' }}>
        <thead><tr>{['Employee', 'Work email', 'Department', 'Account role', 'Link status', 'Required action'].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.record_id}>
          <td>{row.full_name || 'Name not recorded'}</td><td>{row.work_email || 'Not recorded'}</td><td>{row.department || 'Not recorded'}</td>
          <td>{row.role || 'No unique account'}</td><td>{row.status}</td><td>{row.issues.join('; ') || (row.must_change_password ? 'Change initial password at sign-in' : 'No linkage issue found')}</td>
        </tr>)}</tbody>
      </table></div>
      {!rows.length && <p>No FTE records available for this review.</p>}
    </>}
  </section>;
}
