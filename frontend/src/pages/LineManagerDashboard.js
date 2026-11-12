/**
 * LineManagerDashboard — scoped to "my own data + my direct reports".
 *
 * Replaces the generic HR Admin operational dashboard for `line_manager` users
 * per the Additive Role Architecture rule: a Line Manager only ever sees their
 * own record and the records of people they manage.
 *
 * Sections:
 *  - Top brief: team size · pending leave · open reviews · my open tasks
 *  - Flight risk bar (Critical / High / Elevated / Healthy split for the team)
 *  - Direct Reports table with per-person signals
 *  - Pending Leave list (one-click → Leave page Team tab)
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
import { Users as UsersIcon, Palmtree, AlertTriangle, ClipboardList, ListChecks } from 'lucide-react';
import { DashboardAttention, DashboardMetric } from '../components/DashboardOverview';
import WorkspaceSkeleton from '../components/WorkspaceSkeleton';

const RISK_COLOR = { Critical: '#FF353F', High: '#F97316', Elevated: '#EAB308', Healthy: '#22C55E' };

const Tile = ({ label, value, sub, Icon, onClick, testId }) => (
  <DashboardMetric label={label} value={value} sub={sub} Icon={Icon} onClick={onClick} testId={testId} />
);

export default function LineManagerDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.getLineManagerWidget();
        if (!Array.isArray(r.data?.team)) throw new Error('Team information is unavailable');
        if (!cancelled) setData(r.data);
      } catch (e) {
        if (!cancelled) setErr(e.response?.data?.detail || 'Failed to load team data');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div data-testid="lm-dashboard-loading"><WorkspaceSkeleton label="Loading your team..." /></div>;
  if (err) return <div data-testid="lm-dashboard-err" style={{ padding: '24px', backgroundColor: '#FEE2E2', color: '#7F1D1D', border: '1px solid #FF353F' }}>{err}</div>;

  const team = data?.team || [];
  const risk = data?.flight_risk_summary || { Critical: 0, High: 0, Elevated: 0, Healthy: 0 };
  const total = team.length || 1;

  return (
    <div data-testid="line-manager-dashboard" className="dashboard-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <h1 style={{ fontSize: '30px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0, fontFamily: 'Barlow' }}>
          My Team · Line Manager
        </h1>
        <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>
          {user?.full_name} · {data?.team_size || 0} direct {data?.team_size === 1 ? 'report' : 'reports'}
        </p>
      </div>

      {/* Top brief */}
      <div className="dashboard-summary-grid" data-testid="lm-brief">
        <Tile testId="lm-tile-team" label="Direct Reports" value={data?.team_size || 0} Icon={UsersIcon} />
        <Tile
          testId="lm-tile-leave"
          label="Pending Leave"
          value={data?.pending_leave || 0}
          sub={data?.pending_leave ? 'Awaiting your decision' : 'Nothing waiting'}
          color={data?.pending_leave ? '#FF353F' : '#22C55E'}
          Icon={Palmtree}
          onClick={() => navigate('/leave?view=team')}
        />
        <Tile
          testId="lm-tile-reviews"
          label="Open Reviews"
          value={data?.open_reviews || 0}
          sub="In progress for your team"
          color={data?.open_reviews ? '#F97316' : '#191919'}
          Icon={ClipboardList}
          onClick={() => navigate('/performance')}
        />
        <Tile
          testId="lm-tile-mytasks"
          label="My Open Tasks"
          value={data?.my_open_tasks || 0}
          color={data?.my_open_tasks ? '#3B82F6' : '#191919'}
          Icon={ListChecks}
          onClick={() => navigate('/my-tasks')}
        />
      </div>

      <DashboardAttention description="Approvals and work waiting for your team." items={[
        { key: 'leave', label: 'Leave requests awaiting your decision', count: data?.pending_leave, detail: 'Open Team Leave to review the requests', Icon: Palmtree, onClick: () => navigate('/leave?view=team') },
        { key: 'reviews', label: 'Team reviews in progress', count: data?.open_reviews, detail: 'Check your team’s current performance reviews', Icon: ClipboardList, onClick: () => navigate('/performance') },
        { key: 'tasks', label: 'Your open tasks', count: data?.my_open_tasks, detail: 'Review your assigned tasks and deadlines', Icon: ListChecks, onClick: () => navigate('/my-tasks') },
      ]} />
      {/* Flight risk bar */}
      <div data-testid="lm-flight-risk" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
          <AlertTriangle size={14} color={risk.Critical || risk.High ? '#FF353F' : '#525252'} />
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', fontFamily: 'Barlow' }}>
            Team Flight Risk
          </span>
        </div>
        <div style={{ display: 'flex', height: '8px', overflow: 'hidden', backgroundColor: '#F5F5F5' }}>
          {['Critical', 'High', 'Elevated', 'Healthy'].map(k => (
            <div key={k} data-testid={`lm-risk-bar-${k.toLowerCase()}`} title={`${k}: ${risk[k] || 0}`}
              style={{ width: `${((risk[k] || 0) / total) * 100}%`, backgroundColor: RISK_COLOR[k] }} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: '14px', marginTop: '10px', fontSize: '11px', flexWrap: 'wrap' }}>
          {['Critical', 'High', 'Elevated', 'Healthy'].map(k => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '8px', height: '8px', backgroundColor: RISK_COLOR[k] }} />
              <strong>{k}</strong> · {risk[k] || 0}
            </div>
          ))}
        </div>
      </div>

      {/* Direct reports table */}
      <div data-testid="lm-direct-reports" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', fontFamily: 'Barlow' }}>
            My Direct Reports
          </span>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr style={{ backgroundColor: '#FAFAFA' }}>
              {['Name', 'Role', 'State', 'Risk', 'Pending Leave', 'Open Reviews', 'Last Review', 'Score'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Barlow' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {team.map((t, i) => (
              <tr key={t.id} data-testid={`lm-report-${t.id}`}
                onClick={() => navigate(`/employees/${t.id}`)}
                style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = '#FEF2F2'}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = i % 2 === 0 ? '#fff' : '#FAFAFA'}>
                <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{t.full_name}</td>
                <td style={{ padding: '10px 14px', color: '#525252' }}>{t.role_title}</td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{ fontSize: '10px', padding: '2px 8px', backgroundColor: '#F5F5F5', color: '#525252', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>{t.lifecycle_state}</span>
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{ fontSize: '10px', padding: '2px 8px', backgroundColor: RISK_COLOR[t.flight_risk_level] || '#F5F5F5', color: '#fff', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {t.flight_risk_level}
                  </span>
                </td>
                <td style={{ padding: '10px 14px', fontWeight: t.pending_leave ? 700 : 400, color: t.pending_leave ? '#FF353F' : '#525252' }}>
                  {t.pending_leave || '—'}
                </td>
                <td style={{ padding: '10px 14px', color: t.open_reviews ? '#F97316' : '#525252', fontWeight: t.open_reviews ? 700 : 400 }}>
                  {t.open_reviews || '—'}
                </td>
                <td style={{ padding: '10px 14px', color: '#525252' }}>
                  {t.days_since_last_review == null ? '—' : `${t.days_since_last_review}d ago`}
                </td>
                <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{t.last_performance_score ?? '—'}</td>
              </tr>
            ))}
            {team.length === 0 && (
              <tr><td colSpan={8} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF', fontSize: '12px' }}>
                You have no direct reports yet. Ask HR to assign team members.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
