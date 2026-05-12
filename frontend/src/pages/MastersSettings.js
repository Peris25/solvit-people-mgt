/**
 * MastersSettings — system-wide configuration module.
 * IT Admin: full write. HR Admin / Finance: section-scoped write.
 */
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
import ValueEditor, { prettify } from '../components/MastersValueEditor';
import EmailTemplates from '../components/EmailTemplates';
import OnboardingTourConfig from '../components/OnboardingTourConfig';

const CATEGORIES = [
  { key: 'organisation',         label: 'Organisation' },
  { key: 'workforce',            label: 'Workforce & Org Structure' },
  { key: 'performance',          label: 'Performance Management' },
  { key: 'budget_compensation',  label: 'Budget & Compensation' },
  { key: 'onboarding',           label: 'Onboarding' },
  { key: 'recruitment',          label: 'Recruitment' },
  { key: 'alignment_surveys',    label: 'Alignment Surveys' },
  { key: 'retention',            label: 'Retention & Stay Interviews' },
  { key: 'recognition',          label: 'Recognition & Rewards' },
  { key: 'notifications',        label: 'Notifications & Automation' },
  { key: 'lookups',              label: 'Lookup Tables' },
  { key: 'email_templates',      label: 'Email Templates', custom: true },
  { key: 'onboarding_tour',      label: 'Onboarding Tour', custom: true },
];

