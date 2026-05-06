import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';

const LIFECYCLE_STATES = ['Onboarding', 'Probation', 'Active', 'On_Leave', 'PIP', 'Realignment', 'Exiting', 'Exited'];
const DEPARTMENTS = ['Operations', 'Commercial', 'Finance', 'Technology', 'HR_People', 'Valuation', 'Leadership'];
const ROLE_LEVELS = ['L1', 'L2', 'L3', 'L4', 'L5', 'B1a', 'B1b'];

const fmtKES = (n) => n ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function Employees() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterState, setFilterState] = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ full_name: '', work_email: '', department: 'Operations', role_title: '', role_level: 'L2', start_date: '', employment_type: 'Full_Time', current_salary_kes: '', lifecycle_state: 'Onboarding' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState('');

  const canEdit = ['hr_admin', 'hr_manager'].includes(user?.role);

  const handleSeedDemo = async () => {
    setSeeding(true); setSeedMsg('');
    try {
      const res = await api.seedDemoEmployees();
      const r = res.data;
      if (r) {
        setSeedMsg(`✓ ${r.inserted || 0} demo employees added across all 9 lifecycle states`);
        await loadEmployees();
      }
    } catch (err) {
      setSeedMsg(`✗ ${err.response?.data?.detail || err.message}`);
    } finally {
      setSeeding(false);
      setTimeout(() => setSeedMsg(''), 6000);
    }
  };

  useEffect(() => { loadEmployees(); }, [search, filterState, filterDept]);

  const loadEmployees = async () => {
    try {
      setLoading(true);
      const res = await api.getEmployees({ search, lifecycle_state: filterState || undefined, department: filterDept || undefined });
      setEmployees(res.data);
    } finally { setLoading(false); }
  };

  const saveEmployee = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const data = { ...form, current_salary_kes: form.current_salary_kes ? parseInt(form.current_salary_kes) : null };
      if (selected) {
        await api.updateEmployee(selected.id, data);
      } else {
        await api.createEmployee(data);
      }
      setShowForm(false);
      setSelected(null);
      setForm({ full_name: '', work_email: '', department: 'Operations', role_title: '', role_level: 'L2', start_date: '', employment_type: 'Full_Time', current_salary_kes: '', lifecycle_state: 'Onboarding' });
      loadEmployees();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save');
    } finally { setSaving(false); }
  };

  const handleTransition = async (empId, state) => {
    try {
      await api.transitionEmployee(empId, state);
      loadEmployees();
    } catch (err) {
      alert(err.response?.data?.detail || 'Transition failed');
    }
  };

  const openEdit = (emp) => {
    setSelected(emp);
    setForm({ ...emp, current_salary_kes: emp.current_salary_kes || '' });
    setShowForm(true);
  };

  return (
    <div data-testid="employees-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Employee Database</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>FTE employees — {employees.length} records</p>
        </div>
        {canEdit && (
          <div style={{ display: 'flex', gap: '8px' }}>
            {user?.role === 'hr_admin' && (
              <button data-testid="seed-demo-employees-btn" onClick={handleSeedDemo} disabled={seeding} style={{ padding: '10px 18px', backgroundColor: 'transparent', color: '#191919', border: '1px solid #191919', cursor: seeding ? 'not-allowed' : 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial', opacity: seeding ? 0.6 : 1 }}>
                {seeding ? 'Generating...' : '⚡ Generate Demo Employees'}
              </button>
            )}
            <button data-testid="add-employee-btn" onClick={() => { setSelected(null); setShowForm(true); }} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>
              + Add Employee
            </button>
          </div>
        )}
      </div>
      {seedMsg && <div data-testid="seed-msg" style={{ padding: '8px 14px', backgroundColor: seedMsg.startsWith('✓') ? '#DCFCE7' : '#FEE2E2', color: seedMsg.startsWith('✓') ? '#166534' : '#991B1B', fontSize: '12px', fontWeight: 700, marginBottom: '12px' }}>{seedMsg}</div>}

      {/* Filters */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <input data-testid="search-employees" placeholder="Search name, email, role..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', width: '240px', fontFamily: 'Arial', outline: 'none' }} />
        <select data-testid="filter-state" value={filterState} onChange={e => setFilterState(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
          <option value="">All States</option>
          {LIFECYCLE_STATES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select data-testid="filter-dept" value={filterDept} onChange={e => setFilterDept(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
          <option value="">All Departments</option>
          {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {loading ? <div style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>Loading...</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Name', 'Email', 'Role', 'Dept', 'Level', 'Start Date', 'Salary', 'State', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map((emp, i) => (
                <tr key={emp.id} data-testid={`emp-row-${emp.id}`} onClick={() => navigate(`/employees/${emp.id}`)} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA', cursor: 'pointer' }} onMouseEnter={e => e.currentTarget.style.backgroundColor = '#FEF2F2'} onMouseLeave={e => e.currentTarget.style.backgroundColor = i % 2 === 0 ? '#fff' : '#FAFAFA'}>
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: '#191919' }}>{emp.full_name}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.work_email}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.role_title}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.department}</td>
                  <td style={{ padding: '10px 16px' }}><span style={{ backgroundColor: '#F5F5F5', padding: '2px 6px', fontSize: '11px', fontWeight: 700 }}>{emp.role_level}</span></td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{fmtDate(emp.start_date)}</td>
                  <td style={{ padding: '10px 16px', color: '#191919', fontWeight: user?.role === 'finance' ? 700 : 400 }}>
                    {user?.role !== 'employee' ? fmtKES(emp.current_salary_kes) : '***'}
                  </td>
                  <td style={{ padding: '10px 16px' }}><StatusBadge status={emp.lifecycle_state} small /></td>
                  <td style={{ padding: '10px 16px' }} onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      {canEdit && (
                        <>
                          <button onClick={(ev) => { ev.stopPropagation(); openEdit(emp); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700, transition: 'all 0.15s' }}>Edit</button>
                          {emp.lifecycle_state === 'Onboarding' && (
                            <button onClick={(ev) => { ev.stopPropagation(); handleTransition(emp.id, 'Probation'); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #3B82F6', backgroundColor: 'transparent', color: '#3B82F6', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>→ Probation</button>
                          )}
                          {emp.lifecycle_state === 'Probation' && (
                            <button onClick={(ev) => { ev.stopPropagation(); handleTransition(emp.id, 'Active'); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', backgroundColor: 'transparent', color: '#22C55E', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>→ Active</button>
                          )}
                          {emp.lifecycle_state === 'Active' && (
                            <button onClick={(ev) => { ev.stopPropagation(); handleTransition(emp.id, 'Exiting'); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #F97316', backgroundColor: 'transparent', color: '#F97316', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>→ Exiting</button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {employees.length === 0 && (
                <tr><td colSpan={9} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>No employees found</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Add/Edit Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900, fontSize: '18px', letterSpacing: '-0.03em' }}>{selected ? 'Edit Employee' : 'Add Employee'}</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#525252' }}>×</button>
            </div>
            <form onSubmit={saveEmployee} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {[
                  { key: 'full_name', label: 'Full Name', type: 'text', required: true },
                  { key: 'work_email', label: 'Work Email', type: 'email', required: true },
                  { key: 'role_title', label: 'Role Title', type: 'text', required: true },
                  { key: 'start_date', label: 'Start Date', type: 'date', required: true },
                ].map(f => (
                  <div key={f.key}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                    <input type={f.type} value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} required={f.required}
                      style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                  </div>
                ))}
                {[
                  { key: 'department', label: 'Department', options: DEPARTMENTS },
                  { key: 'role_level', label: 'Role Level', options: ROLE_LEVELS },
                  { key: 'employment_type', label: 'Employment Type', options: ['Full_Time', 'Part_Time', 'Fixed_Term'] },
                  { key: 'lifecycle_state', label: 'Lifecycle State', options: LIFECYCLE_STATES },
                ].map(f => (
                  <div key={f.key}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                    <select value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                      style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }}>
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Salary (KES)</label>
                  <input type="number" value={form.current_salary_kes || ''} onChange={e => setForm(p => ({ ...p, current_salary_kes: e.target.value }))}
                    placeholder="e.g. 75000"
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                </div>
              </div>
              {error && <div style={{ color: '#FF353F', fontSize: '12px', marginTop: '12px', padding: '8px', border: '1px solid #FF353F', backgroundColor: 'rgba(255,53,63,0.05)' }}>{error}</div>}
              <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>Cancel</button>
                <button data-testid="save-employee-btn" type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial', opacity: saving ? 0.7 : 1 }}>
                  {saving ? 'Saving...' : 'Save Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
