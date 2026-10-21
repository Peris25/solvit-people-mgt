import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StatusBadge from '../components/StatusBadge';
import EmployeePicker from '../components/EmployeePicker';
import * as api from '../services/api';

const LIFECYCLE_STATES = ['Onboarding', 'Probation', 'Active', 'On_Leave', 'PIP', 'Realignment', 'Exiting', 'Exited'];
const ROLE_LEVELS = ['L1', 'L2', 'L3', 'L4', 'L5', 'B1a', 'B1b'];

const fmtKES = (n) => n ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function Employees() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [departmentError, setDepartmentError] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterState, setFilterState] = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ full_name: '', work_email: '', department: '', role_title: '', role_level: 'L2', start_date: '', employment_type: 'Full_Time', current_salary_kes: '', lifecycle_state: 'Onboarding', line_manager_id: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showBulkTraining, setShowBulkTraining] = useState(false);
  const [bulkTraining, setBulkTraining] = useState({ training_name: '', provider: 'Internal', delivery_method: 'Internal', cost_kes: '', duration_days: 1, business_justification: '' });
  const [bulkBusy, setBulkBusy] = useState(false);
  const [pendingRemoval, setPendingRemoval] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [removalError, setRemovalError] = useState('');

  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleSelectAll = () => setSelectedIds(prev => prev.size === employees.length ? new Set() : new Set(employees.map(e => e.id)));

  const handleBulkTransition = async (newState) => {
    if (!window.confirm(`Transition ${selectedIds.size} employees to ${newState}?`)) return;
    setBulkBusy(true);
    try {
      await api.bulkTransitionEmployees([...selectedIds], newState);
      setSelectedIds(new Set());
      await loadEmployees();
    } finally { setBulkBusy(false); }
  };

  const handleBulkTraining = async (e) => {
    e.preventDefault();
    setBulkBusy(true);
    try {
      await api.bulkAssignTraining({
        employee_ids: [...selectedIds],
        ...bulkTraining,
        cost_kes: parseFloat(bulkTraining.cost_kes) || 0,
        duration_days: parseInt(bulkTraining.duration_days) || 1
      });
      setShowBulkTraining(false);
      setSelectedIds(new Set());
      setBulkTraining({ training_name: '', provider: 'Internal', delivery_method: 'Internal', cost_kes: '', duration_days: 1, business_justification: '' });
    } finally { setBulkBusy(false); }
  };

  const canEdit = ['hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.getAllMastersSettings(), api.getStaffDirectory()]).then(([master, directory]) => {
      if (cancelled) return;
      const configured = master.status === 'fulfilled' ? master.value?.data?.workforce?.departments || [] : [];
      const inactive = new Set(configured.filter(d => d.active === false).map(d => d.name));
      const approved = directory.status === 'fulfilled' ? directory.value?.data?.departments || [] : [];
      setDepartments([...new Set([...configured.filter(d => d.active !== false), ...approved]
        .map(d => d.name).filter(name => name && !inactive.has(name)))]);
      if (master.status === 'rejected') setDepartmentError('Departments could not be loaded. The saved department has been preserved.');
    });
    return () => { cancelled = true; };
  }, []);

  const departmentOptions = [...new Set([...departments, ...(form.department ? [form.department] : [])])];
  const filterDepartments = [...new Set([...departments, ...employees.map(e => e.department).filter(Boolean)])];

  const loadEmployees = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getEmployees({ search, lifecycle_state: filterState || undefined, department: filterDept || undefined });
      setEmployees(res.data);
    } finally { setLoading(false); }
  }, [search, filterState, filterDept]);

  useEffect(() => { loadEmployees(); }, [loadEmployees]);

  const saveEmployee = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    if (!form.line_manager_id && !form.is_board_chair && (!selected || form.line_manager_id !== selected.line_manager_id)) {
      setError('Line Manager is required for approval routing. Please select one.');
      setSaving(false);
      return;
    }
    try {
      const data = { ...form, current_salary_kes: form.current_salary_kes ? parseInt(form.current_salary_kes) : null };
      if (!selected && form.existing_employee && !form.start_date) data.start_date = null;
      if (selected) {
        // Preserve legacy identity/reporting values unless explicitly edited.
        if (form.work_email === selected.work_email) delete data.work_email;
        if (form.line_manager_id === selected.line_manager_id) delete data.line_manager_id;
        // Omit an unchanged department, including legacy or missing values.
        if (form.department === selected.department) delete data.department;
        if (form.role_level === (selected.role_level ?? selected.job_level ?? '')) delete data.role_level;
        if (form.employment_type === selected.employment_type) delete data.employment_type;
        if (form.lifecycle_state === (selected.lifecycle_state ?? selected.employment_status ?? selected.status ?? '')) delete data.lifecycle_state;
        await api.updateEmployee(selected.id, data);
      } else {
        await api.createEmployee(data);
      }
      setShowForm(false);
      setSelected(null);
      setForm({ full_name: '', work_email: '', department: '', role_title: '', role_level: 'L2', start_date: '', employment_type: 'Full_Time', current_salary_kes: '', lifecycle_state: 'Onboarding', line_manager_id: '' });
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

  const handleRemove = async (emp) => {
    setRemoving(true); setRemovalError('');
    try {
      await api.removeEmployee(emp.id, emp.full_name);
      setSelectedIds(prev => { const next = new Set(prev); next.delete(emp.id); return next; });
      setPendingRemoval(null);
      await loadEmployees();
    } catch (err) {
      setRemovalError(err.response?.data?.detail || 'Employee could not be removed');
    } finally { setRemoving(false); }
  };

  const openEdit = (emp) => {
    setSelected(emp);
    setForm({ ...emp, role_level: emp.role_level ?? emp.job_level ?? '',
      lifecycle_state: emp.lifecycle_state ?? emp.employment_status ?? emp.status ?? '',
      current_salary_kes: emp.current_salary_kes || '' });
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
            <button data-testid="export-employees-csv" onClick={() => api.downloadCSV('employees')} style={{ padding: '10px 18px', backgroundColor: 'transparent', color: '#191919', border: '1px solid #191919', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>↓ CSV</button>
            <button data-testid="add-employee-btn" onClick={() => { setSelected(null); setShowForm(true); }} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>
              + Add Employee
            </button>
          </div>
        )}
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && canEdit && (
        <div data-testid="bulk-action-bar" style={{ padding: '10px 16px', marginBottom: '12px', backgroundColor: '#191919', color: '#fff', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{selectedIds.size} selected</strong>
          <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>Bulk action:</span>
          {['Probation', 'Active', 'On_Leave', 'Suspended', 'PIP', 'Notice_Period', 'Exiting'].map(s => (
            <button key={s} disabled={bulkBusy} onClick={() => handleBulkTransition(s)} data-testid={`bulk-transition-${s}`} style={{ padding: '4px 10px', backgroundColor: 'transparent', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>→ {s.replace('_', ' ')}</button>
          ))}
          <button data-testid="bulk-assign-training-btn" onClick={() => setShowBulkTraining(true)} style={{ padding: '4px 12px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>+ Assign Training</button>
          <button onClick={() => setSelectedIds(new Set())} style={{ marginLeft: 'auto', padding: '4px 10px', backgroundColor: 'transparent', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial' }}>Clear</button>
        </div>
      )}

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
          {filterDepartments.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {loading ? <div style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>Loading...</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {canEdit && (
                  <th style={{ padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid rgba(25,25,25,0.08)', width: '32px' }}>
                    <input type="checkbox" data-testid="bulk-select-all" checked={selectedIds.size === employees.length && employees.length > 0} onChange={toggleSelectAll} />
                  </th>
                )}
                {['Name', 'Email', 'Role', 'Dept', 'Level', 'Start Date', 'Salary', 'State', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map((emp, i) => (
                <tr key={emp.id} data-testid={`emp-row-${emp.id}`} onClick={() => navigate(`/employees/${emp.id}`)} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: selectedIds.has(emp.id) ? '#FEF2F2' : (i % 2 === 0 ? '#fff' : '#FAFAFA'), cursor: 'pointer' }} onMouseEnter={e => { if (!selectedIds.has(emp.id)) e.currentTarget.style.backgroundColor = '#FEF2F2'; }} onMouseLeave={e => { if (!selectedIds.has(emp.id)) e.currentTarget.style.backgroundColor = i % 2 === 0 ? '#fff' : '#FAFAFA'; }}>
                  {canEdit && (
                    <td style={{ padding: '10px 12px', width: '32px' }} onClick={e => e.stopPropagation()}>
                      <input type="checkbox" data-testid={`bulk-select-${emp.id}`} checked={selectedIds.has(emp.id)} onChange={() => toggleSelect(emp.id)} />
                    </td>
                  )}
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
                          {user?.role === 'hr_admin' && (
                            <button onClick={() => { setPendingRemoval(emp); setRemovalError(''); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #DC2626', backgroundColor: 'transparent', color: '#DC2626', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Remove</button>
                          )}
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

      {pendingRemoval && <div role="dialog" aria-modal="true" aria-labelledby="remove-employee-title" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.45)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
        <div style={{ backgroundColor: '#fff', padding: '24px', maxWidth: '480px', width: '100%' }}>
          <h3 id="remove-employee-title">Remove {pendingRemoval.full_name}?</h3>
          <p>This removes the employee from the roster and has no in-app undo. Accounts and historical records will not be deleted. Linked accounts and direct reports must be reviewed first.</p>
          {removalError && <p role="alert" style={{ color: '#DC2626' }}>{removalError}</p>}
          <button disabled={removing} onClick={() => setPendingRemoval(null)}>Cancel</button>{' '}
          <button disabled={removing} onClick={() => handleRemove(pendingRemoval)} style={{ backgroundColor: '#DC2626', color: '#fff', padding: '8px 16px', border: 0 }}>{removing ? 'Removing...' : 'Remove employee'}</button>
        </div>
      </div>}
      {/* Add/Edit Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900, fontSize: '18px', letterSpacing: '-0.03em' }}>{selected ? 'Edit Employee' : 'Add Employee'}</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#525252' }}>×</button>
            </div>
            <form onSubmit={saveEmployee} style={{ padding: '24px' }}>
              {!selected && <label style={{ display: 'block', marginBottom: '16px', fontSize: '13px' }}>
                <input type="checkbox" checked={!!form.existing_employee} onChange={e => setForm(p => ({ ...p, existing_employee: e.target.checked, role_level: e.target.checked ? '' : p.role_level }))} /> Existing employee — record missing details later; do not send onboarding notifications
              </label>}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {[
                  { key: 'full_name', label: 'Full Name', type: 'text', required: true },
                  { key: 'work_email', label: 'Work Email', type: 'email', required: true },
                  { key: 'role_title', label: 'Role Title', type: 'text', required: true },
                  { key: 'start_date', label: 'Start Date', type: 'date', required: !form.existing_employee && !selected },
                ].map(f => (
                  <div key={f.key}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                    <input type={f.type} value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} required={f.required}
                      style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                    {f.key === 'work_email' && selected && <div style={{ fontSize: '10px', marginTop: '4px', color: '#525252' }}>Changing work email does not change the linked account's login email.</div>}
                  </div>
                ))}
                {[
                  { key: 'department', label: 'Department', options: departmentOptions },
                  { key: 'role_level', label: 'Role Level', options: ROLE_LEVELS },
                  { key: 'employment_type', label: 'Employment Type', options: ['Full_Time', 'Part_Time', 'Fixed_Term'] },
                  { key: 'lifecycle_state', label: 'Lifecycle State', options: LIFECYCLE_STATES },
                ].map(f => (
                  <div key={f.key}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                    <select required={f.key === 'department' && !selected} data-testid={`employee-${f.key}`} value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                      style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }}>
                      {f.key === 'department' && <option value="">Select department</option>}
                      {f.key !== 'department' && !form[f.key] && <option value="">Not specified</option>}
                      {[...new Set([...f.options, ...(typeof form[f.key] === 'string' && form[f.key] ? [form[f.key]] : [])])].map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Salary (KES)</label>
                  <input type="number" value={form.current_salary_kes || ''} onChange={e => setForm(p => ({ ...p, current_salary_kes: e.target.value }))}
                    placeholder="e.g. 75000"
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>
                    Line Manager <span style={{ color: '#FF353F' }}>*</span>
                  </label>
                  <EmployeePicker
                    testId="employee-lm-picker"
                    value={form.line_manager_id}
                    excludeId={selected?.id}
                    placeholder="Select line manager (required for approval routing)..."
                    onChange={(emp) => setForm(p => ({ ...p, line_manager_id: emp.id }))}
                    required={!form.is_board_chair}
                  />
                  <div style={{ fontSize: '10px', color: '#525252', marginTop: '4px', fontStyle: 'italic' }}>
                    Every employee must have a Line Manager. This drives leave / training / performance approval routing.
                  </div>
                </div>
              </div>
              {!selected && user?.role === 'hr_admin' && <label style={{ display: 'block', fontSize: '12px', marginTop: '12px' }}>
                <input type="checkbox" checked={!!form.is_board_chair} onChange={e => setForm(p => ({ ...p, is_board_chair: e.target.checked, line_manager_id: e.target.checked ? '' : p.line_manager_id }))} /> Reporting apex (Board Chair; no line manager required)
              </label>}
              {departmentError && <div role="status" style={{ fontSize: '12px', marginTop: '12px' }}>{departmentError}</div>}
              {error && <div data-testid="employee-lm-error" style={{ color: '#FF353F', fontSize: '12px', marginTop: '12px', padding: '8px', border: '1px solid #FF353F', backgroundColor: 'rgba(255,53,63,0.05)' }}>{error}</div>}
              <div style={{ marginTop: '20px', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>Cancel</button>
                <button data-testid="employee-save" type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial', opacity: saving ? 0.7 : 1 }}>
                  {saving ? 'Saving...' : 'Save Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Bulk training modal */}
      {showBulkTraining && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 900 }}>Bulk Assign Training</h3>
                <p style={{ fontSize: '11px', color: '#525252', margin: '4px 0 0' }}>Assign the same training to {selectedIds.size} selected employees.</p>
              </div>
              <button onClick={() => setShowBulkTraining(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={handleBulkTraining} style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Training Name</label>
                <input required value={bulkTraining.training_name} onChange={e => setBulkTraining(p => ({ ...p, training_name: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Provider</label>
                <input value={bulkTraining.provider} onChange={e => setBulkTraining(p => ({ ...p, provider: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Delivery</label>
                <select value={bulkTraining.delivery_method} onChange={e => setBulkTraining(p => ({ ...p, delivery_method: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                  <option>Internal</option><option>External</option><option>Online</option><option>Mixed</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Cost per emp (KES)</label>
                <input type="number" value={bulkTraining.cost_kes} onChange={e => setBulkTraining(p => ({ ...p, cost_kes: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Days</label>
                <input type="number" value={bulkTraining.duration_days} onChange={e => setBulkTraining(p => ({ ...p, duration_days: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Justification</label>
                <textarea rows={2} value={bulkTraining.business_justification} onChange={e => setBulkTraining(p => ({ ...p, business_justification: e.target.value }))} placeholder="Mandatory training for all selected employees" style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
              </div>
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" onClick={() => setShowBulkTraining(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button data-testid="bulk-training-submit" type="submit" disabled={bulkBusy} style={{ padding: '10px 24px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{bulkBusy ? 'Assigning...' : `Assign to ${selectedIds.size}`}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
