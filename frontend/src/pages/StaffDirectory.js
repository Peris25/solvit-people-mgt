import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
import { STAFF_DIRECTORY_ROLES } from '../utils/staffDirectory';

export default function StaffDirectory() {
  const { user } = useAuth();
  const allowed = STAFF_DIRECTORY_ROLES.includes(user?.role);
  const [data, setData] = useState({ employees: [], departments: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [department, setDepartment] = useState('');

  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError('');
    api.getStaffDirectory().then(response => {
      if (!Array.isArray(response.data?.employees) || !Array.isArray(response.data?.departments)) throw new Error('The staff directory could not be loaded.');
      if (active) setData(response.data);
    }).catch(e => {
      const detail = e.response?.data?.detail;
      if (active) setError(typeof detail === 'string' ? detail : detail?.message || e.message);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed, user?.id, user?.role]);

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matching = data.employees.filter(employee => {
      const name = employee.department_label || employee.department || 'Unconfirmed department';
      return (!department || department === name) && (!q || [employee.full_name, employee.preferred_name,
        employee.role_title, name, employee.contact_for].some(value => typeof value === 'string' && value.toLowerCase().includes(q)));
    });
    const names = [...new Set([...data.departments.map(d => d.name), ...matching.map(e => e.department_label || e.department || 'Unconfirmed department')])];
    return names.map(name => ({ name, note: data.departments.find(d => d.name === name)?.contact_for || '',
      employees: matching.filter(e => (e.department_label || e.department || 'Unconfirmed department') === name) })).filter(g => g.employees.length);
  }, [data, search, department]);

  if (!allowed) return <div role="alert" style={{ padding: 28 }}>Staff directory access is not available for this account.</div>;
  const departments = [...new Set([...data.departments.map(d => d.name), ...data.employees.map(e => e.department_label || e.department || 'Unconfirmed department')])];
  return (
    <div style={{ padding: '28px', backgroundColor: '#F9FAFB', minHeight: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div><h1 style={{ margin: 0, fontSize: 28, color: '#191919' }}>Staff Directory</h1>
          <p style={{ color: '#525252', fontSize: 13 }}>Find colleagues and the right team to contact.</p></div>
        <Link to="/organogram" style={{ color: '#FF353F', alignSelf: 'center' }}>View organogram</Link>
      </div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', margin: '16px 0 24px' }}>
        <label style={{ flex: '1 1 240px' }}>Search staff
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Name, title, department or responsibility"
            style={{ display: 'block', boxSizing: 'border-box', width: '100%', padding: 12, marginTop: 8, border: '1px solid #D1D5DB' }} />
        </label>
        <label style={{ flex: '1 1 200px' }}>Department
          <select value={department} onChange={e => setDepartment(e.target.value)}
            style={{ display: 'block', width: '100%', padding: 12, marginTop: 8, border: '1px solid #D1D5DB' }}>
            <option value="">All departments</option>{departments.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      {loading && <p role="status">Loading staff directory...</p>}
      {error && <p role="alert">Could not load staff directory: {error}</p>}
      {!loading && !error && !groups.length && <p role="status">No staff match your search and department.</p>}
      {!loading && !error && groups.map(group => <section key={group.name} style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, marginBottom: 8 }}>{group.name}</h2>
        {group.note && <p style={{ fontSize: 13, color: '#525252' }}>Contact for: {group.note}</p>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 16 }}>
          {group.employees.map(employee => <article key={employee.node_id} style={{ padding: 16, backgroundColor: '#fff', border: '1px solid #E5E7EB', borderTop: '3px solid #FF353F' }}>
            <h3 style={{ fontSize: 16, margin: '0 0 8px' }}>{employee.full_name || 'Name unavailable'}</h3>
            <p style={{ fontSize: 13, margin: '8px 0' }}>{employee.role_title || 'Title unavailable'}</p>
            <p style={{ fontSize: 12, color: '#525252' }}>{group.name}</p>
            {employee.work_email && <p style={{ overflowWrap: 'anywhere' }}>Work email: <a href={`mailto:${employee.work_email}`}>{employee.work_email}</a></p>}
            {employee.work_phone && <p>Work phone: {employee.work_phone}</p>}
            {employee.line_manager_name && <p style={{ fontSize: 12 }}>Line manager: {employee.line_manager_name}</p>}
            {employee.identity_status === 'ambiguous' && <p role="status">Employee identifier needs HR review.</p>}
            {employee.reporting_status !== 'resolved' && <p role="status" style={{ fontSize: 12 }}>Reporting assignment awaits HR confirmation.</p>}
          </article>)}
        </div>
      </section>)}
    </div>
  );
}
