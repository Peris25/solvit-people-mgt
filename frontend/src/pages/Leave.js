import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Leave() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [balances, setBalances] = useState(null);
  const [types, setTypes] = useState({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: user?.employee_id || user?.id || '', leave_type: 'Annual', start_date: '', end_date: '', handover_contact: '', notes: '' });
  const [saving, setSaving] = useState(false);

  const myEmpId = user?.employee_id || user?.id;
  const canDecide = ['line_manager', 'hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [r, t] = await Promise.all([api.getLeaveRequests(), api.getLeaveTypes()]);
      setRequests(r.data);
      setTypes(t.data);
      if (myEmpId) {
        try {
          const b = await api.getLeaveBalances(myEmpId);
          setBalances(b.data);
        } catch { /* no balances yet */ }
      }
    } finally { setLoading(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createLeaveRequest({ ...form, employee_id: form.employee_id || myEmpId });
      setShowForm(false);
      setForm({ ...form, start_date: '', end_date: '', handover_contact: '', notes: '' });
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

  return (
    <div data-testid="leave-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Leave Management</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Kenyan Employment Act 2007 — 21 days annual</p>
        </div>
        <button data-testid="apply-leave-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Apply for Leave</button>
      </div>

      {/* Balances */}
      {balances && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {Object.entries(balances).map(([type, b]) => (
            <div key={type} data-testid={`balance-${type}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px' }}>{type}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '24px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919' }}>{b.remaining}</span>
                <span style={{ fontSize: '11px', color: '#525252' }}>of {b.entitlement}</span>
              </div>
              <div style={{ height: '4px', backgroundColor: '#F5F5F5', marginTop: '8px' }}>
                <div style={{ width: `${(b.used / b.entitlement) * 100}%`, height: '100%', backgroundColor: '#FF353F' }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Requests */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
              {['Employee', 'Type', 'Period', 'Days', 'Handover', 'Status', 'Action'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {requests.map((r, i) => (
                <tr key={r.id} data-testid={`leave-${r.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '11px' }}>{(r.employee_id || '').substring(0, 8)}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.leave_type}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.start_date} → {r.end_date}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.working_days}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{r.handover_contact || '—'}</td>
                  <td style={{ padding: '10px 14px' }}><StatusBadge status={r.status?.replace('Pending_', '').replace('_', ' ')} small /></td>
                  <td style={{ padding: '10px 14px' }}>
                    {canDecide && r.status === 'Pending_Manager' && (
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button onClick={() => decide(r.id, 'Approve')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', color: '#22C55E', background: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Approve</button>
                        <button onClick={() => decide(r.id, 'Reject')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {requests.length === 0 && <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No leave requests</td></tr>}
            </tbody>
          </table>
        )}
      </div>

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Apply for Leave</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={submit} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Leave Type</label>
                  <select required value={form.leave_type} onChange={e => setForm(p => ({ ...p, leave_type: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                    {Object.keys(types).map(t => <option key={t} value={t}>{t} — {types[t].description}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Start Date</label>
                  <input type="date" required value={form.start_date} onChange={e => setForm(p => ({ ...p, start_date: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>End Date</label>
                  <input type="date" required value={form.end_date} onChange={e => setForm(p => ({ ...p, end_date: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
                <div style={{ gridColumn: '1 / -1', backgroundColor: '#F5F5F5', padding: '8px 12px', fontSize: '12px' }}>Working Days: <strong>{calcDays()}</strong></div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Handover Contact</label>
                  <input value={form.handover_contact} onChange={e => setForm(p => ({ ...p, handover_contact: e.target.value }))} placeholder="Name of colleague covering" style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Handover Notes</label>
                  <textarea rows={3} value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Submitting...' : 'Submit Request'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
