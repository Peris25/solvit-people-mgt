import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StatusBadge from '../components/StatusBadge';
import EmployeePicker from '../components/EmployeePicker';
import EmployeeAccountForm from '../components/EmployeeAccountForm';
import EmployeeLoginReview from '../components/EmployeeLoginReview';
import * as api from '../services/api';
import { Search } from 'lucide-react';
import WorkspaceSkeleton from '../components/WorkspaceSkeleton';
import FormDialog, { FieldError, FormNotice, fieldErrorsFrom } from '../components/FormDialog';

const LIFECYCLE_STATES = ['Active', 'Inactive', 'Onboarding', 'Probation', 'On_Leave', 'PIP', 'Realignment', 'Suspended', 'Notice_Period', 'Exiting', 'Exited'];
const ROLE_LEVELS = ['L1', 'L2', 'L3', 'L4', 'L5', 'B1a', 'B1b'];
const freshEmployee = () => ({ full_name: '', work_email: '', department: '', role_title: '', role_level: 'L2', start_date: '', employment_type: 'Full_Time', current_salary_kes: '', lifecycle_state: 'Onboarding', line_manager_id: '', gender: '' });

const fmtKES = (n) => n ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';
const employeeError = (err, fallback) => {
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('; ') || fallback;
  return fallback;
};

