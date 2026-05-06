/**
 * EmployeeDashboard — FTE personal action surface.
 * Shows only what is relevant to the individual: tasks, performance, leave, recognition.
 * Uses a horizontal top tab bar (no sidebar nav inside the page).
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

const TABS = [
  { key: 'dashboard', label: 'My Dashboard' },
  { key: 'reviews',   label: 'My Reviews' },
  { key: 'dev',       label: 'My Development' },
  { key: 'recog',     label: 'My Recognition' },
  { key: 'leave',     label: 'Leave' },
];

const RATING_LABEL = (rating) => {
  if (!rating) return '—';
  if (typeof rating === 'string') return rating;
  return rating;
};

export default function EmployeeDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('dashboard');
  const [tasks, setTasks] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [leaveBalance, setLeaveBalance] = useState(null);
  const [recognitions, setRecognitions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [t, r, lb, rg] = await Promise.allSettled([
          api.getMyFormTasks(),
          api.getReviews(),
          api.getLeaveBalances(user?.employee_id || user?.id),
          api.getRecognitions({ nominee_id: user?.employee_id || user?.id }),
        ]);
        if (cancelled) return;
        if (t.status === 'fulfilled') setTasks(t.value.data || []);
        if (r.status === 'fulfilled') setReviews(r.value.data || []);
        if (lb.status === 'fulfilled') setLeaveBalance(lb.value.data);
        if (rg.status === 'fulfilled') setRecognitions(rg.value.data || []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    if (user) load();
    return () => { cancelled = true; };
  }, [user]);

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();
  const firstName = (user?.full_name || user?.email || '').split(' ')[0];

  const latestReview = reviews?.[0];
  const overdueTasks = tasks.filter(t => t.due_date && new Date(t.due_date) < new Date());
  const sortedTasks = [...tasks].sort((a, b) => {
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return new Date(a.due_date) - new Date(b.due_date);
  });

  return (
    <div data-testid="employee-dashboard" style={{ fontFamily: 'Arial, Helvetica, sans-serif', minHeight: '100vh' }}>
      {/* Top bar / greeting */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px' }}>
        <div>
          <h1 data-testid="emp-greeting" style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', margin: 0, color: '#191919' }}>
            {greeting}, {firstName}
          </h1>
          <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>
            {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })} · EAT
          </p>
        </div>
      </div>

      {/* Top tab bar */}
      <div data-testid="emp-tabs" style={{ display: 'flex', gap: '0', borderBottom: '1px solid rgba(25,25,25,0.08)', marginBottom: '24px' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`emp-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            style={{
              padding: '12px 20px', background: 'none', border: 'none',
              borderBottom: tab === t.key ? '2px solid #FF353F' : '2px solid transparent',
              color: tab === t.key ? '#191919' : '#525252',
              fontSize: '13px', fontWeight: tab === t.key ? 700 : 500,
              cursor: 'pointer', fontFamily: 'Arial', letterSpacing: '-0.01em',
              transition: 'all 0.15s'
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#525252' }}>Loading...</div>
      ) : tab === 'dashboard' ? (
        <>
          {/* Zone 1 — My Tasks */}
          <div data-testid="my-tasks-zone" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', marginBottom: '20px' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#191919' }}>My Tasks</span>
              {overdueTasks.length > 0 && <span style={{ fontSize: '11px', color: '#FF353F', fontWeight: 700 }}>{overdueTasks.length} overdue</span>}
            </div>
            {tasks.length === 0 ? (
              <div data-testid="emp-no-tasks" style={{ padding: '32px 20px', textAlign: 'center', color: '#22C55E', fontWeight: 700 }}>
                ✓ You are up to date
              </div>
            ) : (
              <div>
                {sortedTasks.slice(0, 8).map(t => {
                  const overdue = t.due_date && new Date(t.due_date) < new Date();
                  return (
                    <div key={t.id} data-testid={`emp-task-${t.id}`} style={{ padding: '12px 20px', borderBottom: '1px solid rgba(25,25,25,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '13px', fontWeight: 600, color: '#191919' }}>{t.form_title || t.title || 'Form Task'}</div>
                        <div style={{ fontSize: '11px', color: overdue ? '#FF353F' : '#525252', marginTop: '3px' }}>
                          {t.form_id || t.module || ''} {t.due_date && `· Due ${new Date(t.due_date).toLocaleDateString('en-GB')}`}
                        </div>
                      </div>
                      <button
                        onClick={() => navigate('/my-tasks')}
                        style={{ padding: '6px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}
                      >
                        Complete
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {/* Zone 2 — My Performance */}
            <div data-testid="my-performance-zone" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px 24px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', marginBottom: '12px' }}>My Performance</div>
              {latestReview && latestReview.overall_score ? (
                <>
                  <div style={{ fontSize: '48px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', lineHeight: 1 }}>
                    {latestReview.overall_score?.toFixed(1)}
                  </div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#FF353F', marginTop: '4px' }}>
                    {RATING_LABEL(latestReview.rating)}
                  </div>
                  <div style={{ marginTop: '16px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                    {[
                      { l: 'Section A', v: latestReview.section_a_score },
                      { l: 'Section B', v: latestReview.section_b_score },
                      { l: 'Section C', v: latestReview.section_c_score },
                    ].map(s => (
                      <div key={s.l} style={{ padding: '8px', backgroundColor: '#F9FAFB' }}>
                        <div style={{ fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>{s.l}</div>
                        <div style={{ fontSize: '16px', fontWeight: 900, color: '#191919' }}>{s.v?.toFixed(1) || '—'}</div>
                      </div>
                    ))}
                  </div>
                  {latestReview.nine_box_placement && (
                    <div style={{ marginTop: '12px', fontSize: '11px', color: '#525252' }}>
                      9-Box · <strong style={{ color: '#191919' }}>{latestReview.nine_box_placement.replace(/_/g, ' ')}</strong>
                    </div>
                  )}
                </>
              ) : (
                <div style={{ fontSize: '13px', color: '#525252' }}>First review pending</div>
              )}
            </div>

            {/* Zone 3 — My Leave + My Recognition */}
            <div style={{ display: 'grid', gridTemplateRows: '1fr 1fr', gap: '20px' }}>
              <div data-testid="my-leave-zone" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px 24px' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', marginBottom: '8px' }}>My Leave</div>
                <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-end' }}>
                  <div>
                    <div style={{ fontSize: '32px', fontWeight: 900, color: '#191919' }}>{leaveBalance?.annual_days_remaining ?? '—'}</div>
                    <div style={{ fontSize: '10px', color: '#525252', textTransform: 'uppercase', letterSpacing: '0.15em' }}>Annual</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '32px', fontWeight: 900, color: '#191919' }}>{leaveBalance?.sick_days_remaining ?? '—'}</div>
                    <div style={{ fontSize: '10px', color: '#525252', textTransform: 'uppercase', letterSpacing: '0.15em' }}>Sick</div>
                  </div>
                </div>
                <button
                  data-testid="emp-request-leave-btn"
                  onClick={() => navigate('/leave')}
                  style={{ marginTop: '12px', padding: '8px 16px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}
                >Request Leave</button>
              </div>

              <div data-testid="my-recog-zone" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px 24px' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', marginBottom: '8px' }}>My Recognition</div>
                {recognitions.length === 0 ? (
                  <div style={{ fontSize: '12px', color: '#9CA3AF' }}>No recognitions yet</div>
                ) : (
                  recognitions.slice(0, 3).map(r => (
                    <div key={r.id} style={{ padding: '6px 0', borderBottom: '1px solid rgba(25,25,25,0.05)', fontSize: '11px' }}>
                      <div style={{ fontWeight: 700, color: '#191919' }}>{r.recognition_type || r.values_demonstrated?.[0] || 'Recognition'}</div>
                      <div style={{ color: '#525252', fontSize: '10px' }}>
                        {r.nominator_name || r.is_anonymous ? 'Anonymous' : ''} · {r.created_at ? new Date(r.created_at).toLocaleDateString('en-GB') : ''}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </>
      ) : tab === 'reviews' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '12px' }}>My Review History</div>
          {reviews.length === 0 ? <div style={{ color: '#9CA3AF', fontSize: '12px' }}>No reviews yet</div> : reviews.map(r => (
            <div key={r.id} style={{ padding: '10px 0', borderBottom: '1px solid rgba(25,25,25,0.05)', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '13px' }}>{r.cycle_type?.replace('_', ' ')} {r.cycle_year}</div>
                <div style={{ fontSize: '11px', color: '#525252' }}>{r.status}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 900, fontSize: '20px' }}>{r.overall_score?.toFixed(1) || '—'}</div>
                <div style={{ fontSize: '10px', color: '#525252' }}>{r.rating || ''}</div>
              </div>
            </div>
          ))}
        </div>
      ) : tab === 'dev' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', textAlign: 'center' }}>
          <button onClick={() => navigate('/lnd')} style={{ padding: '12px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', cursor: 'pointer' }}>Open Learning & Development</button>
        </div>
      ) : tab === 'recog' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '12px' }}>All Recognition</div>
          {recognitions.length === 0 ? <div style={{ color: '#9CA3AF', fontSize: '12px' }}>No recognitions yet</div> : recognitions.map(r => (
            <div key={r.id} style={{ padding: '10px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
              <div style={{ fontWeight: 700 }}>{r.recognition_type}</div>
              <div style={{ fontSize: '11px', color: '#525252' }}>{r.specific_behaviour}</div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', textAlign: 'center' }}>
          <button onClick={() => navigate('/leave')} style={{ padding: '12px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', cursor: 'pointer' }}>Open Leave Management</button>
        </div>
      )}
    </div>
  );
}
