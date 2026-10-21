import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import SolverWorkflow from '../components/SolverWorkflow';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';
const EDIT_FIELDS = [
  ['full_name', 'Full name'], ['phone_number', 'Phone', 'tel'], ['email', 'Email', 'email'],
  ['region', 'Region'], ['area_covered', 'Area covered'], ['payment_method', 'Payment method'],
  ['national_id_number', 'National ID'], ['kra_pin', 'KRA PIN'], ['nssf_number', 'NSSF number'], ['sha_number', 'SHA number'],
  ['bank_name', 'Bank name'], ['bank_account_number', 'Bank account number'], ['mpesa_number', 'MPesa number'],
  ['driving_licence_type', 'Driving licence type'], ['driving_licence_number', 'Driving licence number'],
  ['driving_licence_expiry', 'Driving licence expiry', 'date'], ['onboarded_at', 'Onboarding date', 'date'],
  ['vehicle_categories', 'Vehicle categories (comma separated)', 'list'], ['zones_covered', 'Zones covered (comma separated)', 'list'],
  ['jobs_completed', 'Completed jobs', 'number'], ['accuracy_score', 'Accuracy score', 'number'],
  ['reliability_score', 'Reliability score', 'number'], ['timeliness_score', 'Timeliness score', 'number'],
  ['client_rating_average', 'Recorded client rating', 'number'], ['performance_tier', 'Performance tier'], ['notes', 'Notes']
];
const editValue = (record, key, type) => type === 'list' ? (Array.isArray(record[key]) ? record[key].join(', ') : record[key] || '') : type === 'date' ? String(record[key] || '').slice(0, 10) : String(record[key] ?? (key === 'national_id_number' ? record.national_id : '') ?? '');

