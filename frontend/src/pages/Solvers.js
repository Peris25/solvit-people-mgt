import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function Solvers() {
  const { user } = useAuth();
  const [solvers, setSolvers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterState, setFilterState] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ full_name: '', phone_number: '', payment_method: 'MPesa', vehicle_categories: [], zones_covered: [] });
  const [saving, setSaving] = useState(false);

  const canEdit = ['hr_admin', 'hr_manager', 'line_manager'].includes(user?.role);

  useEffect(() => { loadSolvers(); }, [search, filterState]);

  const loadSolvers = async () => {
    setLoading(true);
    try {
      const [sRes, statsRes] = await Promise.all([
        api.getSolvers({ search, lifecycle_state: filterState || undefined }),
        api.getSolverStats()
      ]);
      setSolvers(sRes.data);
      setStats(statsRes.data);
    } finally { setLoading(false); }
  };

  const saveSolver = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createSolver(form);
      setShowForm(false);
      setForm({ full_name: '', phone_number: '', payment_method: 'MPesa', vehicle_categories: [], zones_covered: [] });
      loadSolvers();
    } finally { setSaving(false); }
  };

  const toggleCheckbox = (key, val) => {
    setForm(p => ({ ...p, [key]: p[key].includes(val) ? p[key].filter(x => x !== val) : [...p[key], val] }));
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
      {stats && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap' }}>
          {Object.entries(stats.by_state || {}).map(([state, count]) => (
            <div key={state} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 20px', minWidth: '100px' }}>
              <div style={{ fontSize: '22px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919' }}>{count}</div>
              <StatusBadge status={state} small />
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
        <input data-testid="search-solvers" placeholder="Search name or phone..." value={search} onChange={e => setSearch(e.target.value)}
          style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', width: '240px', fontFamily: 'Arial', outline: 'none' }} />
        <select data-testid="filter-solver-state" value={filterState} onChange={e => setFilterState(e.target.value)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', fontFamily: 'Arial' }}>
          <option value="">All States</option>
          {['Registering', 'Active', 'Suspended', 'Inactive', 'Deactivated'].map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Name', 'Phone', 'Zones', 'Vehicle Types', 'Accuracy', 'Reliability', 'Client Rating', 'Tier', 'State', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {solvers.map((s, i) => (
                <tr key={s.id} data-testid={`solver-row-${s.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{s.full_name}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{s.phone_number}</td>
                  <td style={{ padding: '10px 14px', color: '#525252', fontSize: '10px' }}>{(s.zones_covered || []).slice(0, 2).join(', ')}{(s.zones_covered || []).length > 2 ? ` +${s.zones_covered.length - 2}` : ''}</td>
                  <td style={{ padding: '10px 14px', color: '#525252', fontSize: '10px' }}>{(s.vehicle_categories || []).join(', ')}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: s.accuracy_score >= 90 ? '#166534' : '#191919' }}>{s.accuracy_score ? `${s.accuracy_score}%` : '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{s.reliability_score ? `${s.reliability_score}%` : '—'}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{s.client_rating_average ? `${s.client_rating_average}/5.0` : '—'}</td>
                  <td style={{ padding: '10px 14px' }}>
                    {s.performance_tier ? <span style={{ fontSize: '10px', fontWeight: 700, color: tierColors[s.performance_tier] || '#525252', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.performance_tier.replace('_', ' ')}</span> : <span style={{ color: '#9CA3AF' }}>—</span>}
                  </td>
                  <td style={{ padding: '10px 14px' }}><StatusBadge status={s.lifecycle_state} small /></td>
                  <td style={{ padding: '10px 14px' }}>
                    {canEdit && s.lifecycle_state === 'Registering' && (
                      <button onClick={async () => { await api.activateSolver(s.id); loadSolvers(); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', backgroundColor: 'transparent', color: '#22C55E', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Activate</button>
                    )}
                  </td>
                </tr>
              ))}
              {solvers.length === 0 && <tr><td colSpan={10} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No solvers found</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Solver Modal */}
      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Register New Solver</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={saveSolver} style={{ padding: '24px' }}>
              {[{ key: 'full_name', label: 'Full Name', type: 'text' }, { key: 'phone_number', label: 'Phone (+254...)', type: 'tel' }].map(f => (
                <div key={f.key} style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                  <input type={f.type} required value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
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
