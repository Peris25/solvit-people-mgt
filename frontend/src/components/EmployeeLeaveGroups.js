import React, { useEffect, useState } from 'react';
import { getLeaveBalances } from '../services/api';
import { leaveCategories, leaveStatus } from '../utils/leaveDisplay';

export default function EmployeeLeaveGroups({ rows, renderRecords }) {
  const employees = new Map();
  rows.forEach(row => {
    const key = row.employee_id || row.employee_name || row.id;
    if (!employees.has(key)) employees.set(key, { name: row.employee_name || 'Employee name unavailable', rows: [] });
    employees.get(key).rows.push(row);
  });
  if (!rows.length) return <p>No leave records.</p>;
  return <div data-testid="employee-leave-groups">
    {[...employees.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name)).map(([key, employee]) => <EmployeeSection key={key} employee={employee} renderRecords={renderRecords} />)}
  </div>;
}

function EmployeeSection({ employee, renderRecords }) {
  const [expanded, setExpanded] = useState(false);
  const [balance, setBalance] = useState(null);
  const [balanceError, setBalanceError] = useState(false);
  const [retry, setRetry] = useState(0);
  const identity = employee.rows[0]?.employee_id;
  const year = new Date().getFullYear();
  useEffect(() => {
    let cancelled = false;
    setBalance(null); setBalanceError(false);
    if (!expanded || !identity) return undefined;
    Promise.resolve().then(() => getLeaveBalances(identity)).then(response => {
      if (!response?.data) throw new Error();
      if (!cancelled) setBalance(response.data);
    }).catch(() => { if (!cancelled) setBalanceError(true); });
    return () => { cancelled = true; };
  }, [expanded, identity, retry, employee.rows]);
  const remaining = type => {
    if (!identity || balanceError) return 'Unavailable';
    if (!balance) return 'Loading...';
    if (type === 'Annual' && balance.annual_available_to_request === null) return 'Needs HR review';
    const value = balance[type]?.remaining;
    return typeof value === 'number' && Number.isFinite(value) ? value : 'Needs HR review';
  };
  return <details onToggle={event => setExpanded(event.currentTarget.open)} style={{ background: '#fff', border: '1px solid #ddd', marginBottom: '12px' }}>
      <summary style={{ padding: '16px', cursor: 'pointer', fontWeight: 800 }}>{employee.name} <span style={{ fontWeight: 400 }}>({employee.rows.length} {employee.rows.length === 1 ? 'record' : 'records'})</span></summary>
      <div style={{ padding: '0 16px 16px' }}>
        <p style={{ fontSize: '12px', color: '#525252' }}>{year} balances include accrued annual leave and approved usage. Pending applications remain visible in the dated records.</p>
        {balance?.annual_available_to_request === null && <p style={{ fontSize: '12px', color: '#525252' }}>HR needs to confirm the annual balance before it can be used.</p>}
        {balanceError && <p role="alert">Balance unavailable. <button onClick={() => setRetry(value => value + 1)}>Retry balance</button></p>}
        {Object.entries({ ...leaveCategories, ...Object.fromEntries(employee.rows.filter(row => !leaveCategories[row.leave_type]).map(row => [row.leave_type, row.leave_type])) }).map(([type, label]) => {
          const records = employee.rows.filter(row => row.leave_type === type).sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)));
          const days = status => records.filter(row => leaveStatus(row.status) === status && String(row.start_date || '').startsWith(String(year))).reduce((total, row) => total + (Number(row.working_days) || 0), 0);
          return <details key={type} style={{ borderTop: '1px solid #eee' }}>
            <summary style={{ padding: '12px 0', cursor: 'pointer' }}><strong>{label}</strong> · Days taken: {days('Approved')} · Days remaining: {remaining(type)}</summary>
            {records.length ? renderRecords(records) : <p>No {label.toLowerCase()} records.</p>}
          </details>;
        })}
      </div>
    </details>;
}