export default function Employees() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [departmentError, setDepartmentError] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [listError, setListError] = useState('');
  const [filterState, setFilterState] = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(freshEmployee);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [notice, setNotice] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [showBulkTraining, setShowBulkTraining] = useState(false);
  const [bulkTraining, setBulkTraining] = useState({ training_name: '', provider: 'Internal', delivery_method: 'Internal', cost_kes: '', duration_days: 1, business_justification: '' });
  const [bulkBusy, setBulkBusy] = useState(false);
  const [showLogins, setShowLogins] = useState(false);
  const [accountSelection, setAccountSelection] = useState([]);
  const [accountBusy, setAccountBusy] = useState(false);
  const [accountReviewVersion, setAccountReviewVersion] = useState(0);
  const listSequence = useRef(0);
  const hasLoaded = useRef(false);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleSelectAll = () => setSelectedIds(prev => prev.size === employees.length ? new Set() : new Set(employees.map(e => e.id)));

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

  const canEdit = ['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role);

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
    const sequence = ++listSequence.current;
    try {
      if (!hasLoaded.current) setLoading(true);
      setRefreshing(true); setListError('');
      const res = await api.getEmployees({ search: debouncedSearch, lifecycle_state: filterState || undefined, department: filterDept || undefined });
      if (!Array.isArray(res.data)) throw new Error('Unavailable');
      if (sequence === listSequence.current) { setEmployees(res.data); hasLoaded.current = true; }
    } catch {
      if (sequence === listSequence.current) setListError('Employee list could not be updated. Please retry.');
    } finally { if (sequence === listSequence.current) { setLoading(false); setRefreshing(false); } }
  }, [debouncedSearch, filterState, filterDept]);

  useEffect(() => { loadEmployees(); }, [loadEmployees]);

  const saveEmployee = async (e) => {
    e.preventDefault();
    setSaving(true); setError(''); setFieldErrors({}); setNotice('');
    if (!form.line_manager_id && !form.is_board_chair && !form.reports_to_board && (!selected || form.line_manager_id !== selected.line_manager_id)) {
      setError('Line Manager is required for approval routing. Please select one.');
      setFieldErrors({ line_manager_id: 'Select the employee’s line manager.' });
      setSaving(false);
      return;
    }
    try {
      const data = { ...form, current_salary_kes: form.current_salary_kes ? parseInt(form.current_salary_kes) : null };
      if (!selected && form.existing_employee && !form.start_date) data.start_date = null;
      if (selected) {
        // Preserve legacy identity/reporting values unless explicitly edited.
        if (form.work_email === selected.work_email) delete data.work_email;
        if ((form.gender || '') === (selected.gender || '')) delete data.gender;
        if (form.line_manager_id === selected.line_manager_id) delete data.line_manager_id;
        // Omit an unchanged department, including legacy or missing values.
        if (form.department === selected.department) delete data.department;
        if (form.role_level === (selected.role_level ?? selected.job_level ?? '')) delete data.role_level;
        if (form.employment_type === selected.employment_type) delete data.employment_type;
        if (form.lifecycle_state === (selected.lifecycle_state ?? selected.employment_status ?? selected.status ?? '')) delete data.lifecycle_state;
        const response = await api.updateEmployee(selected.id, data);
        if (!response.data || response.status >= 400) throw new Error('Employee save could not be confirmed');
        const saved = { ...selected, ...data, ...response.data };
        // The save response is authoritative; avoid another full list request
        // that hides the table and delays the confirmation of a successful edit.
        ++listSequence.current;
        setLoading(false);
        setRefreshing(false);
        let matchesSearch = true;
        if (search) {
          try {
            const pattern = new RegExp(search, 'i');
            matchesSearch = [saved.full_name, saved.work_email, saved.role_title].some(value => pattern.test(value || ''));
          } catch { matchesSearch = false; }
        }
        const visible = matchesSearch && (!filterDept || saved.department === filterDept)
          && (filterState ? saved.lifecycle_state === filterState : saved.lifecycle_state !== 'Exited');
        setEmployees(rows => rows.flatMap(employee => employee.id === selected.id ? visible ? [saved] : [] : [employee])
          .sort((a, b) => (a.full_name || '').localeCompare(b.full_name || '')));
        if (!visible) setSelectedIds(previous => { const next = new Set(previous); next.delete(selected.id); return next; });
      } else {
        const response = await api.createEmployee(data);
        if (!response.data?.id || response.status >= 400) throw new Error('Employee save could not be confirmed');
      }
      setShowForm(false);
      setSelected(null);
      setForm(freshEmployee());
      setNotice(selected ? 'Employee changes saved.' : 'Employee added.');
      if (!selected) loadEmployees();
    } catch (err) {
      setError(employeeError(err, 'Failed to save'));
      setFieldErrors(fieldErrorsFrom(err));
    } finally { setSaving(false); }
  };

  const openEdit = (emp) => {
    setError(''); setFieldErrors({}); setNotice('');
    setSelected(emp);
    setForm({ ...emp, role_level: emp.role_level ?? emp.job_level ?? '',
      lifecycle_state: emp.lifecycle_state ?? emp.employment_status ?? emp.status ?? '',
      current_salary_kes: emp.current_salary_kes || '' });
    setShowForm(true);
  };

  return (
    <div data-testid="employees-page" className="workspace-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div className="workspace-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Employee Database</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>FTE employees — {employees.length} records</p>
        </div>
        {canEdit && (
          <div className="workspace-page-actions" style={{ display: 'flex', gap: '8px' }}>
            {user?.role === 'hr_admin' && <button type="button" disabled={accountBusy} onClick={() => setShowLogins(value => !value)} aria-expanded={showLogins} style={{ padding: '10px 18px', backgroundColor: 'transparent', border: '1px solid #191919', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>Employee logins</button>}
            <button data-testid="export-employees-csv" onClick={() => api.downloadCSV('employees')} style={{ padding: '10px 18px', backgroundColor: 'transparent', color: '#191919', border: '1px solid #191919', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>↓ CSV</button>
            <button data-testid="add-employee-btn" onClick={() => { setSelected(null); setForm(freshEmployee()); setFieldErrors({}); setError(''); setNotice(''); setShowForm(true); }} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>
              + Add Employee
            </button>
          </div>
        )}
      </div>

      {showLogins && user?.role === 'hr_admin' && <section aria-label="Employee login administration" style={{ border: '1px solid rgba(25,25,25,0.15)', marginBottom: '20px' }}>
        <EmployeeAccountForm key={accountSelection.map(employee => employee.id).join('|') || 'single'} selectedEmployees={accountSelection} onClearSelection={() => setAccountSelection([])} onBusyChange={setAccountBusy} onSaved={() => setAccountReviewVersion(value => value + 1)} />
        <EmployeeLoginReview key={accountReviewVersion} disabled={accountBusy} onPrepareAccounts={setAccountSelection} />
      </section>}
      {/* Bulk action bar */}
      {selectedIds.size > 0 && canEdit && (
        <div data-testid="bulk-action-bar" style={{ padding: '10px 16px', marginBottom: '12px', backgroundColor: '#191919', color: '#fff', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <strong style={{ fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{selectedIds.size} selected</strong>
          <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>Bulk action:</span>
          <button data-testid="bulk-assign-training-btn" onClick={() => setShowBulkTraining(true)} style={{ padding: '4px 12px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>+ Assign Training</button>
          <button onClick={() => setSelectedIds(new Set())} style={{ marginLeft: 'auto', padding: '4px 10px', backgroundColor: 'transparent', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial' }}>Clear</button>
        </div>
      )}

      {/* Filters */}
      <div className="workspace-toolbar" style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <label className="workspace-search"><Search size={17} aria-hidden="true" /><input className="workspace-search-input" aria-label="Search employees" data-testid="search-employees" placeholder="Search name, email, role..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', width: '240px', fontFamily: 'Arial', outline: 'none' }} /></label>
        <select aria-label="Employee status" data-testid="filter-state" value={filterState} onChange={e => setFilterState(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
          <option value="">All Statuses</option>
          {LIFECYCLE_STATES.map(s => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}
        </select>
        <select aria-label="Employee department" data-testid="filter-dept" value={filterDept} onChange={e => setFilterDept(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
          <option value="">All Departments</option>
          {filterDepartments.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* Table */}
      {refreshing && !loading && <p role="status" style={{ fontSize: 12, color: '#667085' }}>Updating employee list...</p>}
      {listError && <p role="alert">{listError} <button onClick={loadEmployees}>Retry</button></p>}
      <div className="workspace-table" aria-busy={refreshing} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {loading ? <WorkspaceSkeleton label="Loading employees..." /> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {canEdit && (
                  <th style={{ padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid rgba(25,25,25,0.08)', width: '32px' }}>
                    <input type="checkbox" data-testid="bulk-select-all" checked={selectedIds.size === employees.length && employees.length > 0} onChange={toggleSelectAll} />
                  </th>
                )}
                {['Name', 'Email', 'Role', 'Dept', 'Level', 'Start Date', 'Salary', 'Status', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map((emp, i) => (
                <tr key={emp.id} data-testid={`emp-row-${emp.id}`} data-selected={selectedIds.has(emp.id)} onClick={() => navigate(`/employees/${emp.id}`)} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: selectedIds.has(emp.id) ? '#FEF2F2' : (i % 2 === 0 ? '#fff' : '#FAFAFA'), cursor: 'pointer' }} onMouseEnter={e => { if (!selectedIds.has(emp.id)) e.currentTarget.style.backgroundColor = '#FEF2F2'; }} onMouseLeave={e => { if (!selectedIds.has(emp.id)) e.currentTarget.style.backgroundColor = i % 2 === 0 ? '#fff' : '#FAFAFA'; }}>
                  {canEdit && (
                    <td style={{ padding: '10px 12px', width: '32px' }} onClick={e => e.stopPropagation()}>
                      <input type="checkbox" data-testid={`bulk-select-${emp.id}`} checked={selectedIds.has(emp.id)} onChange={() => toggleSelect(emp.id)} />
                    </td>
                  )}
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: '#191919' }}><span className="workspace-employee-name"><span className="workspace-employee-avatar" aria-hidden="true">{(emp.full_name || '?').split(' ').filter(Boolean).map(part => part[0]).slice(0,2).join('')}</span><span>{emp.full_name}</span></span></td>
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
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {employees.length === 0 && (
                <tr><td colSpan={canEdit ? 10 : 9} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>No employees found</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <FormNotice message={notice} onDismiss={setNotice} />
      {showForm && <FormDialog id="employee-form" title={selected ? 'Edit Employee' : 'Add Employee'} description="Keep employee details and approval routing up to date." busy={saving} onClose={() => setShowForm(false)}>
        <form className="workspace-form-body" onSubmit={saveEmployee}
          onInvalid={event => { if (event.target.name) setFieldErrors(previous => ({ ...previous, [event.target.name]: event.target.validationMessage })); }}
          onChangeCapture={event => { if (event.target.name) setFieldErrors(previous => ({ ...previous, [event.target.name]: undefined })); }}>
          <p className="workspace-form-hint">Fields marked <span className="workspace-form-required">*</span> are required. Other fields are optional.</p>
          <fieldset disabled={saving}>
            {!selected && <label className="workspace-form-check" style={{ marginBottom: 20 }}><input type="checkbox" checked={!!form.existing_employee} onChange={event => setForm(previous => ({ ...previous, existing_employee: event.target.checked, role_level: event.target.checked ? '' : previous.role_level }))} /> Existing employee ? record missing details later; do not send onboarding notifications</label>}
            <div className="workspace-form-grid">
              {[
                { key: 'full_name', label: 'Full Name', type: 'text', required: true, section: 'Personal details' },
                { key: 'work_email', label: 'Work Email', type: 'email', required: true },
                { key: 'gender', label: 'Gender', options: ['Female', 'Male', 'Other', 'Prefer not to say'] },
                { key: 'role_title', label: 'Role Title', type: 'text', required: true, section: 'Employment' },
                { key: 'start_date', label: 'Start Date', type: 'date', required: !form.existing_employee && !selected },
                { key: 'department', label: 'Department', options: departmentOptions, required: !selected },
                { key: 'role_level', label: 'Role Level', options: ROLE_LEVELS },
                { key: 'employment_type', label: 'Employment Type', options: ['Full_Time', 'Part_Time', 'Fixed_Term'] },
                { key: 'lifecycle_state', label: 'Status', options: LIFECYCLE_STATES, disabled: !!selected && !['hr_admin', 'general_manager'].includes(user?.role) },
                { key: 'current_salary_kes', label: 'Salary (KES)', type: 'number', placeholder: 'e.g. 75000' },
              ].map(field => <React.Fragment key={field.key}>
                {field.section && <div className="workspace-form-section"><h3>{field.section}</h3></div>}
                <div>
                  <label htmlFor={`employee-input-${field.key}`}>{field.label}{field.required ? <span className="workspace-form-required" aria-hidden="true">*</span> : <span className="workspace-form-optional">Optional</span>}</label>
                  {field.options ? <select id={`employee-input-${field.key}`} name={field.key} aria-label={field.label} data-testid={`employee-${field.key}`} required={field.required} disabled={field.disabled}
                    aria-invalid={!!fieldErrors[field.key]} aria-describedby={fieldErrors[field.key] ? `form-error-${field.key}` : undefined} value={form[field.key] || ''} onChange={event => setForm(previous => ({ ...previous, [field.key]: event.target.value }))}>
                    {(field.key === 'department' || !form[field.key] || field.key === 'gender') && <option value="">{field.key === 'department' ? 'Select department' : 'Not specified'}</option>}
                    {[...new Set([...field.options, ...(typeof form[field.key] === 'string' && form[field.key] ? [form[field.key]] : [])])].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
                  </select> : <input id={`employee-input-${field.key}`} name={field.key} aria-label={field.label} type={field.type} placeholder={field.placeholder} required={field.required}
                    aria-invalid={!!fieldErrors[field.key]} aria-describedby={fieldErrors[field.key] ? `form-error-${field.key}` : undefined} value={form[field.key] || ''} onChange={event => setForm(previous => ({ ...previous, [field.key]: event.target.value }))} />}
                  <FieldError field={field.key} errors={fieldErrors} />
                  {field.key === 'work_email' && selected && <span className="workspace-form-help">Changing work email does not change the linked account's login email.</span>}
                  {field.disabled && <span className="workspace-form-help">Status changes require an HR admin.</span>}
                </div>
              </React.Fragment>)}
              <div className="workspace-form-section"><h3>Approval routing</h3><p>The saved reporting relationship routes leave, training and performance approvals.</p></div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label>Line Manager{!form.is_board_chair && !form.reports_to_board && <span className="workspace-form-required" aria-hidden="true">*</span>}</label>
                <EmployeePicker testId="employee-lm-picker" ariaLabel="Line Manager" invalid={!!fieldErrors.line_manager_id} describedBy={fieldErrors.line_manager_id ? 'form-error-line_manager_id' : undefined}
                  value={form.line_manager_id} excludeId={selected?.id} placeholder="Select line manager (required for approval routing)..."
                  onChange={employee => { setForm(previous => ({ ...previous, line_manager_id: employee.id })); setFieldErrors(previous => ({ ...previous, line_manager_id: undefined })); }}
                  required={!form.is_board_chair && !form.reports_to_board} disabled={!!form.reports_to_board} />
                <FieldError field="line_manager_id" errors={fieldErrors} />
              </div>
            </div>
            {!selected && user?.role === 'hr_admin' && <label className="workspace-form-check" style={{ marginTop: 16 }}><input type="checkbox" checked={!!form.is_board_chair} onChange={event => setForm(previous => ({ ...previous, is_board_chair: event.target.checked, line_manager_id: event.target.checked ? '' : previous.line_manager_id }))} /> Reporting apex (Board Chair; no line manager required)</label>}
            {canEdit && form.role_title?.trim().toLowerCase() === 'managing director' && <label className="workspace-form-check" style={{ marginTop: 16 }}><input type="checkbox" checked={!!form.reports_to_board} onChange={event => setForm(previous => ({ ...previous, reports_to_board: event.target.checked, line_manager_id: event.target.checked ? null : previous.line_manager_id }))} /> Managing Director reports to Board of Directors (no FTE line manager)</label>}
            {departmentError && <p role="status" className="workspace-form-help">{departmentError}</p>}
          </fieldset>
          {error && <div data-testid="employee-lm-error" className="workspace-form-error" role="alert">{error}</div>}
          <footer className="workspace-form-footer"><button type="button" disabled={saving} onClick={() => setShowForm(false)} style={{ border: '1px solid #d0d5dd', background: 'transparent' }}>Cancel</button>
            <button data-testid="employee-save" type="submit" disabled={saving} style={{ background: '#d92336', color: '#fff', border: 0 }}>{saving ? 'Saving...' : 'Save Employee'}</button></footer>
        </form>
      </FormDialog>}

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
