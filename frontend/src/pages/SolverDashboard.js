/**
 * SolverDashboard — mobile-first 5-tab bottom-nav interface for Solvers.
 * Data-light, action-focused. Designed for low-bandwidth.
 */
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

const TABS = [
  { key: 'home',    label: 'Home',        icon: '⌂' },
  { key: 'perf',    label: 'Performance', icon: '◎' },
  { key: 'recog',   label: 'Awards',      icon: '★' },
  { key: 'survey',  label: 'Surveys',     icon: '✎' },
  { key: 'tasks',   label: 'Tasks',       icon: '✓' },
];

const TIER_COLORS = {
  Elite: '#EAB308', 'High Performer': '#22C55E', Standard: '#3B82F6', 'Improvement Required': '#FF353F'
};

const Dial = ({ label, value }) => {
  const v = Math.max(0, Math.min(100, value || 0));
  const stroke = v >= 80 ? '#22C55E' : v >= 60 ? '#EAB308' : '#FF353F';
  return (
    <div data-testid={`solver-dial-${label.toLowerCase()}`} style={{ textAlign: 'center', padding: '8px' }}>
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="34" fill="none" stroke="#E5E7EB" strokeWidth="6" />
        <circle cx="40" cy="40" r="34" fill="none" stroke={stroke} strokeWidth="6"
          strokeDasharray={`${(v / 100) * 213.6} 213.6`} strokeDashoffset="0"
          transform="rotate(-90 40 40)" strokeLinecap="round" />
        <text x="40" y="46" textAnchor="middle" fontSize="18" fontWeight="900" fill="#191919">{v}</text>
      </svg>
      <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginTop: '4px' }}>{label}</div>
    </div>
  );
};

