import React, { useCallback, useEffect, useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

export default function OnboardingRegister({ onRecorded, onLoaded }) {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState([]);
  const [view, setView] = useState('All');
  const [search, setSearch] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const response = await api.getOnboardingRegister();
      if (!Array.isArray(response?.data)) throw new Error('Unavailable');
      setRows(response.data);
      onLoaded?.(response.data);
    } catch { setError('Unable to load the onboarding register. Please retry.'); }
    finally { setBusy(false); }
  }, [onLoaded]);
  useEffect(() => { load(); }, [load]);
  const visible = rows.filter(r => (view === 'All' || r.onboarding_status === view) && `${r.name || ''} ${r.department || ''}`.toLowerCase().includes(search.trim().toLowerCase()));
  const eligible = visible.filter(r => ['Active', 'Onboarding', 'Probation'].includes(r.employment_status));
  const record = async status => {
    setBusy(true); setError(''); setNotice('');
    try {
      const response = await api.recordOnboardingStatus({ employee_ids: selected, status, reason });
      if (!response?.data?.recorded) throw new Error('Not saved');
      setNotice(`${response.data.recorded} employee onboarding statuses recorded.`);
      setSelected([]); setReason(''); await load(); await onRecorded();
    } catch (e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Onboarding status could not be saved. Please retry.'); }
    finally { setBusy(false); }
  };
  const control = { padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, font: 'inherit' };
  return <section style={{ background: '#fff', padding: 24, marginBottom: 24, borderRadius: 16 }} aria-label="Onboarding register">
    <h2>Employee onboarding</h2>
    <p>Completed: {rows.filter(r => r.onboarding_status === 'Completed').length} · In progress: {rows.filter(r => r.onboarding_status === 'In_Progress').length} · Not recorded: {rows.filter(r => r.onboarding_status === 'Not recorded').length}</p>
    <p>Record HR-confirmed onboarding already completed outside this portal. This does not change employment status, start dates, leave balances or document verification.</p>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
      <input style={control} aria-label="Search onboarding employees" placeholder="Search name or department" value={search} onChange={e => { setSearch(e.target.value); setSelected([]); }} />
      <select style={control} aria-label="Onboarding status filter" value={view} onChange={e => { setView(e.target.value); setSelected([]); }}>
        <option>All</option><option value="Completed">Onboarded</option><option value="In_Progress">New employees / in progress</option><option>Not recorded</option>
      </select>
      <LeaveActionButton disabled={busy} onClick={load}>Refresh register</LeaveActionButton>
    </div>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Updating onboarding register…</p>}
    <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 520 }}>
      <thead><tr><th><input type="checkbox" aria-label="Select visible onboarding employees" disabled={busy || !eligible.length} checked={eligible.length > 0 && eligible.every(r => selected.includes(r.id))} onChange={e => setSelected(e.target.checked ? eligible.map(r => r.id) : [])} /></th><th style={{ textAlign: 'left' }}>Employee</th><th style={{ textAlign: 'left' }}>Department</th><th style={{ textAlign: 'left' }}>Onboarding</th></tr></thead>
      <tbody>{visible.map(row => <tr key={row.id} style={{ borderTop: '1px solid #e5e7eb' }}>
        <td style={{ padding: 12 }}><input type="checkbox" aria-label={`Select ${row.name}`} disabled={busy || !eligible.includes(row)} checked={selected.includes(row.id)} onChange={e => setSelected(v => e.target.checked ? [...v, row.id] : v.filter(id => id !== row.id))} /></td>
        <td style={{ padding: 12 }}>{row.name}</td><td>{row.department || 'Not specified'}</td><td>{row.onboarding_status === 'Completed' ? 'Onboarded' : row.onboarding_status === 'In_Progress' ? 'In progress' : 'Not recorded'}</td>
      </tr>)}</tbody>
    </table></div>
    {!busy && !visible.length && <p>No matching employees.</p>}
    <label style={{ display: 'block', margin: '16px 0' }}>HR confirmation reason
      <textarea style={{ ...control, display: 'block', width: '100%', boxSizing: 'border-box' }} aria-label="HR onboarding confirmation reason" maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} />
    </label>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <LeaveActionButton variant="primary" disabled={busy || !selected.length || reason.trim().length < 10} onClick={() => record('Completed')}>Record completed onboarding ({selected.length})</LeaveActionButton>
      <LeaveActionButton disabled={busy || !selected.length || reason.trim().length < 10} onClick={() => record('In_Progress')}>Record onboarding in progress ({selected.length})</LeaveActionButton>
    </div>
  </section>;
}
