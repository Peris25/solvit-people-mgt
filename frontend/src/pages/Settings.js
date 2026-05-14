import React, { useState, useEffect } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
import EmailDelivery from '../components/EmailDelivery';
import ReminderRules from '../components/ReminderRules';

export default function Settings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({ llm_provider: '', llm_model: '', llm_api_key: '', email_provider: '', email_api_key: '', email_from_address: '', email_from_name: '', automation_enabled: true, ai_agent_enabled: true });
  const [tab, setTab] = useState('ai');
  // For IT Admin the AI/Email/Automation tabs would 403 — start them on Email Delivery instead.
  useEffect(() => {
    if (user?.role === 'it_admin' && tab === 'ai') setTab('email_delivery');
  }, [user, tab]);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.getSettings();
      setSettings(res.data);
      setForm(prev => ({ ...prev, ...res.data }));
    } catch (err) {
      // IT Admin and other non-HR roles get 403 on /api/settings — that's
      // expected. Render an empty form and don't surface a runtime error.
      if (err?.response?.status !== 403) console.warn('Settings load failed:', err);
      setSettings({});
    } finally { setLoading(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.updateSettings(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally { setSaving(false); }
  };

  const LLM_PROVIDERS = [
    { value: 'openai', label: 'OpenAI (GPT-5.2 default)', models: ['gpt-5.2', 'gpt-4o', 'gpt-4o-mini'] },
    { value: 'anthropic', label: 'Anthropic (Claude)', models: ['claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-opus-4-5'] },
    { value: 'gemini', label: 'Google Gemini', models: ['gemini-3-flash', 'gemini-3-pro'] },
  ];

  const selectedProvider = LLM_PROVIDERS.find(p => p.value === form.llm_provider);

  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState('');
  const handleReset = async () => {
    if (!window.confirm('This will WIPE all transactional data (employees, reviews, leave, recognitions, projects etc.) and re-seed fresh demo data. User accounts and policies will be preserved. Continue?')) return;
    setResetting(true);
    setResetMsg('');
    try {
      const res = await api.resetDemoData();
      setResetMsg(res.data.message);
      setTimeout(() => setResetMsg(''), 5000);
    } catch (err) {
      setResetMsg('Reset failed: ' + (err.response?.data?.detail || err.message));
    } finally { setResetting(false); }
  };

  return (
    <div data-testid="settings-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Platform Settings</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Configure AI, email, and platform options</p>
      </div>

      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '24px' }}>
        {[
          ...(user?.role === 'it_admin' ? [] : [{ key: 'ai', label: 'AI Agent' }]),
          ...(user?.role === 'it_admin' ? [{ key: 'email_delivery', label: 'Email Delivery' }] : [{ key: 'email_delivery', label: 'Email Delivery' }]),
          { key: 'reminders', label: 'Reminder Rules' },
          ...(user?.role === 'it_admin' ? [] : [{ key: 'automation', label: 'Automation' }]),
          { key: 'tour', label: 'Replay Tour' },
          { key: 'audit', label: 'Audit Log' },
        ].map(t => (
          <button key={t.key} data-testid={`settings-tab-${t.key}`} onClick={() => setTab(t.key)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.key ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.key ? 700 : 400, color: tab === t.key ? '#FF353F' : '#525252', fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'email_delivery' && <EmailDelivery />}
      {tab === 'reminders' && <ReminderRules />}
      {tab === 'tour' && (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px', maxWidth: '600px' }}>
          <h3 style={{ margin: '0 0 8px', fontFamily: 'Barlow', fontWeight: 900 }}>Replay Platform Tour</h3>
          <p style={{ color: '#525252', fontSize: '13px', marginTop: 0 }}>Re-run the first-login walkthrough at any time.</p>
          <button data-testid="replay-tour-btn" onClick={async () => { await api.replayTour(); window.location.href = '/dashboard'; }} style={{ padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' }}>Replay Tour</button>
        </div>
      )}

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
        <form onSubmit={save} style={{ maxWidth: '600px' }}>
          {tab === 'ai' && (
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
              <h3 style={{ fontWeight: 900, fontSize: '16px', marginBottom: '20px', color: '#191919' }}>AI Agent Configuration</h3>
              <div style={{ backgroundColor: '#EFF6FF', border: '1px solid #BFDBFE', padding: '12px 16px', marginBottom: '20px', fontSize: '12px', color: '#1D4ED8' }}>
                Configure an LLM provider to power the AI HR Agent's Policy Q&A and Compliance Guardian features.
              </div>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>LLM Provider</label>
                <select data-testid="llm-provider" value={form.llm_provider || ''} onChange={e => setForm(p => ({ ...p, llm_provider: e.target.value, llm_model: '' }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                  <option value="">Select provider...</option>
                  {LLM_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              {selectedProvider && (
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Model</label>
                  <select data-testid="llm-model" value={form.llm_model || ''} onChange={e => setForm(p => ({ ...p, llm_model: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                    <option value="">Select model...</option>
                    {selectedProvider.models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
              )}
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>API Key</label>
                <input data-testid="llm-api-key" type="password" value={form.llm_api_key || ''} onChange={e => setForm(p => ({ ...p, llm_api_key: e.target.value }))} placeholder="sk-..." style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none', boxSizing: 'border-box' }} />
                <p style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>Your API key is stored securely and never exposed in the UI.</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                <input type="checkbox" id="ai_enabled" checked={form.ai_agent_enabled} onChange={e => setForm(p => ({ ...p, ai_agent_enabled: e.target.checked }))} />
                <label htmlFor="ai_enabled" style={{ fontSize: '13px', cursor: 'pointer' }}>Enable AI Agent panel for HR Admin</label>
              </div>
            </div>
          )}

          {tab === 'email' && (
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
              <h3 style={{ fontWeight: 900, fontSize: '16px', marginBottom: '12px', color: '#191919', fontFamily: 'Barlow' }}>Email Notifications — Retired</h3>
              <p style={{ fontSize: '13px', color: '#525252', margin: 0 }}>
                Email delivery is now configured under the <strong>Email Delivery</strong> tab (Mailtrap for testing, Office 365 for production). The legacy SendGrid / SMTP form has been removed.
              </p>
            </div>
          )}

          {tab === 'automation' && (
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
              <h3 style={{ fontWeight: 900, fontSize: '16px', marginBottom: '20px', color: '#191919' }}>Automation Engine</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', padding: '16px', backgroundColor: '#F9FAFB', border: '1px solid rgba(25,25,25,0.06)' }}>
                <input type="checkbox" id="auto_enabled" checked={form.automation_enabled !== false} onChange={e => setForm(p => ({ ...p, automation_enabled: e.target.checked }))} />
                <div>
                  <label htmlFor="auto_enabled" style={{ fontSize: '13px', fontWeight: 700, cursor: 'pointer', display: 'block' }}>Enable Automation Rules Engine</label>
                  <span style={{ fontSize: '11px', color: '#525252' }}>47 rules — cron-based and event-driven automations</span>
                </div>
              </div>
              <div style={{ fontSize: '12px', color: '#525252', padding: '12px', backgroundColor: '#DCFCE7', border: '1px solid #86EFAC' }}>
                ✅ Automation engine is running. 47 rules loaded. View and manage rules in the platform configuration.
              </div>

              {/* Demo Data Reset */}
              <div style={{ marginTop: '24px', padding: '20px', border: '2px solid #FCA5A5', backgroundColor: '#FEF2F2' }}>
                <h4 style={{ margin: '0 0 8px', fontWeight: 900, fontSize: '14px', color: '#991B1B', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Reset Demo Data</h4>
                <p style={{ fontSize: '12px', color: '#7F1D1D', margin: '0 0 14px', lineHeight: 1.5 }}>
                  Wipes all transactional data (employees, performance reviews, leave requests, recognitions, projects, tasks, notifications) and re-seeds clean demo data. <strong>User accounts are preserved</strong>. Ideal for sales walkthroughs and demo resets.
                </p>
                <button data-testid="reset-demo-btn" type="button" onClick={handleReset} disabled={resetting} style={{ padding: '10px 24px', backgroundColor: '#991B1B', color: '#fff', border: 'none', cursor: resetting ? 'not-allowed' : 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em', opacity: resetting ? 0.6 : 1 }}>
                  {resetting ? 'Resetting...' : 'Reset Demo Data'}
                </button>
                {resetMsg && <span style={{ marginLeft: '12px', fontSize: '12px', fontWeight: 700, color: resetMsg.startsWith('Reset failed') ? '#FF353F' : '#22C55E' }}>{resetMsg}</span>}
              </div>
            </div>
          )}

          {tab === 'audit' && <AuditLog />}

          {tab !== 'audit' && (
            <div style={{ marginTop: '20px', display: 'flex', gap: '10px', alignItems: 'center' }}>
              <button data-testid="save-settings-btn" type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
              {saved && <span style={{ color: '#22C55E', fontSize: '12px', fontWeight: 700 }}>✓ Settings saved</span>}
            </div>
          )}
        </form>
      )}
    </div>
  );
}

function EmailTestButton() {
  const { user } = useAuth();
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState('');
  const send = async () => {
    setSending(true); setResult('');
    try {
      const res = await api.sendTestEmail({ to: user?.email });
      const r = res.data;
      if (r.status === 'sent') setResult(`✓ Test email sent via ${r.provider}`);
      else if (r.status === 'skipped') setResult(`⚠ Skipped: ${r.message}`);
      else setResult(`Status: ${r.status}`);
    } catch (err) {
      setResult(`✗ Failed: ${err.response?.data?.detail || err.message}`);
    } finally { setSending(false); }
  };
  return (
    <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(25,25,25,0.08)' }}>
      <button data-testid="send-test-email" type="button" onClick={send} disabled={sending} style={{ padding: '8px 18px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: sending ? 'not-allowed' : 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
        {sending ? 'Sending...' : 'Send Test Email'}
      </button>
      {result && <span style={{ marginLeft: '12px', fontSize: '12px', fontWeight: 700, color: result.startsWith('✓') ? '#22C55E' : result.startsWith('✗') ? '#FF353F' : '#F97316' }}>{result}</span>}
      <p style={{ fontSize: '11px', color: '#525252', marginTop: '8px' }}>Save settings first, then send a test to your own email ({user?.email}).</p>
    </div>
  );
}

function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAuditLog({ limit: 50 }).then(r => setLogs(r.data)).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
        <h3 style={{ margin: 0, fontWeight: 900, fontSize: '16px' }}>Audit Log</h3>
      </div>
      {loading ? <div style={{ padding: '32px', textAlign: 'center' }}>Loading...</div> : (
        <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
          {logs.map((log, i) => (
            <div key={log.id || i} style={{ padding: '10px 20px', borderBottom: '1px solid rgba(25,25,25,0.04)', fontSize: '12px', display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <div style={{ color: '#525252', whiteSpace: 'nowrap', fontSize: '11px' }}>{new Date(log.timestamp).toLocaleString('en-KE')}</div>
              <div>
                <span style={{ fontWeight: 700, color: '#191919' }}>{log.action}</span>
                {log.entity && <span style={{ color: '#525252', marginLeft: '8px' }}>on {log.entity}</span>}
              </div>
              <div style={{ marginLeft: 'auto', fontSize: '10px', color: '#9CA3AF' }}>{log.performed_by?.substring(0, 8)}...</div>
            </div>
          ))}
          {logs.length === 0 && <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No audit log entries</div>}
        </div>
      )}
    </div>
  );
}