export default function SolverDashboard() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState('home');
  const [solver, setSolver] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [awards, setAwards] = useState([]);
  const [activeSurvey, setActiveSurvey] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [tRes, aRes, sRes] = await Promise.allSettled([
          api.getMyFormTasks(),
          api.getRecognitions({ nominee_id: user?.id }),
          api.getSurveyWindows(),
        ]);
        if (cancelled) return;
        if (tRes.status === 'fulfilled') setTasks(tRes.value.data || []);
        if (aRes.status === 'fulfilled') setAwards(aRes.value.data || []);
        if (sRes.status === 'fulfilled') {
          const open = (sRes.value.data || []).find(s => s.status === 'Open' || s.is_open);
          setActiveSurvey(open);
        }
        // Pseudo solver record from user
        setSolver({
          full_name: user?.full_name,
          performance_tier: user?.performance_tier || 'Standard',
          jobs_this_month: user?.jobs_this_month || 0,
          accuracy: user?.accuracy_score || 75,
          reliability: user?.reliability_score || 80,
          timeliness: user?.timeliness_score || 78,
          client_rating: user?.client_rating || 82,
        });
      } catch (_) { /* swallow */ }
    };
    if (user) load();
    return () => { cancelled = true; };
  }, [user]);

  const tier = solver?.performance_tier || 'Standard';

  return (
    <div data-testid="solver-dashboard" style={{ fontFamily: 'Arial, Helvetica, sans-serif', maxWidth: '480px', margin: '0 auto', minHeight: '100vh', paddingBottom: '72px', backgroundColor: '#F5F5F5' }}>
      {/* Top header */}
      <div style={{ backgroundColor: '#191919', color: '#fff', padding: '20px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.2em', color: 'rgba(255,255,255,0.5)' }}>Solvit Solver</div>
          <div data-testid="solver-name" style={{ fontSize: '16px', fontWeight: 900 }}>{user?.full_name || user?.email}</div>
        </div>
        <button onClick={logout} style={{ background: 'none', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '6px 12px', fontSize: '10px', cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Sign Out</button>
      </div>

      <div style={{ padding: '16px' }}>
        {/* Active survey banner */}
        {activeSurvey && (
          <div data-testid="solver-survey-banner" style={{ backgroundColor: '#FEF2F2', border: '1px solid #FF353F', padding: '12px', marginBottom: '16px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: '#FF353F', textTransform: 'uppercase', letterSpacing: '0.15em' }}>Survey Open</div>
            <div style={{ fontSize: '13px', color: '#191919', marginTop: '4px' }}>Complete the active alignment survey on the Surveys tab.</div>
          </div>
        )}

        {tab === 'home' && (
          <>
            <div data-testid="solver-tier-card" style={{ backgroundColor: '#fff', padding: '16px', borderLeft: `4px solid ${TIER_COLORS[tier] || '#525252'}`, marginBottom: '12px' }}>
              <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>Performance Tier</div>
              <div style={{ fontSize: '20px', fontWeight: 900, color: TIER_COLORS[tier] || '#191919', marginTop: '4px' }}>{tier}</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '12px' }}>
              <div style={{ backgroundColor: '#fff', padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: 900 }}>{solver?.jobs_this_month ?? 0}</div>
                <div style={{ fontSize: '9px', textTransform: 'uppercase', color: '#525252', letterSpacing: '0.12em', marginTop: '2px' }}>Jobs MTD</div>
              </div>
              <div style={{ backgroundColor: '#fff', padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: 900 }}>{solver?.accuracy ?? '—'}</div>
                <div style={{ fontSize: '9px', textTransform: 'uppercase', color: '#525252', letterSpacing: '0.12em', marginTop: '2px' }}>Accuracy</div>
              </div>
              <div style={{ backgroundColor: '#fff', padding: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: 900 }}>{solver?.client_rating ?? '—'}</div>
                <div style={{ fontSize: '9px', textTransform: 'uppercase', color: '#525252', letterSpacing: '0.12em', marginTop: '2px' }}>Client Rating</div>
              </div>
            </div>

            <div style={{ backgroundColor: '#fff', padding: '12px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '8px' }}>Announcements</div>
              <div style={{ fontSize: '12px', color: '#191919' }}>Welcome — check the Tasks tab for any pending acknowledgements.</div>
            </div>
          </>
        )}

        {tab === 'perf' && (
          <div style={{ backgroundColor: '#fff', padding: '16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              <Dial label="Accuracy" value={solver?.accuracy} />
              <Dial label="Reliability" value={solver?.reliability} />
              <Dial label="Timeliness" value={solver?.timeliness} />
              <Dial label="Client Rating" value={solver?.client_rating} />
            </div>
          </div>
        )}

        {tab === 'recog' && (
          <div style={{ backgroundColor: '#fff', padding: '16px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '8px' }}>Awards</div>
            {awards.length === 0 ? (
              <div style={{ fontSize: '12px', color: '#9CA3AF' }}>No awards yet — keep up the great work.</div>
            ) : awards.map(a => (
              <div key={a.id} data-testid={`solver-award-${a.id}`} style={{ padding: '8px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                <div style={{ fontWeight: 700, fontSize: '13px' }}>{a.recognition_type || 'Top Solver'}</div>
                <div style={{ fontSize: '11px', color: '#525252' }}>{a.created_at ? new Date(a.created_at).toLocaleDateString('en-GB') : ''} {a.amount_kes ? `· KES ${a.amount_kes.toLocaleString()}` : ''}</div>
              </div>
            ))}
          </div>
        )}

        {tab === 'survey' && (
          <div style={{ backgroundColor: '#fff', padding: '16px' }}>
            {activeSurvey ? (
              <>
                <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '8px' }}>{activeSurvey.title || 'Quarterly Alignment Survey'}</div>
                <div style={{ fontSize: '11px', color: '#525252', marginBottom: '12px' }}>Tap to begin — takes about 5 minutes.</div>
                <button
                  data-testid="solver-start-survey"
                  onClick={() => window.location.href = '/forms?form=form-05'}
                  style={{ width: '100%', padding: '12px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', cursor: 'pointer' }}
                >Start Survey</button>
              </>
            ) : (
              <div style={{ fontSize: '12px', color: '#9CA3AF', textAlign: 'center', padding: '24px 0' }}>No active survey window. We'll notify you when the next one opens.</div>
            )}
          </div>
        )}

        {tab === 'tasks' && (
          <div style={{ backgroundColor: '#fff', padding: '16px' }}>
            {tasks.length === 0 ? (
              <div data-testid="solver-no-tasks" style={{ fontSize: '12px', color: '#22C55E', textAlign: 'center', padding: '24px 0', fontWeight: 700 }}>✓ All clear</div>
            ) : tasks.map(t => (
              <div key={t.id} data-testid={`solver-task-${t.id}`} style={{ padding: '10px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                <div style={{ fontSize: '13px', fontWeight: 600 }}>{t.form_title || t.title}</div>
                <div style={{ fontSize: '11px', color: '#525252' }}>{t.form_id || ''}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom nav */}
      <div data-testid="solver-bottom-nav" style={{ position: 'fixed', bottom: 0, left: 0, right: 0, maxWidth: '480px', margin: '0 auto', backgroundColor: '#191919', display: 'flex', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`solver-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            style={{
              flex: 1, padding: '10px 4px', background: 'none', border: 'none',
              color: tab === t.key ? '#FF353F' : 'rgba(255,255,255,0.6)',
              cursor: 'pointer', fontFamily: 'Arial', display: 'flex', flexDirection: 'column',
              alignItems: 'center', gap: '2px',
            }}
          >
            <span style={{ fontSize: '18px' }}>{t.icon}</span>
            <span style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700 }}>{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
