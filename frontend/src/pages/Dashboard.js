import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';

const KPI = ({ label, value, sub, color = '#191919' }) => (
  <div data-testid={`kpi-${label.toLowerCase().replace(/ /g,'-')}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px 24px' }}>
    <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252', marginBottom: '8px' }}>{label}</div>
    <div style={{ fontSize: '36px', fontWeight: 900, letterSpacing: '-0.05em', color }}>{value ?? '—'}</div>
    {sub && <div style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>{sub}</div>}
  </div>
);

const KanbanCard = ({ emp, onTransition }) => {
  const tenureStr = emp.start_date ? (() => {
    const days = Math.floor((Date.now() - new Date(emp.start_date)) / 86400000);
    return days > 365 ? `${Math.floor(days/365)}y ${Math.floor((days%365)/30)}m` : `${Math.floor(days/30)}m`;
  })() : null;

  return (
    <div data-testid={`kanban-card-${emp.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '12px 14px', marginBottom: '8px', cursor: 'pointer', transition: 'border-color 0.15s' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = '#FF353F'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(25,25,25,0.08)'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
        <div style={{ fontWeight: 700, fontSize: '13px', color: '#191919', letterSpacing: '-0.02em' }}>{emp.full_name}</div>
        <StatusBadge status={emp.lifecycle_state} small />
      </div>
      <div style={{ fontSize: '11px', color: '#525252', marginBottom: '4px' }}>{emp.role_title}</div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
        <span style={{ fontSize: '10px', color: '#525252', backgroundColor: '#F5F5F5', padding: '1px 6px' }}>{emp.department}</span>
        {emp.role_level && <span style={{ fontSize: '10px', color: '#525252', backgroundColor: '#F5F5F5', padding: '1px 6px' }}>{emp.role_level}</span>}
        {tenureStr && <span style={{ fontSize: '10px', color: '#525252' }}>📅 {tenureStr}</span>}
      </div>
      {emp.flight_risk_level && emp.flight_risk_level !== 'Low' && (
        <div style={{ marginTop: '6px' }}>
          <StatusBadge status={emp.flight_risk_level} small />
        </div>
      )}
      {emp.last_performance_score && (
        <div style={{ marginTop: '6px', fontSize: '10px', color: '#525252' }}>
          Perf: <strong>{emp.last_performance_score}</strong>
        </div>
      )}
    </div>
  );
};

const COLUMNS = [
  { key: 'Onboarding', label: 'Onboarding', color: '#3B82F6', bg: '#EFF6FF' },
  { key: 'Active', label: 'Active', color: '#22C55E', bg: '#F0FDF4' },
  { key: 'Exiting', label: 'Exiting', color: '#F97316', bg: '#FFF7ED' },
  { key: 'Exited', label: 'Exited', color: '#6B7280', bg: '#F9FAFB' },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [kanban, setKanban] = useState({ Onboarding: [], Active: [], Exiting: [], Exited: [] });
  const [stats, setStats] = useState(null);
  const [viewMode, setViewMode] = useState('kanban');
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allEmployees, setAllEmployees] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [kanbanRes, statsRes, notifsRes] = await Promise.allSettled([
        api.getKanban(),
        api.getEmployeeStats(),
        api.getNotifications()
      ]);
      if (kanbanRes.status === 'fulfilled') setKanban(kanbanRes.value.data);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (notifsRes.status === 'fulfilled') setNotifications(notifsRes.value.data.filter(n => !n.is_read).slice(0, 5));
      // All employees for list view
      const allRes = await api.getEmployees();
      setAllEmployees(allRes.data);
    } finally {
      setLoading(false);
    }
  };

  const totalEmployees = Object.values(kanban).reduce((sum, col) => sum + col.length, 0);

  return (
    <div data-testid="hr-dashboard" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0, marginBottom: '4px' }}>HR Dashboard</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0 }}>
            {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })} · EAT
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button data-testid="view-kanban" onClick={() => setViewMode('kanban')} style={{ padding: '8px 16px', backgroundColor: viewMode === 'kanban' ? '#191919' : 'transparent', color: viewMode === 'kanban' ? '#fff' : '#191919', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial', transition: 'all 0.2s' }}>Kanban</button>
          <button data-testid="view-list" onClick={() => setViewMode('list')} style={{ padding: '8px 16px', backgroundColor: viewMode === 'list' ? '#191919' : 'transparent', color: viewMode === 'list' ? '#fff' : '#191919', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial', transition: 'all 0.2s' }}>List</button>
          <button data-testid="refresh-dashboard" onClick={loadData} style={{ padding: '8px 12px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial' }}>Refresh</button>
        </div>
      </div>

      {/* KPI Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px', marginBottom: '24px' }}>
        <KPI label="Total FTE" value={stats?.total_fte ?? totalEmployees} />
        <KPI label="Active" value={stats?.active} color="#22C55E" />
        <KPI label="Onboarding" value={stats?.onboarding} color="#3B82F6" />
        <KPI label="Exiting" value={stats?.exiting} color="#F97316" />
        <KPI label="Active Solvers" value={stats?.active_solvers} color="#8B5CF6" />
        <KPI label="Open Tasks" value={stats?.open_tasks} color="#FF353F" />
      </div>

      {/* Notifications Banner */}
      {notifications.length > 0 && (
        <div style={{ backgroundColor: '#FFF7ED', border: '1px solid #F97316', padding: '12px 16px', marginBottom: '20px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#9A3412', marginBottom: '8px' }}>Automation Alerts ({notifications.length})</div>
          {notifications.map(n => (
            <div key={n.id} style={{ fontSize: '12px', color: '#7C2D12', marginBottom: '4px', display: 'flex', gap: '8px' }}>
              <span>⚠</span>
              <span>{n.title}: {n.message}</span>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#525252', fontSize: '13px' }}>Loading dashboard...</div>
      ) : viewMode === 'kanban' ? (
        /* Kanban View */
        <div data-testid="kanban-board" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', alignItems: 'start' }}>
          {COLUMNS.map(col => {
            const employees = kanban[col.key] || [];
            return (
              <div key={col.key} data-testid={`kanban-column-${col.key}`} style={{ backgroundColor: col.bg, border: `1px solid rgba(25,25,25,0.08)` }}>
                <div style={{ padding: '12px 14px', borderBottom: `2px solid ${col.color}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: col.color }}>{col.label}</span>
                  </div>
                  <span style={{ backgroundColor: col.color, color: '#fff', borderRadius: '50%', width: '22px', height: '22px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', fontWeight: 900 }}>{employees.length}</span>
                </div>
                <div style={{ padding: '12px', maxHeight: '600px', overflowY: 'auto' }}>
                  {employees.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px 0', fontSize: '11px', color: '#9CA3AF' }}>No employees</div>
                  ) : (
                    employees.map(emp => <KanbanCard key={emp.id} emp={emp} />)
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* List View */
        <div data-testid="employee-list" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', fontWeight: 700, color: '#191919' }}>All Employees — {allEmployees.length} records</span>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Name', 'Role', 'Department', 'Level', 'Start Date', 'State', 'Risk', 'Perf Score'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allEmployees.map((emp, i) => (
                <tr key={emp.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: '#191919' }}>{emp.full_name}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.role_title}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.department}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.role_level}</td>
                  <td style={{ padding: '10px 16px', color: '#525252' }}>{emp.start_date ? new Date(emp.start_date).toLocaleDateString('en-GB') : '—'}</td>
                  <td style={{ padding: '10px 16px' }}><StatusBadge status={emp.lifecycle_state} small /></td>
                  <td style={{ padding: '10px 16px' }}>{emp.flight_risk_level ? <StatusBadge status={emp.flight_risk_level} small /> : <span style={{ color: '#9CA3AF' }}>—</span>}</td>
                  <td style={{ padding: '10px 16px', fontWeight: 700, color: '#191919' }}>{emp.last_performance_score ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