export default function Solvers() {
  const { user } = useAuth();
  const generation = useRef(0);
  const [loadedFor, setLoadedFor] = useState(null);
  const [region, setRegion] = useState('');
  const [category, setCategory] = useState('');
  const [options, setOptions] = useState({ regions: [], categories: [] });
  const [solvers, setSolvers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterState, setFilterState] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ full_name: '', phone_number: '', payment_method: 'MPesa', vehicle_categories: [], zones_covered: [] });
  const [saving, setSaving] = useState(false);
  const [viewSolver, setViewSolver] = useState(null);
  const [error, setError] = useState('');
  const [editingStatus, setEditingStatus] = useState(null);
  const [nextStatus, setNextStatus] = useState('');
  const [statusError, setStatusError] = useState('');
  const [editValues, setEditValues] = useState({});

  const current = loadedFor === user?.id;
  const canEdit = current && stats?.can_manage === true;
  const canEditStatus = current && ['hr_admin', 'hr_manager'].includes(user?.role) &&
    (stats?.can_edit_profile ?? stats?.can_manage ?? !stats?.directory_only);


  const loadSolvers = useCallback(async () => {
    const requestId = ++generation.current;
    setLoading(true); setError(''); setViewSolver(null);
    try {
      const [sRes, statsRes, optionsRes] = await Promise.all([
        api.getSolvers({ search, lifecycle_state: filterState || undefined, region: region || undefined, category: category || undefined }),
        api.getSolverStats(),
        api.getSolverDirectoryOptions()
      ]);
      if (requestId !== generation.current) return;
      if (!Array.isArray(sRes.data) || !statsRes.data) throw new Error(sRes.error || statsRes.error || 'Solver information could not be loaded.');
      setSolvers(sRes.data);
      setStats(statsRes.data); setOptions(optionsRes.data || { regions: [], categories: [] }); setLoadedFor(user?.id);
    } catch (e) {
      if (requestId !== generation.current) return;
      setSolvers([]); setStats(null);
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || e.message);
    } finally { if (requestId === generation.current) setLoading(false); }
  }, [search, filterState, region, category, user?.id]);

  useEffect(() => { loadSolvers(); return () => { generation.current += 1; }; }, [loadSolvers]);

  const saveSolver = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createSolver(form);
      setShowForm(false);
      setForm({ full_name: '', phone_number: '', payment_method: 'MPesa', vehicle_categories: [], zones_covered: [] });
      loadSolvers();
    } catch (e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Could not register Solver. Please retry.'); } finally { setSaving(false); }
  };

  const toggleCheckbox = (key, val) => {
    setForm(p => ({ ...p, [key]: p[key].includes(val) ? p[key].filter(x => x !== val) : [...p[key], val] }));
  };

  const saveStatus = async event => {
    event.preventDefault();
    if (!canEditStatus || editingStatus?.accountId !== user?.id || saving) return;
    const changes = {};
    if (nextStatus !== editingStatus.lifecycle_state) changes.lifecycle_state = nextStatus;
    for (const [key, , type] of EDIT_FIELDS) {
      if (editValues[key] !== editValue(editingStatus, key, type)) {
        changes[key] = type === 'list' ? editValues[key].split(',').map(value => value.trim()).filter(Boolean) :
          type === 'number' ? (editValues[key] === '' ? null : Number(editValues[key])) :
          type === 'date' && editValues[key] === '' ? null : editValues[key];
      }
    }
    if (!Object.keys(changes).length) { setEditingStatus(null); return; }
    setSaving(true); setStatusError('');
    try {
      await api.updateSolver(editingStatus.id, changes);
      setEditingStatus(null);
      await loadSolvers();
    } catch (e) {
      setStatusError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Could not update status. Refresh before retrying.');
    } finally { setSaving(false); }
  };

  const VEHICLE_CATS = ['Saloon', 'SUV', 'Pick-Up', 'Van', 'Truck', 'Motorcycle'];
  const ZONES = ['Zone 1: CBD', 'Zone 2: Westlands-Kileleshwa', 'Zone 3: Karen-Langata', 'Zone 4: Eastlands', 'Zone 5: Thika Rd Corridor', 'Zone 6: South B-South C'];

  const tierColors = { 'Elite': '#22C55E', 'High_Performer': '#3B82F6', 'Standard': '#525252', 'Under_Review': '#F97316', null: '#9CA3AF', undefined: '#9CA3AF' };

  return (
    <div data-testid="solvers-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Solver Database</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Gig workforce — {solvers.length} records</p>
        </div>
        {canEdit && (
          <button data-testid="add-solver-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Register Solver</button>
        )}
      </div>

      {/* Stats */}
      {current && stats && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap' }}>
          {Object.entries(stats.by_state || {}).map(([state, count]) => (
            <div key={state} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 20px', minWidth: '100px' }}>
              <div style={{ fontSize: '22px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919' }}>{count}</div>
              <StatusBadge status={state} small />
            </div>
          ))}
        </div>
      )}

      {error && <p role="alert" style={{ color: '#991B1B' }}>Could not load Solver information: {error}</p>}
      {/* Filters */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '20px' }}>
        <input data-testid="search-solvers" placeholder="Search name or phone..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', width: '240px', fontFamily: 'Arial', outline: 'none' }} />
        <select data-testid="filter-solver-state" value={filterState} onChange={e => setFilterState(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial' }}>
          <option value="">All States</option>
          {['Registering', 'Active', 'Suspended', 'Inactive', 'Deactivated'].map(s => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Filter Solver region" value={region} onChange={e => setRegion(e.target.value)}><option value="">All regions</option>{options.regions.map(value => <option key={value}>{value}</option>)}</select>
        <select aria-label="Filter Solver category" value={category} onChange={e => setCategory(e.target.value)}><option value="">All vehicle categories</option>{options.categories.map(value => <option key={value}>{value}</option>)}</select>
      </div>

      {/* Table */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
        {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Name', 'Phone', 'Region / area', 'Zones', 'Vehicle Types', 'Accuracy', 'Reliability', 'Client Rating', 'Tier', 'State', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(current ? solvers : []).map((s, i) => (
                <tr key={s.id} data-testid={`solver-row-${s.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>
                    {s.full_name}
                    {canEditStatus && <button data-testid={`edit-solver-${s.id}`} onClick={() => { setEditingStatus({ ...s, accountId: user?.id }); setNextStatus(s.lifecycle_state); setEditValues(Object.fromEntries(EDIT_FIELDS.map(([key, , type]) => [key, editValue(s, key, type)]))); setStatusError(''); }} style={{ display: 'block', marginTop: 6, padding: '4px 10px', fontSize: 11, border: '1px solid #FF353F', color: '#FF353F', backgroundColor: 'transparent', cursor: 'pointer', fontWeight: 700 }}>Edit</button>}
                  </td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{s.phone_number}</td>
                  <td style={{ padding: '10px 14px' }}>{[s.region, s.area_covered].filter(Boolean).join(' / ') || 'Not recorded'}</td>
                  <td style={{ padding: '10px 14px', color: '#525252', fontSize: '10px' }}>{(s.zones_covered || []).slice(0, 2).join(', ')}{(s.zones_covered || []).length > 2 ? ` +${s.zones_covered.length - 2}` : ''}</td>
                  <td style={{ padding: '10px 14px', color: '#525252', fontSize: '10px' }}>{(s.vehicle_categories || []).join(', ')}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: s.accuracy_score >= 90 ? '#166534' : '#191919' }}>{s.accuracy_score != null ? `${s.accuracy_score}%` : '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{s.reliability_score != null ? `${s.reliability_score}%` : '—'}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{s.client_rating_average ? `${s.client_rating_average} (recorded)` : '—'}</td>
                  <td style={{ padding: '10px 14px' }}>
                    {s.performance_tier ? <span style={{ fontSize: '10px', fontWeight: 700, color: tierColors[s.performance_tier] || '#525252', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.performance_tier.replace('_', ' ')}</span> : <span style={{ color: '#9CA3AF' }}>—</span>}
                  </td>
                  <td style={{ padding: '10px 14px' }}><StatusBadge status={s.lifecycle_state} small /></td>
                  <td style={{ padding: '10px 14px' }}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button data-testid={`view-solver-${s.id}`} onClick={() => setViewSolver(s)} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', color: '#191919', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>View</button>
                      {canEdit && s.lifecycle_state === 'Registering' && (
                        <button onClick={async () => { try { await api.activateSolver(s.id); loadSolvers(); } catch (e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Activation could not be completed.'); } }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', backgroundColor: 'transparent', color: '#22C55E', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700 }}>Activate</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {solvers.length === 0 && <tr><td colSpan={11} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No solvers found</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {canEditStatus && editingStatus?.accountId === user?.id && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 24 }}>
          <section role="dialog" aria-modal="true" aria-labelledby="solver-status-title" style={{ backgroundColor: '#fff', width: 700, maxWidth: '100%', maxHeight: '90vh', overflowY: 'auto', padding: 24 }}>
            <h3 id="solver-status-title">Edit Solver</h3>
            <p>{editingStatus.full_name}</p>
            <form onSubmit={saveStatus}>
              <label htmlFor="solver-status">Status</label>
              <select id="solver-status" value={nextStatus} disabled={saving} onChange={event => setNextStatus(event.target.value)} style={{ display: 'block', width: '100%', padding: 10, margin: '8px 0' }}>
                {!['Registering', 'Active', 'Suspended', 'Inactive', 'Deactivated'].includes(editingStatus.lifecycle_state) && <option value={editingStatus.lifecycle_state}>{editingStatus.lifecycle_state}</option>}
                {['Registering', 'Active', 'Suspended', 'Inactive', 'Deactivated'].map(state => <option key={state} value={state}>{state}</option>)}
              </select>
              <p style={{ fontSize: 12 }}>HR can edit this record and change its status directly. Changes are audited; no external or legacy verification is required.</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                {EDIT_FIELDS.map(([key, label, type]) => <label key={key} htmlFor={`solver-edit-${key}`} style={{ fontSize: 12 }}>{label}
                  <input id={`solver-edit-${key}`} type={['number', 'date', 'email', 'tel'].includes(type) ? type : 'text'}
                    required={key === 'full_name' || key === 'phone_number'} disabled={saving} value={editValues[key] || ''}
                    min={type === 'number' ? 0 : undefined} max={type === 'number' && key !== 'jobs_completed' ? 100 : undefined}
                    step={key === 'jobs_completed' ? 1 : 'any'} onChange={event => setEditValues(values => ({ ...values, [key]: event.target.value }))}
                    style={{ display: 'block', width: '100%', padding: 8, marginTop: 4, boxSizing: 'border-box', border: '1px solid #ccc' }} />
                </label>)}
              </div>
              {statusError && <p role="alert">{statusError}</p>}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
                <button type="button" disabled={saving} onClick={() => setEditingStatus(null)}>Cancel</button>
                <button type="submit" disabled={saving} style={{ backgroundColor: '#FF353F', color: '#fff', border: 'none', padding: '10px 20px' }}>{saving ? 'Saving...' : 'Save Solver'}</button>
              </div>
            </form>
          </section>
        </div>
      )}

      {/* View Solver Modal */}
      {current && viewSolver && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '24px' }}>
          <div data-testid="solver-view-modal" style={{ backgroundColor: '#fff', width: '600px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '18px 24px', borderBottom: '3px solid #FF353F', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#FF353F', fontFamily: 'Barlow' }}>Solver Detail</div>
                <h3 style={{ margin: '4px 0 0', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.03em', fontSize: '20px' }}>{viewSolver.full_name}</h3>
              </div>
              <button onClick={() => setViewSolver(null)} style={{ background: 'none', border: '1px solid rgba(25,25,25,0.2)', padding: '6px 12px', cursor: 'pointer', fontSize: '11px', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase' }}>Close</button>
            </div>
            <div style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', fontSize: '12px', marginBottom: '20px' }}>
                <Field label="Phone" value={viewSolver.phone_number} />
                <Field label="Email" value={viewSolver.email} />
                <Field label="Region" value={viewSolver.region} />
                <Field label="Area covered" value={viewSolver.area_covered} />
                <Field label="Payment Method" value={viewSolver.payment_method} />
                <Field label="State" value={viewSolver.lifecycle_state} />
                <Field label="Tier" value={(viewSolver.performance_tier || '—').replace('_', ' ')} />
                <Field label="Accuracy" value={viewSolver.accuracy_score != null ? `${viewSolver.accuracy_score}%` : '—'} />
                <Field label="Reliability" value={viewSolver.reliability_score ? `${viewSolver.reliability_score}%` : '—'} />
                <Field label="Client Rating" value={viewSolver.client_rating_average != null ? `${viewSolver.client_rating_average} (recorded)` : '—'} />
                <Field label="Onboarded" value={viewSolver.onboarded_at ? new Date(viewSolver.onboarded_at).toLocaleDateString('en-GB') : '—'} />
              </div>
              <Field label="Vehicle Categories" value={(viewSolver.vehicle_categories || []).join(', ') || '—'} block />
              <Field label="Zones Covered" value={(viewSolver.zones_covered || []).join(', ') || '—'} block />
              {viewSolver.notes && <Field label="Notes" value={viewSolver.notes} block />}
              {!stats?.directory_only && <SolverWorkflow solverId={viewSolver.id} accountId={user?.id} onChanged={loadSolvers} />}
            </div>
          </div>
        </div>
      )}

      {/* Add Solver Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Register New Solver</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={saveSolver} style={{ padding: '24px' }}>
              {[{ key: 'full_name', label: 'Full Name', type: 'text' }, { key: 'phone_number', label: 'Phone (+254...)', type: 'tel' }, { key: 'region', label: 'Region', type: 'text' }, { key: 'area_covered', label: 'Area covered', type: 'text' }].map(f => (
                <div key={f.key} style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                  <input type={f.type} required={f.key === 'full_name' || f.key === 'phone_number'} value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                </div>
              ))}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '8px' }}>Vehicle Categories</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {VEHICLE_CATS.map(v => <label key={v} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}><input type="checkbox" checked={form.vehicle_categories.includes(v)} onChange={() => toggleCheckbox('vehicle_categories', v)} />{v}</label>)}
                </div>
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '8px' }}>Zones Covered</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {ZONES.map(z => <label key={z} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}><input type="checkbox" checked={form.zones_covered.includes(z)} onChange={() => toggleCheckbox('zones_covered', z)} />{z}</label>)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Arial' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>
                  {saving ? 'Registering...' : 'Register Solver'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, block }) {
  return (
    <div style={{ gridColumn: block ? '1 / -1' : 'auto', marginBottom: block ? '12px' : 0 }}>
      <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontFamily: 'Barlow' }}>{label}</div>
      <div style={{ fontSize: '13px', color: '#191919', marginTop: '2px' }}>{value || '—'}</div>
    </div>
  );
}
