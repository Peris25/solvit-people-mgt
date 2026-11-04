import React, { useState, useEffect, useCallback } from 'react';
import StatusBadge from '../components/StatusBadge';
import DeleteReviewDialog from '../components/DeleteReviewDialog';
import { useNotifications } from '../context/NotificationContext';
import CreateReviewDialog from '../components/CreateReviewDialog';
import PerformanceWorkflow, { CycleConfiguration } from '../components/PerformanceWorkflow';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function Performance() {
  const { user } = useAuth();
  const notifications=useNotifications();
  const [deleting,setDeleting]=useState([]);
  const [selected,setSelected]=useState([]);
  const isHR=["hr_admin","hr_manager","general_manager"].includes(user?.role);
  const [reviews, setReviews] = useState([]);
  const [cycles, setCycles] = useState([]);
  const [error, setError] = useState('');
  const [cycle, setCycle] = useState(null);
  const [nineBox, setNineBox] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('reviews');
  const [employees, setEmployees] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [talentDensity, setTalentDensity] = useState(null);
  const [viewReview, setViewReview] = useState(null);
  const [viewEmpName, setViewEmpName] = useState('');



  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [revRes, cycleRes, cyclesRes] = await Promise.all([api.getReviews(), api.getActiveCycle(), api.getReviewCycles()]);
      setCycles(cyclesRes.data);
      setViewReview(previous => revRes.data.find(row => row.id === (previous?.id || new URLSearchParams(window.location.search).get('review'))) || null);
      setReviews(revRes.data);
      setSelected([]);
      setCycle(cycleRes.data);
      if (['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role)) {
        const empRes = await api.getEmployees();
        setEmployees(empRes.data);
      }
    } catch { setError('Unable to load performance information. Please retry.'); } finally { setLoading(false); }
  }, [user?.role]);

  useEffect(() => { load(); if (['hr_admin', 'hr_manager', 'general_manager', 'executive'].includes(user?.role)) api.getTalentDensity().then(r => setTalentDensity(r.data)).catch(() => {}); }, [load, user?.role]);

  const loadNineBox = async () => {
    try { const res = await api.getNineBoxMatrix(); setNineBox(res.data); }
    catch { setError('Unable to load the HR matrix.'); }
  };

  const NINE_BOX_LABELS = { Stars: '#22C55E', Core_Contributor: '#3B82F6', Culture_Risk: '#F59E0B', Realignment_Needed: '#F97316', Exit_Track: '#EF4444' };

  const openView = async (r) => {
    try {
      const res = await api.getReview(r.id);
      setViewReview(res.data || r);
    } catch {
      setViewReview(null);
      setError('Unable to open this review. Please retry.');
    }
    const emp = employees.find(e => e.id === r.employee_id);
    setViewEmpName(r.employee_name || emp?.full_name || 'Employee unavailable');
  };

  const printPDF = () => {
    // Uses browser native print → "Save as PDF". Print CSS in index.css confines
    // output to the .solvit-print-area block.
    window.print();
  };

  // 9-box grid layout (rows = Values High→Low, cols = Performance Low→High)
  // Per FRD §2 correction: axes are Performance vs Values (NOT Potential)
  const NINE_BOX_GRID = [
    // Top row (High Values alignment)
    [{ key: 'Realignment_Needed', label: 'Realignment', sub: 'Strong values · low KPI — supportive intervention' },
     { key: 'Core_Contributor', label: 'Core Contributor', sub: 'Solid values · solid KPI', main: true },
     { key: 'Stars', label: 'Star', sub: 'High values · high KPI — promote / retain', main: true }],
    // Middle row (Solid Values)
    [{ key: 'Realignment_Needed', label: 'Realignment', sub: 'Solid values · low KPI' },
     { key: 'Core_Contributor', label: 'Core Player', sub: 'Solid values · solid KPI', main: true },
     { key: 'Core_Contributor', label: 'High Performer', sub: 'Solid values · high KPI', main: true }],
    // Bottom row (Low Values — values failure is non-negotiable)
    [{ key: 'Exit_Track', label: 'Exit Track', sub: 'Low values · low KPI — PIP or exit' },
     { key: 'Culture_Risk', label: 'Culture Risk', sub: 'Low values · solid KPI — values enforcement' },
     { key: 'Culture_Risk', label: 'Culture Risk', sub: 'Low values · high KPI — values overrule performance' }],
  ];

  const [draggedEmp, setDraggedEmp] = useState(null);

  const handleDrop = async (targetKey, e) => {
    e.preventDefault();
    if (!draggedEmp || draggedEmp.fromKey === targetKey) { setDraggedEmp(null); return; }
    // Optimistically update UI
    setNineBox(prev => {
      const next = { ...prev };
      next[draggedEmp.fromKey] = (next[draggedEmp.fromKey] || []).filter(e => e.employee_id !== draggedEmp.emp.employee_id);
      next[targetKey] = [...(next[targetKey] || []), draggedEmp.emp];
      return next;
    });
    try {
      await api.updateNineBoxPlacement(draggedEmp.emp.employee_id, targetKey, cycle?.cycle_year);
    } catch (err) {
      // Rollback
      setNineBox(prev => {
        const next = { ...prev };
        next[targetKey] = (next[targetKey] || []).filter(e => e.employee_id !== draggedEmp.emp.employee_id);
        next[draggedEmp.fromKey] = [...(next[draggedEmp.fromKey] || []), draggedEmp.emp];
        return next;
      });
    }
    setDraggedEmp(null);
  };

  const renderNineBoxGrid = () => {
    const placementCells = {};
    Object.keys(NINE_BOX_LABELS).forEach(p => placementCells[p] = (nineBox?.[p] || []));
    return (
      <div style={{ display: 'flex', gap: '24px' }}>
        <div style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', display: 'flex', alignItems: 'center', justifyContent: 'space-around', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', minHeight: '420px' }}>
          <span>Low</span><span>VALUES (Section B) →</span><span>High</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px' }}>
            {NINE_BOX_GRID.map((row, ri) => (
              row.map((cell, ci) => {
                const employees = placementCells[cell.key] || [];
                const cellsOfKey = NINE_BOX_GRID.flat().filter(c => c.key === cell.key);
                const idx = cellsOfKey.findIndex((c) => c === cell);
                const totalCellsOfKey = cellsOfKey.length;
                const myEmps = employees.filter((_, i) => i % totalCellsOfKey === idx);
                const color = NINE_BOX_LABELS[cell.key];
                const isDropTarget = draggedEmp && draggedEmp.fromKey !== cell.key;
                return (
                  <div key={`${ri}-${ci}`} data-testid={`ninebox-${cell.key}-${ri}-${ci}`}
                    onDragOver={(e) => { if (isDropTarget) { e.preventDefault(); e.currentTarget.style.backgroundColor = `${color}25`; } }}
                    onDragLeave={(e) => { e.currentTarget.style.backgroundColor = cell.main ? `${color}15` : `${color}08`; }}
                    onDrop={(e) => { e.currentTarget.style.backgroundColor = cell.main ? `${color}15` : `${color}08`; handleDrop(cell.key, e); }}
                    style={{
                      border: `2px solid ${color}`,
                      backgroundColor: cell.main ? `${color}15` : `${color}08`,
                      padding: '12px',
                      minHeight: '130px',
                      display: 'flex',
                      flexDirection: 'column',
                      transition: 'background-color 0.15s'
                    }}>
                    <div style={{ fontSize: '11px', fontWeight: 900, color, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{cell.label}</div>
                    <div style={{ fontSize: '10px', color: '#525252', marginBottom: '8px' }}>{cell.sub}</div>
                    <div style={{ flex: 1 }}>
                      {myEmps.map(emp => (
                        <div key={emp.employee_id}
                          draggable
                          onDragStart={() => setDraggedEmp({ emp, fromKey: cell.key })}
                          onDragEnd={() => setDraggedEmp(null)}
                          data-testid={`ninebox-emp-${emp.employee_id}`}
                          style={{ fontSize: '11px', padding: '4px 6px', borderTop: '1px solid rgba(25,25,25,0.06)', cursor: 'grab', userSelect: 'none', transition: 'background-color 0.1s' }}
                          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.6)'}
                          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                        >
                          <strong style={{ color: '#191919' }}>{emp.name}</strong>
                          <span style={{ color: '#525252', marginLeft: '4px' }}>· {emp.score}</span>
                        </div>
                      ))}
                      {myEmps.length === 0 && <div style={{ fontSize: '10px', color: '#9CA3AF', fontStyle: 'italic' }}>{isDropTarget ? '↓ drop here' : 'No employees'}</div>}
                    </div>
                  </div>
                );
              })
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>
            <span>Low (2.0+)</span><span>← KPI PERFORMANCE (Section A) →</span><span>High (1.0-1.49)</span>
          </div>
          <div style={{ marginTop: '12px', padding: '10px 14px', backgroundColor: '#FEF3C7', border: '1px solid #FCD34D', fontSize: '11px', color: '#78350F' }}>
            Tip: Drag an employee card between cells to reassign their 9-box placement. Y-axis = Section B values alignment (peer scores 7-10/4-7/&lt;4). X-axis = Section A KPI score. Values failure is non-negotiable — high KPI does NOT override low values.
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
          {cycle?.is_active ? <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Active cycle: {cycle.cycle_type} {cycle.cycle_year}</p> : <p>{['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role) ? 'Create an employee review with its own dates. Shared team cycles are optional.' : 'No review cycle currently active'}</p>}
        </div>
        {['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role) && (
          <button data-testid="create-review-btn" disabled={loading} onClick={() => { setError(''); setShowCreate(true); }} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Create Review</button>
        )}
      </div>

      {error && <div role="alert">{error} <button onClick={load}>Retry</button></div>}
      {['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role) && <CycleConfiguration cycles={cycles} onUpdated={load} />}
      {['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role) && <section style={{ background: '#fff', padding: 20, marginBottom: 20, borderRadius: 12 }}>
        <h2>Review meetings to arrange</h2>
        <p>Manager-approved assessments return to HR here. Open a review to arrange its meeting.</p>
        {reviews.filter(r => r.can_hr_review && r.status === 'Manager_Submitted' && !r.review_meeting).length === 0 ? <p>No review meetings awaiting scheduling.</p> :
          reviews.filter(r => r.can_hr_review && r.status === 'Manager_Submitted' && !r.review_meeting).map(r => <div key={r.id} style={{ display: 'flex', gap: 16, alignItems: 'center', padding: 12, borderBottom: '1px solid #eee' }}><strong>{r.employee_name || 'Employee unavailable'}</strong><span>{r.cycle_type?.replaceAll('_', ' ')} {r.cycle_year}</span><button onClick={() => openView(r)}>Arrange meeting</button></div>)}
      </section>}
      <p style={{ fontSize: '12px', color: '#525252' }}>Talent-density component weights below describe the aggregate dashboard metric, not an individual review score. Each review uses its approved cycle policy.</p>
      {/* Talent Density Score banner (correction §3) */}
      {talentDensity && (
        <div data-testid="talent-density-card" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '18px 22px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '24px', flexWrap: 'wrap' }}>
          <div style={{ flex: '0 0 auto' }}>
            <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#525252' }}>Talent Density</div>
            <div style={{ fontSize: '40px', fontWeight: 900, letterSpacing: '-0.04em', color: talentDensity.status === 'Healthy' ? '#22C55E' : talentDensity.status === 'Below Target' ? '#F97316' : '#FF353F' }}>
              {talentDensity.score_pct == null ? 'Awaiting data' : `${talentDensity.score_pct}%`}
            </div>
            <div style={{ fontSize: '11px', color: '#525252' }}>Target: {talentDensity.target_pct}% · <strong style={{ color: talentDensity.status === 'Healthy' ? '#22C55E' : talentDensity.status === 'Below Target' ? '#F97316' : '#FF353F' }}>{talentDensity.status}</strong></div>
          </div>
          <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
            <div style={{ padding: '10px 12px', backgroundColor: '#F9FAFB', border: '1px solid rgba(25,25,25,0.06)' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>Stars + Core %</div>
              <div style={{ fontSize: '20px', fontWeight: 900, color: '#191919' }}>{talentDensity.components.primary_stars_core_pct}%</div>
              <div style={{ fontSize: '10px', color: '#9CA3AF' }}>weight 60%</div>
            </div>
            <div style={{ padding: '10px 12px', backgroundColor: '#F9FAFB', border: '1px solid rgba(25,25,25,0.06)' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>Section B Values</div>
              <div style={{ fontSize: '20px', fontWeight: 900, color: '#191919' }}>{talentDensity.components.secondary_values_avg_pct}%</div>
              <div style={{ fontSize: '10px', color: '#9CA3AF' }}>weight 25%</div>
            </div>
            <div style={{ padding: '10px 12px', backgroundColor: '#F9FAFB', border: '1px solid rgba(25,25,25,0.06)' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>Alignment Survey</div>
              <div style={{ fontSize: '20px', fontWeight: 900, color: '#191919' }}>{talentDensity.components.tertiary_alignment_pct == null ? 'Awaiting data' : `${talentDensity.components.tertiary_alignment_pct}%`}</div>
              <div style={{ fontSize: '10px', color: '#9CA3AF' }}>weight 15%</div>
            </div>
          </div>
        </div>
      )}

      {isHR && <div style={{display:'flex',gap:12,alignItems:'center',marginBottom:16,flexWrap:'wrap'}}>
        <button type="button" onClick={()=>setSelected(reviews.filter(r=>r.can_delete).slice(0,100).map(r=>r.id))}>Select unsubmitted drafts</button>
        <button type="button" disabled={!selected.length} onClick={()=>setDeleting(reviews.filter(r=>selected.includes(r.id)&&r.can_delete))}>Delete selected ({selected.length})</button>
        {!!selected.length&&<button type="button" onClick={()=>setSelected([])}>Clear selection</button>}
      </div>}
      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {(['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role) ? ['reviews', '9-box'] : ['reviews']).map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === '9-box') loadNineBox(); }}
            style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t ? 700 : 400, color: tab === t ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {t === '9-box' ? '9-Box Matrix' : 'Reviews'}
          </button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'reviews' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
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
                  <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{r.employee_name || 'Employee unavailable'}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.cycle_type?.replace('_', ' ') || r.cycle_label || 'Historical'}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.cycle_year}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_a_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_b_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.section_c_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 900, color: '#191919' }}>{r.overall_score ?? '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{r.rating ? <StatusBadge status={r.rating} small /> : '—'}</td>
                  <td style={{ padding: '10px 14px' }}><StatusBadge status={r.status} small /></td>
                  <td style={{ padding: '10px 14px' }}>
                    {isHR&&r.can_delete&&<input type="checkbox" aria-label={`Select review for ${r.employee_name||r.employee_id}`} checked={selected.includes(r.id)} onChange={e=>setSelected(ids=>e.target.checked?[...ids,r.id].slice(0,100):ids.filter(id=>id!==r.id))} style={{marginRight:10}}/>}
                    <button data-testid={`view-review-${r.id}`} onClick={() => openView(r)} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>View</button>
                    {isHR&&r.can_delete&&<button type="button" aria-label={`Delete draft review for ${r.employee_name||r.employee_id}`} onClick={()=>setDeleting([r])} style={{marginLeft:8,padding:'8px 12px',border:'1px solid #fecaca',borderRadius:8,background:'#fff1f2',color:'#b91c1c',cursor:'pointer'}}>Delete draft</button>}
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
              <p style={{ fontSize: '11px', color: '#525252', margin: '2px 0 0' }}>Performance × Values (per FRD Correction §1) — placements based on completed reviews</p>
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

      {viewReview && (
        <div className="solvit-no-print" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '24px' }}>
          <div style={{ backgroundColor: '#fff', width: '720px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div className="solvit-no-print" style={{ padding: '18px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>Performance Review</h3>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button data-testid="review-pdf-btn" onClick={printPDF} style={{ padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' }}>Download PDF</button>
                <button onClick={() => setViewReview(null)} style={{ background: 'none', border: '1px solid rgba(25,25,25,0.2)', padding: '6px 12px', cursor: 'pointer', fontSize: '11px', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase' }}>Close</button>
              </div>
            </div>
            <div className="solvit-print-area" data-testid="review-view-modal" style={{ padding: '24px', fontFamily: 'Nunito Sans, sans-serif', color: '#191919' }}>
              <div style={{ borderBottom: '3px solid #FF353F', paddingBottom: '12px', marginBottom: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                  <div>
                    <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#FF353F', fontFamily: 'Barlow' }}>SOLVIT · Performance Review</div>
                    <h2 style={{ margin: '6px 0 0', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.03em', fontSize: '24px' }}>{viewReview.employee_name || viewEmpName}</h2>
                    <div style={{ fontSize: '12px', color: '#525252', marginTop: '2px' }}>{viewReview.cycle_type?.replace('_', ' ') || viewReview.cycle_label || 'Historical'} {viewReview.cycle_year}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Overall Score</div>
                    <div style={{ fontSize: '36px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.04em', color: '#FF353F' }}>{viewReview.overall_score ?? '—'}</div>
                    {viewReview.rating && <div style={{ fontSize: '11px', fontWeight: 700, color: '#191919' }}>{viewReview.rating}</div>}
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px', marginBottom: '20px' }}>
                {[
                  { label: 'Section A — KPI', value: viewReview.section_a_score, sub: 'Performance objectives' },
                  { label: 'Section B — Values', value: viewReview.section_b_score, sub: 'Peer 360° alignment' },
                  { label: `Section C - ${viewReview.scoring_policy?.section_c || 'Feedback'}`, value: viewReview.section_c_score, sub: viewReview.scoring_policy?.section_c || 'Historical source' },
                ].map(s => (
                  <div key={s.label} style={{ padding: '14px', backgroundColor: '#F5F5F5', borderLeft: '3px solid #191919' }}>
                    <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontFamily: 'Barlow' }}>{s.label}</div>
                    <div style={{ fontSize: '24px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.03em', color: '#191919', marginTop: '4px' }}>{s.value ?? '—'}</div>
                    <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>{s.sub}</div>
                  </div>
                ))}
              </div>

              <PerformanceWorkflow key={viewReview.id + viewReview.status} review={viewReview} onUpdated={load} />
              {viewReview.section_a_kpis && viewReview.section_a_kpis.length > 0 && (
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ margin: '0 0 8px', fontFamily: 'Barlow', fontWeight: 900, fontSize: '13px', letterSpacing: '-0.01em' }}>KPI Detail</h4>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead><tr style={{ backgroundColor: '#F5F5F5' }}>{['KPI','Weight','Score'].map(h => <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{h}</th>)}</tr></thead>
                    <tbody>
                      {viewReview.section_a_kpis.map((k, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid rgba(25,25,25,0.06)' }}>
                          <td style={{ padding: '8px 12px' }}>{k.name || k.kpi || '—'}</td>
                          <td style={{ padding: '8px 12px', color: '#525252' }}>{k.weight ? `${k.weight}%` : '—'}</td>
                          <td style={{ padding: '8px 12px', fontWeight: 700 }}>{k.score ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', fontSize: '12px' }}>
                <div><strong style={{ color: '#525252', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.12em', fontFamily: 'Barlow' }}>Status:</strong> <span style={{ marginLeft: '6px' }}>{viewReview.status || '—'}</span></div>
                <div><strong style={{ color: '#525252', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.12em', fontFamily: 'Barlow' }}>9-Box:</strong> <span style={{ marginLeft: '6px' }}>{(viewReview.nine_box_placement || '—').replace('_', ' ')}</span></div>
                {viewReview.manager_comments && <div style={{ gridColumn: '1 / -1' }}><strong style={{ color: '#525252', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.12em', fontFamily: 'Barlow' }}>Manager Comments:</strong><p style={{ marginTop: '4px' }}>{viewReview.manager_comments}</p></div>}
                {viewReview.employee_comments && <div style={{ gridColumn: '1 / -1' }}><strong style={{ color: '#525252', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.12em', fontFamily: 'Barlow' }}>Employee Comments:</strong><p style={{ marginTop: '4px' }}>{viewReview.employee_comments}</p></div>}
              </div>

              <div style={{ marginTop: '32px', paddingTop: '12px', borderTop: '1px solid rgba(25,25,25,0.08)', fontSize: '10px', color: '#9CA3AF', textAlign: 'center' }}>
                Generated from Solvit People Platform · {new Date().toLocaleDateString('en-GB')} · Confidential
              </div>
            </div>
          </div>
        </div>
      )}

      {deleting.length>0&&<DeleteReviewDialog reviews={deleting} onClose={()=>setDeleting([])} onDeleted={async()=>{setDeleting([]);await load();await notifications?.refresh?.();}}/>}
      {showCreate && <CreateReviewDialog employees={employees} onClose={() => setShowCreate(false)} onCreated={async () => { setShowCreate(false); await load(); }} />}

    </div>
  );
}