export default function MastersSettings() {
  const { user } = useAuth();
  const [meta, setMeta] = useState(null);
  const [tab, setTab] = useState('organisation');
  const [edits, setEdits] = useState({});
  const [auditLog, setAuditLog] = useState([]);
  const [showAudit, setShowAudit] = useState(false);
  const [savingMsg, setSavingMsg] = useState('');
  const [loading, setLoading] = useState(true);

  const canRead = ['it_admin', 'hr_admin', 'hr_manager', 'finance'].includes(user?.role);

  useEffect(() => {
    if (!canRead) { setLoading(false); return; }
    Promise.all([api.listMastersSettings(), api.getAllMastersSettings()])
      .then(([m, all]) => {
        // Inject pseudo-write rights for the custom tabs so the UI doesn't gate them via the standard backend matrix.
        const meta = m.data || {};
        if (meta.write_access) {
          meta.write_access.email_templates = user?.role === 'it_admin';
          meta.write_access.onboarding_tour = user?.role === 'it_admin';
        }
        setMeta(meta);
        setEdits(all.data || {});
      })
      .finally(() => setLoading(false));
  }, [canRead, user]);

  const loadAudit = async () => {
    const r = await api.getMastersAudit({ category: tab });
    setAuditLog(r.data || []);
    setShowAudit(true);
  };

  const writable = meta?.write_access?.[tab];

  const save = async () => {
    setSavingMsg('Saving...');
    await api.updateMastersSettings(tab, edits[tab]);
    const r = await api.getMastersSettings(tab);
    setEdits(p => ({ ...p, [tab]: r.data.values }));
    setSavingMsg('Saved ✓');
    setTimeout(() => setSavingMsg(''), 1500);
  };

  const reset = async () => {
    if (!window.confirm(`Reset ${tab} to factory defaults?`)) return;
    setSavingMsg('Resetting...');
    await api.resetMastersSettings(tab);
    const r = await api.getMastersSettings(tab);
    setEdits(p => ({ ...p, [tab]: r.data.values }));
    setSavingMsg('Reset ✓');
    setTimeout(() => setSavingMsg(''), 1500);
  };

  if (!canRead) return <div data-testid="masters-no-access" style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>No access to Masters Settings.</div>;
  if (loading) return <div style={{ padding: '48px', textAlign: 'center' }}>Loading settings...</div>;

  const currentValues = edits[tab] || {};
  const showAuditBtn = user.role === 'it_admin' || user.role === 'hr_admin';
  const showResetBtn = writable && user.role === 'it_admin';

  return (
    <div data-testid="masters-settings-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '16px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0 }}>Masters Settings</h1>
          <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>System-wide configuration. Changes apply immediately.</p>
        </div>
        {showAuditBtn && (
          <button data-testid="btn-audit-log" onClick={loadAudit} style={{ padding: '8px 14px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Audit Log</button>
        )}
      </div>

      <div data-testid="masters-tabs" style={{ display: 'flex', gap: '4px', borderBottom: '1px solid rgba(25,25,25,0.08)', marginBottom: '16px', overflowX: 'auto' }}>
        {CATEGORIES.map(c => {
          const w = meta?.write_access?.[c.key];
          return (
            <button
              key={c.key}
              data-testid={`tab-${c.key}`}
              onClick={() => setTab(c.key)}
              style={{
                padding: '10px 14px', background: 'none', border: 'none',
                borderBottom: tab === c.key ? '2px solid #FF353F' : '2px solid transparent',
                color: tab === c.key ? '#191919' : '#525252',
                fontSize: '12px', fontWeight: tab === c.key ? 700 : 500,
                cursor: 'pointer', whiteSpace: 'nowrap',
                fontFamily: 'Arial', letterSpacing: '-0.01em',
              }}
            >
              {c.label}
              {!w && <span style={{ marginLeft: '6px', fontSize: '8px', color: '#9CA3AF', textTransform: 'uppercase' }}>read</span>}
            </button>
          );
        })}
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '12px 16px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '12px', color: '#525252' }}>
          {writable
            ? <span style={{ color: '#22C55E', fontWeight: 700 }}>● Editable</span>
            : <span style={{ color: '#9CA3AF', fontWeight: 700 }}>● Read-only for your role</span>}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {savingMsg && <span style={{ fontSize: '11px', color: '#22C55E', fontWeight: 700 }}>{savingMsg}</span>}
          {showResetBtn && tab !== 'email_templates' && tab !== 'onboarding_tour' && (
            <button data-testid="btn-reset-defaults" onClick={reset} style={{ padding: '8px 14px', border: '1px solid rgba(25,25,25,0.2)', background: 'transparent', cursor: 'pointer', fontSize: '11px', fontWeight: 700 }}>Reset to defaults</button>
          )}
          {writable && tab !== 'email_templates' && tab !== 'onboarding_tour' && (
            <button data-testid="btn-save-settings" onClick={save} style={{ padding: '8px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Save</button>
          )}
        </div>
      </div>

      <div data-testid={`masters-form-${tab}`} style={{ backgroundColor: tab === 'email_templates' || tab === 'onboarding_tour' ? 'transparent' : '#fff', border: tab === 'email_templates' || tab === 'onboarding_tour' ? 'none' : '1px solid rgba(25,25,25,0.08)', padding: tab === 'email_templates' || tab === 'onboarding_tour' ? 0 : '16px 20px' }}>
        {tab === 'email_templates' ? (
          <EmailTemplates />
        ) : tab === 'onboarding_tour' ? (
          <OnboardingTourConfig />
        ) : Object.entries(currentValues).map(([k, v]) => (
          <div key={k} style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '16px', alignItems: 'flex-start', padding: '12px 0', borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
            <label style={{ fontSize: '12px', fontWeight: 700, color: '#191919', paddingTop: '8px' }}>{prettify(k)}</label>
            <ValueEditor
              keyName={k}
              value={v}
              disabled={!writable}
              testIdPrefix={`${tab}.`}
              onChange={(nv) => setEdits(p => ({ ...p, [tab]: { ...p[tab], [k]: nv } }))}
            />
          </div>
        ))}
      </div>

      {showAudit && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div data-testid="audit-modal" style={{ backgroundColor: '#fff', width: '720px', maxHeight: '80vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Settings Audit Log — {tab}</h3>
              <button onClick={() => setShowAudit(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ overflowY: 'auto', padding: '12px' }}>
              {auditLog.length === 0 ? (
                <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No changes recorded yet.</div>
              ) : (
                <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
                  <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                    {['When', 'Who', 'Field', 'From', 'To'].map(h => (
                      <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 700, textTransform: 'uppercase', fontSize: '9px', letterSpacing: '0.1em', color: '#525252' }}>{h}</th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {auditLog.map(r => (
                      <tr key={r.id} style={{ borderTop: '1px solid rgba(25,25,25,0.05)' }}>
                        <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>{r.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                        <td style={{ padding: '6px 10px' }}>{r.changed_by_name} <span style={{ color: '#9CA3AF' }}>({r.changed_by_role})</span></td>
                        <td style={{ padding: '6px 10px', fontWeight: 700 }}>{r.field}</td>
                        <td style={{ padding: '6px 10px', color: '#FF353F' }}>{JSON.stringify(r.old_value)}</td>
                        <td style={{ padding: '6px 10px', color: '#22C55E' }}>{JSON.stringify(r.new_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
