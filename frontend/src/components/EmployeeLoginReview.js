import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

export default function EmployeeLoginReview() {
  const { user } = useAuth();
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (user?.role !== 'it_admin') return null;
  const rows = result?.accountId === user.id ? result.rows : null;
  const review = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const response = await api.getEmployeeLoginReview();
      if (!Array.isArray(response.data)) throw new Error('Unavailable');
      setResult({ accountId: user.id, rows: response.data });
    } catch {
      setError('Could not review employee logins. Please retry.');
    } finally { setBusy(false); }
  };
  return <section aria-label="FTE login readiness" style={{ padding: 16, borderBottom: '1px solid #ddd' }}>
    <h3>FTE login readiness</h3>
    <p>Check saved employee records against login accounts. This review does not create accounts, change roles, reset passwords or send emails.</p>
    <button type="button" disabled={busy} onClick={review}>{busy ? 'Checking logins...' : 'Check employee logins'}</button>
    {error && <p role="alert">{error}</p>}
    {rows && <>
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
