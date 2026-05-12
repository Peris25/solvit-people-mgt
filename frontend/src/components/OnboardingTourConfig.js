/**
 * OnboardingTourConfig — IT Admin controls for the first-login walkthrough.
 * Headline/body text, enable/disable toggle, per-user reset, completion report.
 */
import React, { useEffect, useState } from 'react';
import * as api from '../services/api';

export default function OnboardingTourConfig() {
  const [cfg, setCfg] = useState(null);
  const [report, setReport] = useState(null);
  const [saving, setSaving] = useState(false);
  const [emps, setEmps] = useState([]);
  const [resetTargetId, setResetTargetId] = useState('');

  const loadAll = async () => {
    try {
      const [c, r] = await Promise.all([api.getTourConfig(), api.getTourReport()]);
      setCfg(c.data);
      setReport(r.data);
    } catch {}
    try {
      const e = await api.getEmployees();
      setEmps((e.data || []).slice(0, 200));
    } catch {}
  };
  useEffect(() => { loadAll(); }, []);

  if (!cfg) return <div style={{ padding: '24px', color: '#525252' }}>Loading…</div>;

  const save = async () => {
    setSaving(true);
    try {
      await api.updateTourConfig({ enabled: cfg.enabled, headline_template: cfg.headline_template, body_text: cfg.body_text });
      await loadAll();
    } finally { setSaving(false); }
  };

  const resetUser = async () => {
    if (!resetTargetId) return;
    if (!window.confirm('Reset the first-login tour for this user? It will fire again on their next login.')) return;
    await api.resetTourForUser(resetTargetId);
    setResetTargetId('');
    alert('Tour reset.');
  };

  return (
    <div data-testid="tour-config-section" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', marginBottom: '20px' }}>
        <h4 style={{ margin: '0 0 14px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Welcome Modal Content</h4>
        <div style={{ display: 'grid', gap: '14px' }}>
          <div>
            <label style={lbl}>Headline template (supports <code>{'{{first_name}}'}</code>)</label>
            <input data-testid="tour-headline" value={cfg.headline_template || ''} onChange={e => setCfg(c => ({ ...c, headline_template: e.target.value }))} style={inp} />
          </div>
          <div>
            <label style={lbl}>Body text</label>
            <textarea data-testid="tour-body" rows={3} value={cfg.body_text || ''} onChange={e => setCfg(c => ({ ...c, body_text: e.target.value }))} style={{ ...inp, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              <input data-testid="tour-enabled" type="checkbox" checked={!!cfg.enabled} onChange={e => setCfg(c => ({ ...c, enabled: e.target.checked }))} />
              Enable the tour globally
            </label>
            <button data-testid="tour-save-btn" onClick={save} disabled={saving} style={btnRed}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', marginBottom: '20px' }}>
        <h4 style={{ margin: '0 0 14px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Reset Tour for a Specific User</h4>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select data-testid="tour-reset-user" value={resetTargetId} onChange={e => setResetTargetId(e.target.value)} style={{ ...inp, maxWidth: '420px' }}>
            <option value="">Select user…</option>
            {emps.map(e => <option key={e.id} value={e.user_id || e.id}>{e.full_name} · {e.role_title}</option>)}
          </select>
          <button data-testid="tour-reset-btn" onClick={resetUser} disabled={!resetTargetId} style={btnGhost}>Reset Tour</button>
        </div>
      </div>

      {report && (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <h4 style={{ margin: '0 0 14px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Completion Report</h4>
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
            <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
              {['Role', 'Total', 'Completed', 'Skipped', 'Pending'].map(h =>
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {Object.entries(report.by_role || {}).map(([role, b]) => (
                <tr key={role} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 700 }}>{role}</td>
                  <td style={{ padding: '8px 12px' }}>{b.total}</td>
                  <td style={{ padding: '8px 12px', color: '#16A34A', fontWeight: 700 }}>{b.completed}</td>
                  <td style={{ padding: '8px 12px', color: '#F97316' }}>{b.skipped}</td>
                  <td style={{ padding: '8px 12px', color: '#FF353F' }}>{b.pending}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '8px' }}>Total users tracked: {report.total_users}</div>
        </div>
      )}
    </div>
  );
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans', boxSizing: 'border-box' };
const btnRed = { padding: '9px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' };
const btnGhost = { padding: '9px 16px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };
