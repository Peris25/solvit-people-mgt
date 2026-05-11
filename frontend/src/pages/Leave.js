import React, { useState, useEffect, useCallback } from 'react';
import StatusBadge from '../components/StatusBadge';
import EmployeePicker from '../components/EmployeePicker';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Calendar as CalendarIcon, ClipboardList, Users as UsersIcon, RotateCcw, Plus } from 'lucide-react';

const LEAVE_TYPE_LABELS = {
  Annual: 'Annual leave',
  Sick: 'Sick leave',
  Maternity: 'Maternity leave',
  Paternity: 'Paternity leave',
  Compassionate: 'Compassionate leave',
  Unpaid: 'Unpaid leave',
};

const LEAVE_TYPE_COLOR = {
  Annual: '#FF353F', Sick: '#F97316', Maternity: '#8B5CF6',
  Paternity: '#3B82F6', Compassionate: '#525252', Unpaid: '#9CA3AF',
};

const fmtPeriod = (s, e) => {
  try {
    const a = new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    const b = new Date(e).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    return `${a} → ${b}`;
  } catch { return `${s} → ${e}`; }
};

export default function Leave() {
  const { user } = useAuth();
  const myEmpId = user?.employee_id || user?.id;
  const isLM = user?.role === 'line_manager';
  const isHR = ['hr_admin', 'hr_manager'].includes(user?.role);
  const canDecide = isLM || isHR;

  const [tab, setTab] = useState('my');
  const [requests, setRequests] = useState([]);
  const [balances, setBalances] = useState(null);
  const [rollover, setRollover] = useState(null);
  const [types, setTypes] = useState({});
  const [calendar, setCalendar] = useState(null);
  const [calYear, setCalYear] = useState(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    leave_type: 'Annual', start_date: '', end_date: '',
    handover_contact: '', handover_contact_id: '',
    line_manager_id: '', notes: ''
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, t] = await Promise.all([api.getLeaveRequests(), api.getLeaveTypes()]);
      setRequests(r.data || []);
      setTypes(t.data || {});
      if (myEmpId) {
        try {
          const b = await api.getLeaveBalances(myEmpId);
          setBalances(b.data);
        } catch { /* no balances */ }
        try {
          const ro = await api.getLeaveRollover(myEmpId);
          setRollover(ro.data);
        } catch { /* no rollover */ }
      }
    } finally { setLoading(false); }
  }, [myEmpId]);

  useEffect(() => { load(); }, [load]);

  const loadCalendar = useCallback(async () => {
    try {
      const c = await api.getLeaveCalendar(calYear, calMonth);
      setCalendar(c.data);
    } catch { setCalendar(null); }
  }, [calYear, calMonth]);

  useEffect(() => { if (tab === 'calendar') loadCalendar(); }, [tab, loadCalendar]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.line_manager_id) {
      alert('Please select your Line Manager for approval routing.');
      return;
    }
    setSaving(true);
    try {
      await api.createLeaveRequest({ ...form, employee_id: myEmpId });
      setShowForm(false);
      setForm({ leave_type: 'Annual', start_date: '', end_date: '', handover_contact: '', handover_contact_id: '', line_manager_id: '', notes: '' });
      load();
    } finally { setSaving(false); }
  };

  const decide = async (id, decision) => {
    await api.leaveDecision(id, { decision });
    load();
  };

  const calcDays = () => {
    if (!form.start_date || !form.end_date) return 0;
    let d = 0;
    const cur = new Date(form.start_date);
    const end = new Date(form.end_date);
    while (cur <= end) {
      if (cur.getDay() !== 0 && cur.getDay() !== 6) d++;
      cur.setDate(cur.getDate() + 1);
    }
    return d;
  };

  // Filtered request lists
  const myRequests = requests.filter(r => r.employee_id === myEmpId);
  const teamRequests = requests.filter(r => r.employee_id !== myEmpId);

  const annualBal = balances?.Annual;
  const accruedDisplay = annualBal?.accrued_kenyan_act ?? balances?.accrued_annual ?? 0;

  const TabButton = ({ id, label, Icon }) => (
    <button
      data-testid={`leave-tab-${id}`}
      onClick={() => setTab(id)}
      style={{
        padding: '10px 18px', backgroundColor: 'transparent', border: 'none',
        borderBottom: tab === id ? '2px solid #FF353F' : '2px solid transparent',
        marginBottom: '-2px', cursor: 'pointer', fontSize: '12px',
        fontWeight: tab === id ? 700 : 500, color: tab === id ? '#FF353F' : '#525252',
        fontFamily: 'Barlow, sans-serif', textTransform: 'uppercase', letterSpacing: '0.1em',
        display: 'inline-flex', alignItems: 'center', gap: '8px'
      }}>
      <Icon size={14} />{label}
    </button>
  );

  return (
    <div data-testid="leave-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0, fontFamily: 'Barlow' }}>Leave Management</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Kenyan Employment Act 2007 — accruals 1.75 days/month · Annual cap 21 days</p>
        </div>
        <button data-testid="apply-leave-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          <Plus size={14} /> Apply for Leave
        </button>
      </div>

      {/* Rollover banner */}
      {rollover && rollover.carried_forward > 0 && (
        <div data-testid="rollover-banner" style={{ padding: '12px 16px', backgroundColor: rollover.deadline_passed ? '#FEE2E2' : '#FEF3C7', borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: rollover.deadline_passed ? '#FF353F' : '#F59E0B', marginBottom: '20px', fontSize: '12px', color: '#191919' }}>
          <strong style={{ color: '#FF353F' }}>Rollover Leave:</strong> {rollover.remaining} of {rollover.carried_forward} carried-forward days remaining. {rollover.banner}
        </div>
      )}

      {/* Balances */}
      {balances && (
        <div data-testid="leave-balances" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {/* Accrued balance card */}
          {annualBal && (
            <div data-testid="balance-accrued" style={{ backgroundColor: '#191919', color: '#fff', padding: '14px 18px' }}>
              <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'rgba(255,255,255,0.6)', marginBottom: '6px' }}>Accrued Balance</div>
              <div style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', fontFamily: 'Barlow' }}>{accruedDisplay}</div>
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>Earned so far · {annualBal.completed_months_in_year || 0} months @ 1.75/mo</div>
            </div>
          )}
          {Object.entries(balances).filter(([k]) => !['annual_days_remaining','sick_days_remaining','accrued_annual'].includes(k)).map(([type, b]) => (
            <div key={type} data-testid={`balance-${type}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px' }}>{type}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '26px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', fontFamily: 'Barlow' }}>{b.remaining}</span>
                <span style={{ fontSize: '11px', color: '#525252' }}>of {b.entitlement}</span>
              </div>
              <div style={{ height: '4px', backgroundColor: '#F5F5F5', marginTop: '8px' }}>
                <div style={{ width: `${Math.min(100, (b.used / Math.max(1, b.entitlement)) * 100)}%`, height: '100%', backgroundColor: LEAVE_TYPE_COLOR[type] || '#FF353F' }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        <TabButton id="my" label="My Applications" Icon={ClipboardList} />
        {(canDecide || isHR) && <TabButton id="team" label="Team Leave" Icon={UsersIcon} />}
        <TabButton id="calendar" label="Calendar" Icon={CalendarIcon} />
        <TabButton id="rollover" label="Rollover" Icon={RotateCcw} />
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
        <>
          {tab === 'my' && <RequestsTable rows={myRequests} canDecide={false} decide={decide} testId="my-applications" />}
          {tab === 'team' && (canDecide || isHR) && <RequestsTable rows={teamRequests} canDecide={canDecide} decide={decide} testId="team-leave" />}
          {tab === 'calendar' && <LeaveCalendar calendar={calendar} year={calYear} month={calMonth} setYear={setCalYear} setMonth={setCalMonth} />}
          {tab === 'rollover' && <RolloverPanel rollover={rollover} />}
        </>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900, fontFamily: 'Barlow' }}>Apply for Leave</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={submit} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Leave Type</label>
                  <select required value={form.leave_type} onChange={e => setForm(p => ({ ...p, leave_type: e.target.value }))} style={inp}>
                    {Object.keys(types).map(t => <option key={t} value={t}>{LEAVE_TYPE_LABELS[t] || `${t} leave`}</option>)}
                  </select>
                  {types[form.leave_type]?.description && (
                    <div style={{ fontSize: '10px', color: '#525252', marginTop: '4px', fontStyle: 'italic' }}>{types[form.leave_type].description}</div>
                  )}
                </div>
                <div>
                  <label style={lbl}>Start Date</label>
                  <input type="date" required value={form.start_date} onChange={e => setForm(p => ({ ...p, start_date: e.target.value }))} style={inp} />
                </div>
                <div>
                  <label style={lbl}>End Date</label>
                  <input type="date" required value={form.end_date} onChange={e => setForm(p => ({ ...p, end_date: e.target.value }))} style={inp} />
                </div>
                <div style={{ gridColumn: '1 / -1', backgroundColor: '#F5F5F5', padding: '8px 12px', fontSize: '12px' }}>
                  Working Days: <strong>{calcDays()}</strong>
                  {annualBal && form.leave_type === 'Annual' && (
                    <span style={{ marginLeft: '12px', color: calcDays() > accruedDisplay ? '#FF353F' : '#525252' }}>
                      · Accrued available: {accruedDisplay} days
                    </span>
                  )}
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Line Manager (required for approval)</label>
                  <EmployeePicker
                    testId="leave-lm-picker"
                    value={form.line_manager_id}
                    excludeId={myEmpId}
                    placeholder="Select your line manager..."
                    onChange={(emp) => setForm(p => ({ ...p, line_manager_id: emp.id }))}
                  />
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Handover Contact</label>
                  <EmployeePicker
                    testId="leave-handover-picker"
                    value={form.handover_contact_id}
                    excludeId={myEmpId}
                    placeholder="Select colleague covering for you..."
                    onChange={(emp) => setForm(p => ({ ...p, handover_contact: emp.full_name, handover_contact_id: emp.id }))}
                  />
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Handover Notes</label>
                  <textarea rows={3} value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} style={{ ...inp, resize: 'vertical' }} />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={btnGhost}>Cancel</button>
                <button data-testid="leave-submit-btn" type="submit" disabled={saving} style={btnRed}>{saving ? 'Submitting…' : 'Submit Request'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', fontFamily: 'Nunito Sans, sans-serif' };
const btnRed = { padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' };
const btnGhost = { padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Nunito Sans, sans-serif' };

function RequestsTable({ rows, canDecide, decide, testId }) {
  return (
    <div data-testid={testId} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr style={{ backgroundColor: '#F5F5F5' }}>
            {['Employee', 'Type', 'Period', 'Days', 'Handover', 'Status', 'Action'].map(h => (
              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Barlow' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} data-testid={`leave-${r.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
              <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '11px' }}>{(r.employee_id || '').substring(0, 8)}</td>
              <td style={{ padding: '10px 14px', fontWeight: 700 }}>{LEAVE_TYPE_LABELS[r.leave_type] || r.leave_type}</td>
              <td style={{ padding: '10px 14px', color: '#525252' }}>{fmtPeriod(r.start_date, r.end_date)}</td>
              <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.working_days}</td>
              <td style={{ padding: '10px 14px', color: '#525252' }}>{r.handover_contact || '—'}</td>
              <td style={{ padding: '10px 14px' }}><StatusBadge status={(r.status || '').replace('Pending_', '').replace('_', ' ')} small /></td>
              <td style={{ padding: '10px 14px' }}>
                {canDecide && r.status === 'Pending_Manager' && (
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button data-testid={`leave-approve-${r.id}`} onClick={() => decide(r.id, 'Approve')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', color: '#22C55E', background: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Approve</button>
                    <button data-testid={`leave-reject-${r.id}`} onClick={() => decide(r.id, 'Reject')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Reject</button>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No requests</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function LeaveCalendar({ calendar, year, month, setYear, setMonth }) {
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayWeek = new Date(year, month - 1, 1).getDay(); // 0=Sun
  // Map: day -> events
  const dayMap = {};
  (calendar?.events || []).forEach(ev => {
    const start = new Date(ev.start_date);
    const end = new Date(ev.end_date);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      if (d.getFullYear() === year && d.getMonth() + 1 === month) {
        const day = d.getDate();
        if (!dayMap[day]) dayMap[day] = [];
        dayMap[day].push(ev);
      }
    }
  });

  const monthName = new Date(year, month - 1, 1).toLocaleString('en-GB', { month: 'long' });

  const prev = () => { if (month === 1) { setYear(year - 1); setMonth(12); } else setMonth(month - 1); };
  const next = () => { if (month === 12) { setYear(year + 1); setMonth(1); } else setMonth(month + 1); };

  return (
    <div data-testid="leave-calendar" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <button data-testid="cal-prev" onClick={prev} style={navBtn}>‹ Prev</button>
        <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>{monthName} {year}</h3>
        <button data-testid="cal-next" onClick={next} style={navBtn}>Next ›</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px', fontSize: '11px' }}>
        {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d => (
          <div key={d} style={{ padding: '6px', textAlign: 'center', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{d}</div>
        ))}
        {Array.from({ length: firstDayWeek }).map((_, i) => <div key={`empty-${i}`} />)}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1;
          const events = dayMap[day] || [];
          return (
            <div key={day} data-testid={`cal-day-${day}`} style={{ minHeight: '70px', border: '1px solid rgba(25,25,25,0.06)', padding: '4px', backgroundColor: events.length ? '#FFF5F5' : '#fff' }}>
              <div style={{ fontWeight: 700, fontSize: '11px', color: '#191919' }}>{day}</div>
              {events.slice(0, 2).map(ev => (
                <div key={ev.id} title={`${ev.employee_name} · ${ev.leave_type}`} style={{ marginTop: '2px', padding: '1px 4px', fontSize: '9px', backgroundColor: LEAVE_TYPE_COLOR[ev.leave_type] || '#FF353F', color: '#fff', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                  {ev.employee_name?.split(' ')[0] || '·'}
                </div>
              ))}
              {events.length > 2 && <div style={{ fontSize: '9px', color: '#525252', marginTop: '2px' }}>+{events.length - 2} more</div>}
            </div>
          );
        })}
      </div>
      {(!calendar || (calendar.events || []).length === 0) && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF', fontSize: '12px', marginTop: '12px' }}>No approved leave in this month.</div>
      )}
    </div>
  );
}

const navBtn = { padding: '6px 12px', border: '1px solid rgba(25,25,25,0.15)', backgroundColor: '#fff', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };

function RolloverPanel({ rollover }) {
  if (!rollover) return <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No rollover data</div>;
  const cf = rollover.carried_forward || 0;
  return (
    <div data-testid="rollover-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
      <h3 style={{ margin: '0 0 16px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>Rollover Leave · {rollover.year || new Date().getFullYear()}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '20px' }}>
        <div style={statBox}>
          <div style={statLabel}>Carried Forward</div>
          <div style={statValue}>{cf}</div>
        </div>
        <div style={statBox}>
          <div style={statLabel}>Used</div>
          <div style={statValue}>{rollover.used || 0}</div>
        </div>
        <div style={statBox}>
          <div style={statLabel}>Remaining</div>
          <div style={{ ...statValue, color: rollover.deadline_passed ? '#FF353F' : '#191919' }}>{rollover.remaining || 0}</div>
        </div>
      </div>
      {rollover.banner && (
        <div style={{ padding: '12px 16px', backgroundColor: rollover.deadline_passed ? '#FEE2E2' : '#FEF3C7', borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: rollover.deadline_passed ? '#FF353F' : '#F59E0B', fontSize: '12px', color: '#191919' }}>
          {rollover.banner} {rollover.deadline_passed && <strong style={{ color: '#FF353F' }}>· Deadline passed — remaining days forfeited.</strong>}
        </div>
      )}
      {cf === 0 && <div style={{ padding: '20px', textAlign: 'center', color: '#525252', fontSize: '12px' }}>No carry-forward days from previous year.</div>}
    </div>
  );
}

const statBox = { padding: '16px', backgroundColor: '#F5F5F5', borderLeftWidth: '3px', borderLeftStyle: 'solid', borderLeftColor: '#FF353F' };
const statLabel = { fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', fontFamily: 'Barlow' };
const statValue = { fontSize: '32px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.04em', color: '#191919', marginTop: '4px' };
