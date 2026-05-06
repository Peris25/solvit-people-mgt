import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtKES = (n) => n != null ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : '—';

export default function EmployeeProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');

  useEffect(() => {
    api.getEmployeeProfile(id)
      .then(r => setProfile(r.data))
      .catch(() => setProfile(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div style={{ padding: '48px', textAlign: 'center' }}>Loading profile...</div>;
  if (!profile) return <div style={{ padding: '48px', textAlign: 'center' }}>Employee not found</div>;

  const e = profile.employee;
  const initials = (e.full_name || '?').split(' ').map(s => s[0]).slice(0, 2).join('');

  const TABS = [
    { k: 'overview', l: 'Overview' },
    { k: 'timeline', l: `Timeline (${profile.timeline?.length || 0})` },
    { k: 'performance', l: `Performance (${profile.performance_history?.length || 0})` },
    { k: 'leave', l: `Leave (${profile.leave_history?.length || 0})` },
    { k: 'recognitions', l: `Recognitions (${profile.recognitions?.length || 0})` },
    { k: 'training', l: `Training (${profile.trainings?.length || 0})` },
    { k: 'idp', l: 'IDP' },
  ];

  return (
    <div data-testid="employee-profile-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      {/* Header card */}
      <div style={{ backgroundColor: '#191919', color: '#fff', padding: '28px', marginBottom: '20px' }}>
        <button data-testid="back-to-employees" onClick={() => navigate('/employees')} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '11px', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '14px', padding: 0 }}>← Back to Employees</button>
        <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
          <div style={{ width: '72px', height: '72px', borderRadius: '50%', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: '#fff', fontWeight: 900, fontSize: '24px' }}>{initials}</span>
          </div>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', margin: 0 }}>{e.full_name}</h1>
            <div style={{ fontSize: '13px', color: 'rgba(255,255,255,0.7)', marginTop: '4px' }}>{e.role_title} · {e.department} · {e.role_level}</div>
            <div style={{ display: 'flex', gap: '14px', marginTop: '14px', flexWrap: 'wrap', fontSize: '11px' }}>
              <Stat label="State" value={<StatusBadge status={e.lifecycle_state} small />} />
              <Stat label="Email" value={e.work_email} />
              <Stat label="Phone" value={e.phone_number || '—'} />
              <Stat label="Started" value={fmtDate(e.start_date)} />
              {['hr_admin', 'hr_manager', 'finance'].includes(user?.role) && <Stat label="Salary" value={fmtKES(e.current_salary_kes)} />}
              <Stat label="Manager" value={e.line_manager_id ? e.line_manager_id.substring(0, 8) : '—'} />
              <Stat label="Last Score" value={e.last_performance_score ?? '—'} />
              {e.flight_risk_level && <Stat label="Flight Risk" value={<span style={{ color: e.flight_risk_level === 'Critical' ? '#FF353F' : e.flight_risk_level === 'High' ? '#F97316' : e.flight_risk_level === 'Elevated' ? '#FCD34D' : '#22C55E', fontWeight: 900 }}>{e.flight_risk_level}</span>} />}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.k} data-testid={`profile-tab-${t.k}`} onClick={() => setTab(t.k)} style={{ padding: '10px 18px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '11px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {tab === 'overview' && <Overview profile={profile} user={user} />}
      {tab === 'timeline' && <Timeline events={profile.timeline} />}
      {tab === 'performance' && <PerformanceList items={profile.performance_history} />}
      {tab === 'leave' && <LeaveList items={profile.leave_history} />}
      {tab === 'recognitions' && <RecognitionsList items={profile.recognitions} />}
      {tab === 'training' && <TrainingList items={profile.trainings} />}
      {tab === 'idp' && <IDPView idp={profile.idp} />}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.15em', color: 'rgba(255,255,255,0.4)' }}>{label}</div>
      <div style={{ fontSize: '13px', fontWeight: 700, marginTop: '2px', color: '#fff' }}>{value}</div>
    </div>
  );
}

function Overview({ profile, user }) {
  const e = profile.employee;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
      <Card title="Personal & Statutory">
        <Row k="National ID" v={e.national_id_number || '—'} />
        <Row k="KRA PIN" v={e.kra_pin || '—'} />
        <Row k="NSSF" v={e.nssf_number || '—'} />
        <Row k="SHA" v={e.sha_number || '—'} />
        <Row k="DOB" v={fmtDate(e.date_of_birth)} />
        <Row k="Gender" v={e.gender || '—'} />
      </Card>
      <Card title="Employment">
        <Row k="Type" v={e.employment_type || 'Full Time'} />
        <Row k="Start Date" v={fmtDate(e.start_date)} />
        <Row k="Probation Ends" v={fmtDate(e.probation_end_date)} />
        <Row k="Lifecycle" v={<StatusBadge status={e.lifecycle_state} small />} />
        <Row k="Project Eligible" v={e.project_ownership_eligible ? 'Yes' : 'No'} />
      </Card>
      <Card title="Recent Performance">
        {profile.performance_history?.length ? (
          <div style={{ fontSize: '12px' }}>
            {profile.performance_history.slice(0, 3).map(r => (
              <div key={r.id} style={{ padding: '8px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                <strong>{r.cycle}</strong> — Score <strong style={{ color: r.score <= 1.5 ? '#22C55E' : r.score <= 2 ? '#F97316' : '#FF353F' }}>{r.score ?? '—'}</strong> · {r.placement?.replace('_', ' ') || '—'}
              </div>
            ))}
          </div>
        ) : <div style={{ fontSize: '12px', color: '#9CA3AF' }}>No reviews yet</div>}
      </Card>
      <Card title="Recognitions Received">
        {profile.recognitions?.length ? (
          <div style={{ fontSize: '12px' }}>
            {profile.recognitions.slice(0, 3).map(r => (
              <div key={r.id} style={{ padding: '8px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                <strong>{r.from || 'Anonymous'}</strong> — {(r.values || []).join(', ')}
                <div style={{ color: '#525252', marginTop: '2px' }}>{(r.behaviour || '').slice(0, 80)}</div>
              </div>
            ))}
          </div>
        ) : <div style={{ fontSize: '12px', color: '#9CA3AF' }}>No recognitions yet</div>}
      </Card>
    </div>
  );
}

function Card({ title, children }) {
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F9FAFB', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{title}</div>
      <div style={{ padding: '14px 16px' }}>{children}</div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(25,25,25,0.04)', fontSize: '12px' }}>
      <span style={{ color: '#525252' }}>{k}</span>
      <span style={{ fontWeight: 700, color: '#191919' }}>{v}</span>
    </div>
  );
}

function Timeline({ events }) {
  if (!events?.length) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No timeline events</div>;
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      {events.map((ev, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '120px 16px 1fr', gap: '14px', padding: '12px 18px', borderBottom: i < events.length - 1 ? '1px solid rgba(25,25,25,0.05)' : 'none', alignItems: 'flex-start' }}>
          <div style={{ fontSize: '11px', color: '#525252', fontWeight: 700, paddingTop: '2px' }}>{fmtDate(ev.date)}</div>
          <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: ev.color || '#9CA3AF', marginTop: '4px' }} />
          <div style={{ fontSize: '13px', color: '#191919' }}>
            <strong style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '10px', color: ev.color || '#525252' }}>{ev.type}</strong>
            <div>{ev.title}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PerformanceList({ items }) {
  if (!items?.length) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No performance reviews yet</div>;
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead><tr style={{ backgroundColor: '#F5F5F5' }}>{['Cycle', 'Score', 'Rating', 'Placement', 'Status'].map(h => <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>{h}</th>)}</tr></thead>
        <tbody>{items.map((r, i) => (
          <tr key={r.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
            <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.cycle}</td>
            <td style={{ padding: '10px 14px', fontWeight: 900, color: r.score <= 1.5 ? '#22C55E' : r.score <= 2 ? '#F97316' : '#FF353F' }}>{r.score ?? '—'}</td>
            <td style={{ padding: '10px 14px' }}>{r.rating && <StatusBadge status={r.rating} small />}</td>
            <td style={{ padding: '10px 14px', color: '#525252' }}>{r.placement?.replace('_', ' ') || '—'}</td>
            <td style={{ padding: '10px 14px' }}><StatusBadge status={r.status} small /></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function LeaveList({ items }) {
  if (!items?.length) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No leave records</div>;
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead><tr style={{ backgroundColor: '#F5F5F5' }}>{['Type', 'Start', 'End', 'Days', 'Status'].map(h => <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>{h}</th>)}</tr></thead>
        <tbody>{items.map((l, i) => (
          <tr key={l.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
            <td style={{ padding: '10px 14px', fontWeight: 700 }}>{l.type}</td>
            <td style={{ padding: '10px 14px', color: '#525252' }}>{fmtDate(l.start)}</td>
            <td style={{ padding: '10px 14px', color: '#525252' }}>{fmtDate(l.end)}</td>
            <td style={{ padding: '10px 14px', fontWeight: 700 }}>{l.days}</td>
            <td style={{ padding: '10px 14px' }}><StatusBadge status={l.status?.replace('Pending_', '').replace('_', ' ')} small /></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function RecognitionsList({ items }) {
  if (!items?.length) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No recognitions yet</div>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
      {items.map(r => (
        <div key={r.id} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px' }}>
          <div style={{ fontSize: '11px', color: '#FF353F', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>{r.type}</div>
          <div style={{ fontSize: '13px', fontWeight: 900, color: '#191919', marginTop: '4px' }}>From {r.from || 'Anonymous'}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '8px' }}>
            {(r.values || []).map(v => <span key={v} style={{ fontSize: '10px', backgroundColor: '#FFEDD5', color: '#9A3412', padding: '2px 8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{v}</span>)}
          </div>
          <p style={{ fontSize: '12px', color: '#191919', lineHeight: 1.5, margin: '10px 0 0' }}>{r.behaviour}</p>
        </div>
      ))}
    </div>
  );
}

function TrainingList({ items }) {
  if (!items?.length) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No training history</div>;
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead><tr style={{ backgroundColor: '#F5F5F5' }}>{['Training', 'Provider', 'Cost', 'Status'].map(h => <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>{h}</th>)}</tr></thead>
        <tbody>{items.map((t, i) => (
          <tr key={t.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
            <td style={{ padding: '10px 14px', fontWeight: 700 }}>{t.name}</td>
            <td style={{ padding: '10px 14px', color: '#525252' }}>{t.provider}</td>
            <td style={{ padding: '10px 14px', fontWeight: 700 }}>{fmtKES(t.cost_kes)}</td>
            <td style={{ padding: '10px 14px' }}><StatusBadge status={t.status?.replace('Pending_', '').replace('_', ' ')} small /></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function IDPView({ idp }) {
  if (!idp) return <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No IDP on file</div>;
  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
      <pre style={{ fontSize: '12px', color: '#191919', whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{JSON.stringify(idp, null, 2)}</pre>
    </div>
  );
}
