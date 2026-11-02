import React from 'react';
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
    {[...employees.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name)).map(([key, employee]) => <details key={key} style={{ background: '#fff', border: '1px solid #ddd', marginBottom: '12px' }}>
      <summary style={{ padding: '16px', cursor: 'pointer', fontWeight: 800 }}>{employee.name} <span style={{ fontWeight: 400 }}>({employee.rows.length} records)</span></summary>
      <div style={{ padding: '0 16px 16px' }}>
        {Object.entries({ ...leaveCategories, ...Object.fromEntries(employee.rows.filter(row => !leaveCategories[row.leave_type]).map(row => [row.leave_type, row.leave_type])) }).map(([type, label]) => {
          const records = employee.rows.filter(row => row.leave_type === type).sort((a, b) => String(b.start_date).localeCompare(String(a.start_date)));
          const days = status => records.filter(row => leaveStatus(row.status) === status).reduce((total, row) => total + (Number(row.working_days) || 0), 0);
          return <details key={type} style={{ borderTop: '1px solid #eee' }}>
            <summary style={{ padding: '12px 0', cursor: 'pointer' }}><strong>{label}</strong> · {days('Approved')} approved days · {days('Pending')} pending days</summary>
            {records.length ? renderRecords(records) : <p>No {label.toLowerCase()} records.</p>}
          </details>;
        })}
      </div>
    </details>)}
  </div>;
}
