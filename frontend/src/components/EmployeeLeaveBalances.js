import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

const days = value => typeof value === 'number' && Number.isFinite(value) ? value : 'Needs HR review';
const control = { padding: '10px 14px', border: '1px solid #d1d5db', borderRadius: 8, minHeight: 42, background: '#fff', font: 'inherit' };

export default function EmployeeLeaveBalances() {
  const [search, setSearch] = useState('');
  const [department, setDepartment] = useState('');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setData(null);
    const timer = setTimeout(async () => {
      try {
        const response = await api.getEmployeeLeaveBalances({ search, department, offset, limit: 20 });
        if (!response.data || !Array.isArray(response.data.items)) throw new Error('Unavailable');
        if (active) setData(response.data);
      } catch {
        if (active) setError('Employee balances could not be loaded. Please retry.');
      } finally { if (active) setLoading(false); }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [search, department, offset, revision]);
  return <section aria-label="Employee leave balances">
    <h2>Employee Balances</h2>
    <p>Read-only current-year balances from the existing leave records. Estimates and conflicting records are flagged for HR review; no balances are changed here.</p>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
      <input style={control} aria-label="Search employee balances" placeholder="Search employee name" value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} />
      <select style={control} aria-label="Balance department" value={department} onChange={e => { setDepartment(e.target.value); setOffset(0); }}>
        <option value="">All departments</option>
        {(data?.departments || (department ? [department] : [])).map(d => <option key={d}>{d}</option>)}
      </select>
      <LeaveActionButton onClick={() => setRevision(v => v + 1)}>Refresh balances</LeaveActionButton>
    </div>
    {loading && <p role="status">Loading employee balances…</p>}
    {error && <p role="alert">{error} <LeaveActionButton onClick={() => setRevision(v => v + 1)}>Retry</LeaveActionButton></p>}
    {data && <>
      <p>{data.total} matching employees</p>
      {!data.items.length ? <p>No matching employees.</p> : <div style={{ overflowX: 'auto', background: '#fff', borderRadius: 12, border: '1px solid #e5e7eb' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
          <thead><tr>{['Employee', 'Department', 'Annual accrued', 'Annual taken', 'Annual remaining', 'Available to request', 'Other balances / review'].map(label => <th key={label} style={{ padding: 14, textAlign: 'left', background: '#f5f6f8' }}>{label}</th>)}</tr></thead>
          <tbody>{data.items.map(row => {
            const annual = row.balances?.Annual;
            return <tr key={row.record_key} style={{ borderBottom: '1px solid #e5e7eb' }}>
              <td style={{ padding: 14 }}>{row.name}<small style={{ display: 'block' }}>{row.status || 'Status unavailable'}</small></td>
              <td>{row.department}</td><td>{days(annual?.accrued_kenyan_act ?? row.balances?.accrued_annual)}</td>
              <td>{days(annual?.used)}</td><td>{days(annual?.remaining)}{row.annual_pending_days > 0 && <small style={{ display: 'block' }}>{row.annual_pending_days} days pending separately</small>}</td><td>{days(row.balances?.annual_available_to_request)}</td>
              <td style={{ padding: 14 }}>
                {row.needs_review && <strong>Needs HR review</strong>}
                {Object.entries(row.balances || {}).filter(([type, value]) => type !== 'Annual' && value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'remaining')).map(([type, value]) => <div key={type}>{type}: {days(value.remaining)} days remaining</div>)}
                {row.balances?.warning && <details><summary>Balance source</summary>{row.balances.warning}</details>}
              </td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
      <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
        <LeaveActionButton disabled={offset === 0} onClick={() => setOffset(v => Math.max(0, v - 20))}>Previous</LeaveActionButton>
        <LeaveActionButton disabled={offset + 20 >= data.total} onClick={() => setOffset(v => v + 20)}>Next</LeaveActionButton>
      </div>
    </>}
  </section>;
}
