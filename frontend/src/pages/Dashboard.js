/**
 * HR Admin Dashboard — Section C layout (Alerts → Kanban+Calendar → Stats Bar).
 * Primary operational control surface for HR Admin & HR Manager.
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';

const KPI_TILE = ({ label, value, sub, color = '#191919', testId, onClick }) => (
  <div
    data-testid={testId || `kpi-${label.toLowerCase().replace(/ /g,'-')}`}
    onClick={onClick}
    style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 16px', cursor: onClick ? 'pointer' : 'default', transition: 'all 0.15s' }}
    onMouseEnter={e => onClick && (e.currentTarget.style.borderColor = '#FF353F')}
    onMouseLeave={e => onClick && (e.currentTarget.style.borderColor = 'rgba(25,25,25,0.08)')}
  >
    <div style={{ fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>{label}</div>
    <div style={{ fontSize: '26px', fontWeight: 900, letterSpacing: '-0.04em', color, marginTop: '4px' }}>{value ?? '—'}</div>
    {sub && <div style={{ fontSize: '10px', color: '#525252', marginTop: '2px' }}>{sub}</div>}
  </div>
);

const ALERT_PRIORITY = (n) => {
  const cat = (n.category || '').toLowerCase();
  const title = (n.title || '').toLowerCase();
  if (n.priority === 'high' || cat === 'exit' || title.includes('overdue') || title.includes('critical') || title.includes('failed')) return 'critical';
  if (cat === 'compliance' || cat === 'probation' || title.includes('elevated') || title.includes('deadline')) return 'elevated';
  return 'info';
};

const ALERT_COLORS = {
  critical: { bg: '#FEF2F2', border: '#FF353F', text: '#7F1D1D', label: 'CRITICAL' },
  elevated: { bg: '#FFF7ED', border: '#F97316', text: '#7C2D12', label: 'ELEVATED' },
  info:     { bg: '#EFF6FF', border: '#3B82F6', text: '#1E3A8A', label: 'INFO' },
};

const TalentDensityGauge = ({ data }) => {
  const score = data?.score_pct || 0;
  const target = data?.target_pct || 85;
  const pct = Math.max(0, Math.min(100, score));
  const stroke = score >= target ? '#22C55E' : score >= 70 ? '#EAB308' : '#FF353F';
  return (
    <div data-testid="talent-density-gauge" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px', textAlign: 'center' }}>
      <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', marginBottom: '8px' }}>Talent Density</div>
      <svg width="100" height="56" viewBox="0 0 100 56" style={{ display: 'block', margin: '0 auto' }}>
        <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="#E5E7EB" strokeWidth="8" />
        <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke={stroke} strokeWidth="8"
          strokeDasharray={`${(pct / 100) * 125.6} 125.6`} strokeLinecap="round" />
      </svg>
      <div style={{ fontSize: '20px', fontWeight: 900, color: '#191919', marginTop: '-4px' }}>{score.toFixed(0)}%</div>
      <div style={{ fontSize: '10px', color: '#525252' }}>Target {target}%</div>
    </div>
  );
};

const KanbanCard = ({ emp, onClick }) => {
  const tenureStr = emp.start_date ? (() => {
    const days = Math.floor((Date.now() - new Date(emp.start_date)) / 86400000);
    return days > 365 ? `${Math.floor(days/365)}y ${Math.floor((days%365)/30)}m` : `${Math.floor(days/30)}m`;
  })() : null;
  const daysInState = emp.updated_at ? Math.floor((Date.now() - new Date(emp.updated_at)) / 86400000) : 0;
  return (
    <div data-testid={`kanban-card-${emp.id}`} onClick={onClick} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '10px 12px', marginBottom: '6px', cursor: 'pointer' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
        <div style={{ fontWeight: 700, fontSize: '12px', color: '#191919' }}>{emp.full_name}</div>
        <StatusBadge status={emp.lifecycle_state} small />
      </div>
      <div style={{ fontSize: '10px', color: '#525252' }}>{emp.role_title}</div>
      <div style={{ display: 'flex', gap: '6px', marginTop: '4px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '9px', backgroundColor: '#F5F5F5', padding: '1px 5px', color: '#525252' }}>{emp.department}</span>
        {tenureStr && <span style={{ fontSize: '9px', color: '#525252' }}>{tenureStr}</span>}
        {daysInState > 0 && <span style={{ fontSize: '9px', color: '#525252' }}>· {daysInState}d in state</span>}
      </div>
      {emp.last_performance_score && (
        <div style={{ fontSize: '9px', color: '#525252', marginTop: '4px' }}>Perf <strong>{emp.last_performance_score}</strong></div>
      )}
    </div>
  );
};

const COLUMNS = [
  { key: 'Onboarding', label: 'Onboarding', color: '#3B82F6', bg: '#EFF6FF' },
  { key: 'Active',     label: 'Active',     color: '#22C55E', bg: '#F0FDF4' },
  { key: 'Exiting',    label: 'Exiting',    color: '#F97316', bg: '#FFF7ED' },
  { key: 'Exited',     label: 'Exited',     color: '#6B7280', bg: '#F9FAFB' },
];

const EVENT_COLOR = (type) => {
  const t = (type || '').toLowerCase();
  if (t.includes('review')) return '#3B82F6';
  if (t.includes('recog')) return '#22C55E';
  if (t.includes('compl') || t.includes('paye') || t.includes('nssf')) return '#F97316';
  if (t.includes('overdue')) return '#FF353F';
  return '#525252';
};

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [kanban, setKanban] = useState({ Onboarding: [], Active: [], Exiting: [], Exited: [] });
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [talent, setTalent] = useState(null);
  const [attrition, setAttrition] = useState(null);
  const [search, setSearch] = useState('');
  const [dismissed, setDismissed] = useState(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [k, s, n, c, td, va] = await Promise.allSettled([
        api.getKanban(), api.getEmployeeStats(), api.getNotifications(),
        api.getCalendarEvents(14), api.getTalentDensity(),
        api.getVoluntaryAttrition(),
      ]);
      if (k.status === 'fulfilled') setKanban(k.value.data || {});
      if (s.status === 'fulfilled') setStats(s.value.data);
      if (n.status === 'fulfilled') setAlerts((n.value.data || []).filter(x => !x.is_read).slice(0, 12));
      if (c.status === 'fulfilled') setCalendar(c.value.data || []);
      if (td.status === 'fulfilled') setTalent(td.value.data);
      if (va.status === 'fulfilled') setAttrition(va.value.data);
    } finally { setLoading(false); }
  };

  const matches = (emp) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return [emp.full_name, emp.role_title, emp.department].some(x => (x || '').toLowerCase().includes(s));
  };

  const visibleAlerts = alerts.filter(a => !dismissed.has(a.id));

  return (
    <div data-testid="hr-dashboard" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0 }}>HR Dashboard</h1>
          <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>
            {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })} · EAT
          </p>
        </div>
        <button data-testid="refresh-dashboard" onClick={loadData} style={{ padding: '8px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Refresh</button>
      </div>

      {/* Zone 1: Alerts banner */}
      {visibleAlerts.length === 0 ? (
        <div data-testid="alerts-all-clear" style={{ backgroundColor: '#F0FDF4', border: '1px solid #22C55E', padding: '10px 16px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: '#22C55E', fontWeight: 900 }}>✓</span>
          <span style={{ fontSize: '12px', color: '#14532D', fontWeight: 600 }}>All clear — no active alerts</span>
        </div>
      ) : (
        <div data-testid="alerts-banner" style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '8px', marginBottom: '20px' }}>
          {visibleAlerts.map(a => {
            const level = ALERT_PRIORITY(a);
            const c = ALERT_COLORS[level];
            return (
              <div key={a.id} data-testid={`alert-${a.id}`} style={{ minWidth: '280px', backgroundColor: c.bg, borderLeft: `4px solid ${c.border}`, padding: '10px 12px', position: 'relative' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                  <span style={{ fontSize: '9px', fontWeight: 700, color: c.border, letterSpacing: '0.18em' }}>{c.label}</span>
                  <button onClick={() => setDismissed(p => new Set(p).add(a.id))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: c.text, fontSize: '14px', padding: 0, lineHeight: 1 }}>×</button>
                </div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: c.text, marginTop: '4px' }}>{a.title}</div>
                <div style={{ fontSize: '11px', color: c.text, marginTop: '2px', opacity: 0.85 }}>{a.message}</div>
              </div>
            );
          })}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#525252' }}>Loading dashboard...</div>
      ) : (
        <>
          {/* Search */}
          <input
            data-testid="kanban-search"
            type="text"
            placeholder="Search employees..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: '100%', padding: '10px 14px', border: '1px solid rgba(25,25,25,0.12)', marginBottom: '12px', fontSize: '12px', fontFamily: 'Arial' }}
          />

          {/* Zones 2 + 3: Kanban (2/3) + Calendar (1/3) */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px', marginBottom: '20px', alignItems: 'start' }}>
            <div data-testid="kanban-board" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' }}>
              {COLUMNS.map(col => {
                const employees = (kanban[col.key] || []).filter(matches);
                return (
                  <div key={col.key} data-testid={`kanban-column-${col.key}`} style={{ backgroundColor: col.bg, border: '1px solid rgba(25,25,25,0.08)' }}>
                    <div style={{ padding: '10px 12px', borderBottom: `2px solid ${col.color}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '10px', fontWeight: 700, color: col.color, letterSpacing: '0.15em' }}>{col.label}</span>
                      <span style={{ backgroundColor: col.color, color: '#fff', borderRadius: '50%', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', fontWeight: 900 }}>{employees.length}</span>
                    </div>
                    <div style={{ padding: '8px', maxHeight: '500px', overflowY: 'auto' }}>
                      {employees.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '16px 0', fontSize: '10px', color: '#9CA3AF' }}>—</div>
                      ) : employees.map(emp => (
                        <KanbanCard key={emp.id} emp={emp} onClick={() => navigate(`/employees/${emp.id}`)} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Calendar widget + Talent gauge */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div data-testid="hr-calendar-widget" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
                <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#191919' }}>Next 14 days</span>
                  <button onClick={() => navigate('/calendar')} style={{ fontSize: '10px', color: '#FF353F', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}>View all</button>
                </div>
                <div style={{ padding: '8px 12px', maxHeight: '320px', overflowY: 'auto' }}>
                  {calendar.length === 0 ? (
                    <div style={{ fontSize: '11px', color: '#9CA3AF', padding: '8px 0' }}>No upcoming events</div>
                  ) : calendar.slice(0, 8).map((e, i) => (
                    <div key={e.id || i} data-testid={`calendar-event-${i}`} style={{ padding: '6px 0', borderBottom: i < 7 ? '1px solid rgba(25,25,25,0.05)' : 'none', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                      <span style={{ width: '6px', height: '6px', backgroundColor: EVENT_COLOR(e.event_type), borderRadius: '50%', marginTop: '6px', flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#191919' }}>{e.title || e.event_type}</div>
                        <div style={{ fontSize: '10px', color: '#525252' }}>{e.event_date && new Date(e.event_date).toLocaleDateString('en-GB')}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <TalentDensityGauge data={talent} />
            </div>
          </div>

          {/* Zone 4: Quick Stats Bar */}
          <div data-testid="quick-stats-bar" style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '8px' }}>
            <KPI_TILE testId="stat-active-employees" label="Active FTE" value={stats?.active} color="#22C55E" onClick={() => navigate('/employees')} />
            <KPI_TILE testId="stat-active-solvers"  label="Solvers" value={stats?.active_solvers} color="#8B5CF6" onClick={() => navigate('/solvers')} />
            <KPI_TILE testId="stat-onboarding"     label="Onboarding" value={stats?.onboarding} color="#3B82F6" onClick={() => navigate('/onboarding')} />
            <KPI_TILE testId="stat-attrition"      label="Attrition" value={attrition ? `${attrition.pct}%` : '—'} sub={`Target ≤${attrition?.target_pct ?? 10}%`} color={attrition && attrition.pct > 10 ? '#FF353F' : '#22C55E'} onClick={() => navigate('/retention')} />
            <KPI_TILE testId="stat-overdue-tasks"  label="Open Tasks" value={stats?.open_tasks} color={(stats?.open_tasks || 0) > 0 ? '#FF353F' : '#191919'} onClick={() => navigate('/my-tasks')} />
            <KPI_TILE testId="stat-talent-density" label="Talent Density" value={talent ? `${(talent.score_pct || 0).toFixed(0)}%` : '—'} sub={`Target ${talent?.target_pct ?? 85}%`} color={talent && talent.score_pct >= 85 ? '#22C55E' : '#FF353F'} onClick={() => navigate('/performance')} />
          </div>
        </>
      )}
    </div>
  );
}
