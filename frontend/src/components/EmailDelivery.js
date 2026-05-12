/**
 * EmailDelivery — Testing (Mailtrap) / Production (Office 365) toggle.
 * Embedded in Settings page; IT Admin only edit, HR Admin view active mode.
 */
import React, { useEffect, useState } from 'react';
import * as api from '../services/api';

const FIELDS_TESTING = ['smtp_host', 'smtp_port', 'username', 'password', 'from_name', 'from_email'];
const FIELDS_PROD = ['smtp_host', 'smtp_port', 'encryption', 'username', 'password', 'from_name', 'from_email'];
const LABELS = {
  smtp_host: 'SMTP Host', smtp_port: 'SMTP Port', username: 'Username',
  password: 'Password / App Password', from_name: 'From Name', from_email: 'From Email Address',
  encryption: 'Encryption',
};

export default function EmailDelivery() {
  const [cfg, setCfg] = useState(null);
  const [testing, setTesting] = useState({});
  const [production, setProduction] = useState({});
  const [savingMode, setSavingMode] = useState(null);
  const [testTo, setTestTo] = useState('');
  const [testing_send, setTestingSend] = useState(false);
  const [switchTarget, setSwitchTarget] = useState(null);
  const [audit, setAudit] = useState([]);

  const load = async () => {
    try {
      const r = await api.getEmailDelivery();
      setCfg(r.data);
      setTesting(r.data?.testing || {});
      setProduction(r.data?.production || {});
    } catch {}
    try {
      const a = await api.getEmailDeliveryAudit();
      setAudit(a.data || []);
    } catch {}
  };
  useEffect(() => { load(); }, []);

  if (!cfg) return <div style={{ padding: '24px', color: '#525252' }}>Loading…</div>;
  const canEdit = !!cfg.can_edit;
  const active = cfg.active_mode || 'testing';

  const saveMode = async (mode) => {
    setSavingMode(mode);
    try {
      const payload = mode === 'testing' ? testing : production;
      // Strip masked passwords (keep server-side value if blank/masked)
      if (payload.password && payload.password.includes('***')) delete payload.password;
      payload.smtp_port = Number(payload.smtp_port) || 0;
      await api.updateEmailDeliveryMode(mode, payload);
      await load();
    } finally { setSavingMode(null); }
  };

  const performSwitch = async () => {
    if (!switchTarget) return;
    await api.switchEmailDeliveryMode(switchTarget);
    setSwitchTarget(null);
    await load();
  };

  const runTestSend = async () => {
    if (!testTo) { alert('Enter destination email'); return; }
    setTestingSend(true);
    try {
      await api.sendEmailDeliveryTest(testTo);
      await load();
    } catch (err) {
      alert('Test send failed: ' + (err?.response?.data?.detail || err.message));
    } finally { setTestingSend(false); }
  };

  const renderForm = (mode, state, setState, fields) => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
      {fields.map(f => (
        <div key={f}>
          <label style={lbl}>{LABELS[f]}</label>
          {f === 'encryption' ? (
            <select disabled={!canEdit} value={state[f] || 'STARTTLS'} onChange={e => setState(s => ({ ...s, [f]: e.target.value }))} style={inp}>
              {['STARTTLS','SSL','None'].map(o => <option key={o}>{o}</option>)}
            </select>
          ) : (
            <input
              data-testid={`${mode}-${f}`}
              disabled={!canEdit}
              type={f === 'password' ? 'password' : (f === 'smtp_port' ? 'number' : 'text')}
              value={state[f] != null ? state[f] : ''}
              onChange={e => setState(s => ({ ...s, [f]: e.target.value }))}
              placeholder={f === 'password' && state[f] && String(state[f]).includes('***') ? 'Leave blank to keep current' : ''}
              style={inp}
            />
          )}
        </div>
      ))}
      {canEdit && (
        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end' }}>
          <button data-testid={`save-${mode}-btn`} onClick={() => saveMode(mode)} disabled={savingMode === mode} style={btnRed}>{savingMode === mode ? 'Saving…' : `Save ${mode === 'testing' ? 'Testing' : 'Production'} Config`}</button>
        </div>
      )}
    </div>
  );

  return (
    <div data-testid="email-delivery-section" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      {/* Banner */}
      <div data-testid="active-mode-banner" style={{
        padding: '14px 18px', marginBottom: '20px',
        backgroundColor: active === 'production' ? '#DCFCE7' : '#FEE2E2',
        borderLeftWidth: '5px', borderLeftStyle: 'solid',
        borderLeftColor: active === 'production' ? '#16A34A' : '#FF353F',
        color: '#191919', fontSize: '13px', fontWeight: 600,
      }}>
        <strong style={{ fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '11px', color: active === 'production' ? '#166534' : '#FF353F' }}>
          {active === 'production' ? 'Production mode is active' : 'Testing mode is active'}
        </strong>
        <div style={{ marginTop: '2px' }}>
          {active === 'production'
            ? 'Emails are being delivered to real recipients.'
            : 'All emails are being sent to Mailtrap and will not reach real recipients.'}
        </div>
      </div>

      {/* Mode switcher */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '20px' }}>
        <strong style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', fontFamily: 'Barlow' }}>Mode:</strong>
        {['testing', 'production'].map(m => (
          <button key={m}
            data-testid={`mode-${m}`}
            disabled={!canEdit || m === active}
            onClick={() => setSwitchTarget(m)}
            style={{
              padding: '8px 18px', backgroundColor: m === active ? (m === 'production' ? '#16A34A' : '#FF353F') : '#fff',
              color: m === active ? '#fff' : '#191919',
              border: m === active ? 'none' : '1px solid rgba(25,25,25,0.2)',
              cursor: (!canEdit || m === active) ? 'default' : 'pointer',
              fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em'
            }}>{m === active ? `${m} (active)` : `Switch to ${m}`}</button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <h4 style={{ margin: '0 0 14px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Testing — Mailtrap</h4>
          {renderForm('testing', testing, setTesting, FIELDS_TESTING)}
        </div>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <h4 style={{ margin: '0 0 14px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Production — Office 365</h4>
          {renderForm('production', production, setProduction, FIELDS_PROD)}
        </div>
      </div>

      {/* Test send + status */}
      <div style={{ marginTop: '20px', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
        <h4 style={{ margin: '0 0 12px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Send Test Email</h4>
        <p style={{ fontSize: '12px', color: '#525252', marginTop: 0 }}>Uses the active mode's saved configuration.</p>
        {canEdit && (
          <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '260px' }}>
              <label style={lbl}>Destination Email</label>
              <input data-testid="test-to-email" type="email" value={testTo} onChange={e => setTestTo(e.target.value)} placeholder="your.email@example.com" style={inp} />
            </div>
            <button data-testid="test-send-btn" onClick={runTestSend} disabled={testing_send} style={btnRed}>{testing_send ? 'Sending…' : 'Send Test'}</button>
          </div>
        )}
        {cfg.last_test && (
          <div data-testid="last-test-status" style={{ marginTop: '14px', padding: '12px 14px', backgroundColor: cfg.last_test.status === 'Success' ? '#DCFCE7' : '#FEE2E2', fontSize: '12px', color: '#191919' }}>
            <strong>Last Test:</strong> {cfg.last_test.status} · code {cfg.last_test.smtp_code} · to {cfg.last_test.to} · {cfg.last_test.tested_at ? new Date(cfg.last_test.tested_at).toLocaleString('en-GB') : ''}
            {cfg.last_test.error && <div style={{ marginTop: '4px', color: '#FF353F', fontSize: '11px' }}>{cfg.last_test.error}</div>}
          </div>
        )}
      </div>

      {/* Audit */}
      {audit.length > 0 && (
        <div style={{ marginTop: '20px', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <h4 style={{ margin: '0 0 12px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.01em' }}>Mode Switch Audit</h4>
          <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
            <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
              {['When', 'From', 'To', 'By'].map(h => <th key={h} style={{ padding: '6px 12px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {audit.slice(0, 15).map(a => (
                <tr key={a.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                  <td style={{ padding: '6px 12px' }}>{new Date(a.timestamp).toLocaleString('en-GB')}</td>
                  <td style={{ padding: '6px 12px' }}>{a.old_mode || '—'}</td>
                  <td style={{ padding: '6px 12px', fontWeight: 700 }}>{a.new_mode}</td>
                  <td style={{ padding: '6px 12px' }}>{a.by_user_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Mode switch confirmation */}
      {switchTarget && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}>
          <div data-testid="confirm-switch-modal" style={{ width: '440px', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '16px 22px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
              <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900 }}>Confirm Mode Switch</h3>
            </div>
            <div style={{ padding: '18px 22px', fontSize: '13px', color: '#191919' }}>
              You are switching to <strong>{switchTarget}</strong> mode. All subsequent emails will be{' '}
              <strong>{switchTarget === 'production' ? 'delivered to real recipients' : 'routed to Mailtrap'}</strong>.
            </div>
            <div style={{ padding: '14px 22px', borderTop: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button onClick={() => setSwitchTarget(null)} style={btnGhost}>Cancel</button>
              <button data-testid="confirm-switch-btn" onClick={performSwitch} style={btnRed}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans', boxSizing: 'border-box' };
const btnRed = { padding: '9px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' };
const btnGhost = { padding: '9px 16px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };
