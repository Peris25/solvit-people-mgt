import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../services/api';

const GROUPS = [
  'Onboarding', 'Probation', 'Performance', 'Surveys', 'Leave',
  'Recognition', 'Policy', 'Retention', 'Exit', 'Recruitment', 'System',
];

const fmtDate = (s) => {
  if (!s) return '—';
  try { return new Date(s).toLocaleString('en-KE', { dateStyle: 'short', timeStyle: 'short' }); }
  catch { return s; }
};

export default function ReminderRules() {
  const [config, setConfig] = useState(null);
  const [rules, setRules] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [groupFilter, setGroupFilter] = useState('');
  const [logModal, setLogModal] = useState(null); // { rule_id, name }
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, r] = await Promise.all([api.getReminderConfig(), api.getReminderRules()]);
      setConfig(c.data.config);
      setCanEdit(c.data.can_edit);
      setRules(r.data.rules);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleRule = async (ruleId, enabled) => {
    setSavingId(ruleId);
    try {
      await api.updateReminderRule(ruleId, { enabled });
      await load();
    } finally { setSavingId(null); }
  };

  const runNow = async (ruleId) => {
    setSavingId(ruleId);
    try {
      const res = await api.runReminderNow(ruleId);
      alert(`Rule ${ruleId} executed:\nEvaluated: ${res.data.evaluated}\nFired: ${res.data.fired}\nSkipped (dedup): ${res.data.skipped}\nStatus: ${res.data.status}`);
      await load();
    } catch (e) {
      alert(`Run failed: ${e.response?.data?.detail || e.message}`);
    } finally { setSavingId(null); }
  };

  const toggleMaster = async (enabled) => {
    await api.updateReminderConfig({ master_enabled: enabled });
    await load();
  };

  const saveDailyTime = async (newTime) => {
    if (!/^\d{2}:\d{2}$/.test(newTime)) return;
    await api.updateReminderConfig({ daily_run_time: newTime });
    await load();
  };

  const filtered = rules.filter(r => {
    const t = filter.toLowerCase();
    return (!t || r.id.toLowerCase().includes(t) || r.name.toLowerCase().includes(t))
        && (!groupFilter || r.group === groupFilter);
  });

  if (loading) return <div style={{ padding: '24px' }}>Loading reminder rules…</div>;

  return (
    <div data-testid="reminder-rules-section">
      {/* Master config bar */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px 20px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '24px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Reminder Service</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' }}>
            <span style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 700, backgroundColor: config?.master_enabled ? '#DCFCE7' : '#FEE2E2', color: config?.master_enabled ? '#166534' : '#991B1B' }}>
              {config?.master_enabled ? 'ACTIVE' : 'PAUSED'}
            </span>
            {canEdit && (
              <button data-testid="reminder-master-toggle" onClick={() => toggleMaster(!config?.master_enabled)} style={{ padding: '4px 10px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700 }}>
                {config?.master_enabled ? 'Pause All' : 'Resume All'}
              </button>
            )}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Daily Run Time</div>
          <input
            data-testid="reminder-daily-time"
            type="time"
            defaultValue={config?.daily_run_time || '08:00'}
            disabled={!canEdit}
            onBlur={(e) => e.target.value !== config?.daily_run_time && saveDailyTime(e.target.value)}
            style={{ marginTop: '6px', padding: '4px 8px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}
          />
        </div>
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Timezone</div>
          <div style={{ marginTop: '6px', padding: '4px 8px', fontSize: '13px', color: '#525252' }}>Africa/Nairobi (EAT, UTC+3)</div>
        </div>
        <div style={{ marginLeft: 'auto', fontSize: '12px', color: '#525252' }}>
          <strong style={{ color: '#191919' }}>{rules.length}</strong> rules · <strong style={{ color: '#191919' }}>{rules.filter(r => r.enabled).length}</strong> enabled
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '12px' }}>
        <input
          data-testid="reminder-filter"
          placeholder="Search rules…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{ flex: 1, padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}
        />
        <select value={groupFilter} onChange={e => setGroupFilter(e.target.value)} style={{ padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }} data-testid="reminder-group-filter">
          <option value="">All groups</option>
          {GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      {/* Rules table */}
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead style={{ backgroundColor: '#F9FAFB', borderBottom: '2px solid rgba(25,25,25,0.08)' }}>
            <tr style={{ textAlign: 'left', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.1em', color: '#525252' }}>
              <th style={{ padding: '10px 12px' }}>Rule</th>
              <th style={{ padding: '10px 12px' }}>Group</th>
              <th style={{ padding: '10px 12px' }}>Schedule</th>
              <th style={{ padding: '10px 12px' }}>Last Run</th>
              <th style={{ padding: '10px 12px' }}>Next Run</th>
              <th style={{ padding: '10px 12px', textAlign: 'center' }}>Enabled</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id} data-testid={`rem-row-${r.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.04)' }}>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: 700, color: '#191919' }}>{r.name}</div>
                  <div style={{ fontSize: '11px', color: '#9CA3AF' }}>{r.id}</div>
                </td>
                <td style={{ padding: '10px 12px', color: '#525252' }}>{r.group}</td>
                <td style={{ padding: '10px 12px', color: '#525252', fontSize: '11px' }}>{r.schedule_human}</td>
                <td style={{ padding: '10px 12px', color: '#525252' }}>
                  {r.last_run_at ? (
                    <>
                      <div>{fmtDate(r.last_run_at)}</div>
                      <div style={{ fontSize: '11px' }}>
                        <span style={{ color: r.last_status === 'Completed' ? '#16A34A' : r.last_status === 'Failed' ? '#FF353F' : '#F97316' }}>{r.last_status}</span>
                        {' · '}{r.last_fired} fired, {r.last_skipped} skipped
                      </div>
                    </>
                  ) : '—'}
                </td>
                <td style={{ padding: '10px 12px', color: '#525252', fontSize: '11px' }}>{fmtDate(r.next_run_at)}</td>
                <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={r.enabled}
                    disabled={!canEdit || savingId === r.id || !config?.master_enabled}
                    onChange={(e) => toggleRule(r.id, e.target.checked)}
                    data-testid={`rem-toggle-${r.id}`}
                  />
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                  {canEdit && (
                    <button
                      data-testid={`rem-run-${r.id}`}
                      onClick={() => runNow(r.id)}
                      disabled={savingId === r.id}
                      style={{ padding: '5px 10px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, marginRight: '6px' }}
                    >
                      {savingId === r.id ? '…' : 'Run Now'}
                    </button>
                  )}
                  <button
                    data-testid={`rem-log-${r.id}`}
                    onClick={() => setLogModal({ rule_id: r.id, name: r.name })}
                    style={{ padding: '5px 10px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700 }}
                  >
                    View Log
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No rules match the filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {logModal && <ReminderLogModal ruleId={logModal.rule_id} ruleName={logModal.name} onClose={() => setLogModal(null)} />}
    </div>
  );
}

function ReminderLogModal({ ruleId, ruleName, onClose }) {
  const [log, setLog] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getReminderLog({ rule_id: ruleId, limit: 100 }),
      api.getReminderRuns({ rule_id: ruleId, limit: 30 }),
    ]).then(([l, r]) => {
      setLog(l.data.log);
      setRuns(r.data.runs);
    }).finally(() => setLoading(false));
  }, [ruleId]);

  return (
    <div data-testid="reminder-log-modal" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200 }}>
      <div style={{ backgroundColor: '#fff', width: '900px', maxHeight: '85vh', overflow: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontWeight: 900, fontSize: '15px' }}>{ruleName} <span style={{ color: '#9CA3AF', fontWeight: 400 }}>· {ruleId}</span></h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '20px' }} data-testid="rem-log-close">×</button>
        </div>
        {loading ? <div style={{ padding: '40px', textAlign: 'center' }}>Loading…</div> : (
          <div style={{ padding: '16px 20px' }}>
            <h4 style={{ margin: '0 0 8px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252' }}>Recent Runs ({runs.length})</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', marginBottom: '20px' }}>
              <thead style={{ backgroundColor: '#F9FAFB' }}>
                <tr style={{ textAlign: 'left' }}>
                  <th style={{ padding: '8px' }}>When</th>
                  <th style={{ padding: '8px' }}>Trigger</th>
                  <th style={{ padding: '8px' }}>Evaluated</th>
                  <th style={{ padding: '8px' }}>Fired</th>
                  <th style={{ padding: '8px' }}>Skipped</th>
                  <th style={{ padding: '8px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={r.id} style={{ borderTop: '1px solid rgba(25,25,25,0.04)' }}>
                    <td style={{ padding: '6px 8px' }}>{fmtDate(r.started_at)}</td>
                    <td style={{ padding: '6px 8px' }}>{r.triggered_by}</td>
                    <td style={{ padding: '6px 8px' }}>{r.evaluated}</td>
                    <td style={{ padding: '6px 8px', color: '#16A34A', fontWeight: 700 }}>{r.fired}</td>
                    <td style={{ padding: '6px 8px', color: '#9CA3AF' }}>{r.skipped}</td>
                    <td style={{ padding: '6px 8px', fontWeight: 700, color: r.status === 'Completed' ? '#16A34A' : r.status === 'Failed' ? '#FF353F' : '#F97316' }}>{r.status}</td>
                  </tr>
                ))}
                {runs.length === 0 && <tr><td colSpan={6} style={{ padding: '16px', textAlign: 'center', color: '#9CA3AF' }}>No runs yet</td></tr>}
              </tbody>
            </table>

            <h4 style={{ margin: '0 0 8px', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252' }}>Reminders Fired ({log.length})</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead style={{ backgroundColor: '#F9FAFB' }}>
                <tr style={{ textAlign: 'left' }}>
                  <th style={{ padding: '8px' }}>Fired At</th>
                  <th style={{ padding: '8px' }}>Target</th>
                  <th style={{ padding: '8px' }}>Dedup Key</th>
                  <th style={{ padding: '8px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {log.map(e => (
                  <tr key={e.id} style={{ borderTop: '1px solid rgba(25,25,25,0.04)' }}>
                    <td style={{ padding: '6px 8px' }}>{fmtDate(e.fired_at)}</td>
                    <td style={{ padding: '6px 8px' }}>{e.target_id}</td>
                    <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: '11px', color: '#525252' }}>{e.dedup_key}</td>
                    <td style={{ padding: '6px 8px', fontWeight: 700, color: e.status === 'Fired' ? '#16A34A' : '#FF353F' }}>{e.status}</td>
                  </tr>
                ))}
                {log.length === 0 && <tr><td colSpan={4} style={{ padding: '16px', textAlign: 'center', color: '#9CA3AF' }}>No reminders fired yet</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
