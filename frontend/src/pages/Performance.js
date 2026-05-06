import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function Performance() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState([]);
  const [cycle, setCycle] = useState(null);
  const [nineBox, setNineBox] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('reviews');
  const [employees, setEmployees] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newReview, setNewReview] = useState({ employee_id: '', cycle_type: 'Year_End', cycle_year: new Date().getFullYear() });
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [revRes, cycleRes] = await Promise.all([api.getReviews(), api.getActiveCycle()]);
      setReviews(revRes.data);
      setCycle(cycleRes.data);
      if (['hr_admin', 'hr_manager'].includes(user?.role)) {
        const empRes = await api.getEmployees();
        setEmployees(empRes.data.filter(e => e.lifecycle_state === 'Active'));
      }
    } finally { setLoading(false); }
  };

  const loadNineBox = async () => {
    const res = await api.getNineBoxMatrix();
    setNineBox(res.data);
  };

  const createReview = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createReview(newReview);
      setShowCreate(false);
      load();
    } finally { setSaving(false); }
  };

  const NINE_BOX_LABELS = { Stars: '#22C55E', Core_Contributor: '#3B82F6', Culture_Risk: '#F59E0B', Realignment_Needed: '#F97316', Exit_Track: '#EF4444' };

  // 9-box grid layout (rows = Potential High→Low, cols = Performance Low→High)
  const NINE_BOX_GRID = [
    // Top row (High potential)
    [{ key: 'Realignment_Needed', label: 'Inconsistent Star', sub: 'High potential / low perf' },
     { key: 'Stars', label: 'Future Leader', sub: 'High potential / met perf', main: true },
     { key: 'Stars', label: 'Star', sub: 'Promote / retain', main: true }],
    // Middle row (Medium potential)
    [{ key: 'Realignment_Needed', label: 'Up or Out', sub: 'Develop or exit' },
     { key: 'Core_Contributor', label: 'Core Player', sub: 'Solid contributor', main: true },
     { key: 'Core_Contributor', label: 'High Performer', sub: 'Stretch role', main: true }],
    // Bottom row (Low potential)
    [{ key: 'Exit_Track', label: 'Exit Track', sub: 'Low / low — manage out' },
     { key: 'Culture_Risk', label: 'Effective', sub: 'Low pot / met perf' },
     { key: 'Culture_Risk', label: 'Trusted Pro', sub: 'Strong perf, capped potential' }],
  ];

  const renderNineBoxGrid = () => {
    const placementCells = {};
    Object.keys(NINE_BOX_LABELS).forEach(p => placementCells[p] = (nineBox?.[p] || []));
    return (
      <div style={{ display: 'flex', gap: '24px' }}>
        {/* Y-axis label */}
        <div style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', display: 'flex', alignItems: 'center', justifyContent: 'space-around', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', minHeight: '420px' }}>
          <span>Low</span><span>POTENTIAL →</span><span>High</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
            {NINE_BOX_GRID.map((row, ri) => (
              row.map((cell, ci) => {
                const employees = placementCells[cell.key] || [];
                // Distribute employees by index across cells of same key
                const cellsOfKey = NINE_BOX_GRID.flat().filter(c => c.key === cell.key);
                const idx = cellsOfKey.findIndex((c, i) => c === cell);
                const totalCellsOfKey = cellsOfKey.length;
                const myEmps = employees.filter((_, i) => i % totalCellsOfKey === idx);
                const color = NINE_BOX_LABELS[cell.key];
                return (
                  <div key={`${ri}-${ci}`} data-testid={`ninebox-${cell.key}-${ri}-${ci}`}
                    style={{
                      border: `2px solid ${color}`,
                      backgroundColor: cell.main ? `${color}15` : `${color}08`,
                      padding: '12px',
                      minHeight: '130px',
                      display: 'flex',
                      flexDirection: 'column'
                    }}>
                    <div style={{ fontSize: '11px', fontWeight: 900, color, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{cell.label}</div>
                    <div style={{ fontSize: '10px', color: '#525252', marginBottom: '8px' }}>{cell.sub}</div>
                    <div style={{ flex: 1 }}>
                      {myEmps.map(e => (
                        <div key={e.employee_id} style={{ fontSize: '11px', padding: '3px 0', borderTop: '1px solid rgba(25,25,25,0.06)' }}>
                          <strong style={{ color: '#191919' }}>{e.name}</strong>
                          <span style={{ color: '#525252', marginLeft: '4px' }}>· {e.score}</span>
                        </div>
                      ))}
                      {myEmps.length === 0 && <div style={{ fontSize: '10px', color: '#9CA3AF', fontStyle: 'italic' }}>No employees</div>}
                    </div>
                  </div>
                );
              })
            ))}
          </div>
          {/* X-axis label */}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>
            <span>Below</span><span>← PERFORMANCE →</span><span>Exceeded</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div data-testid="performance-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Performance Reviews</h1>
          {cycle && <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Active cycle: {cycle.cycle_type} {cycle.cycle_year}</p>}
        </div>
        {['hr_admin', 'hr_manager'].includes(user?.role) && (
          <button data-testid="create-review-btn" onClick={() => setShowCreate(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Create Review</button>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {['reviews', '9-box'].map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === '9-box') loadNineBox(); }}
            style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t ? 700 : 400, color: tab === t ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {t === '9-box' ? '9-Box Matrix' : 'Reviews'}
          </button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'reviews' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Employee', 'Cycle', 'Year', 'Section A', 'Section B', 'Section C', 'Overall', 'Rating', 'Status', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reviews.map((r, i) => (
                <tr key={r.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{r.employee_id?.substring(0, 8)}...</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.cycle_type?.replace('_', ' ')}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.cycle_year}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_a_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_b_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_c_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 900, color: '#191919' }}>{r.overall_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.rating ? <StatusBadge status={r.rating} small /> : '—'}</td>
                  <td style={{ padding: '10px 14px' }}><StatusBadge status={r.status} small /></td>
                  <td style={{ padding: '10px 14px' }}>
                    <button style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>View</button>
                  </td>
                </tr>
              ))}
              {reviews.length === 0 && <tr><td colSpan={10} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No reviews yet</td></tr>}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px' }}>
            <div>
              <h3 style={{ fontWeight: 900, fontSize: '16px', margin: 0, color: '#191919' }}>9-Box Talent Matrix — {cycle?.cycle_year}</h3>
              <p style={{ fontSize: '11px', color: '#525252', margin: '2px 0 0' }}>Performance × Potential — placements based on completed reviews</p>
            </div>
            {nineBox && (
              <div style={{ display: 'flex', gap: '12px', fontSize: '11px' }}>
                {Object.entries(NINE_BOX_LABELS).map(([k, c]) => {
                  const count = (nineBox[k] || []).length;
                  return <div key={k} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '10px', height: '10px', backgroundColor: c, display: 'inline-block' }} />
                    <span style={{ fontWeight: 700, color: c }}>{count}</span>
                    <span style={{ color: '#525252' }}>{k.replace('_', ' ')}</span>
                  </div>;
                })}
              </div>
            )}
          </div>
          {nineBox ? renderNineBoxGrid() : <div style={{ textAlign: 'center', color: '#9CA3AF', padding: '32px' }}>Click "9-Box Matrix" to load data</div>}
        </div>
      )}

      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '440px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Create Performance Review</h3>
              <button onClick={() => setShowCreate(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={createReview} style={{ padding: '24px' }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Employee</label>
                <select required value={newReview.employee_id} onChange={e => setNewReview(p => ({ ...p, employee_id: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                  <option value="">Select employee...</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.full_name} — {e.role_title}</option>)}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Cycle Type</label>
                  <select value={newReview.cycle_type} onChange={e => setNewReview(p => ({ ...p, cycle_type: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                    <option value="Mid_Year">Mid Year</option>
                    <option value="Year_End">Year End</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Year</label>
                  <input type="number" value={newReview.cycle_year} onChange={e => setNewReview(p => ({ ...p, cycle_year: parseInt(e.target.value) }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none', boxSizing: 'border-box' }} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowCreate(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Arial' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>Create Review</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
