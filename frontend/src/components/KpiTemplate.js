import { MAX_REVIEW_KPIS } from './performanceLimits';
import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

const blank = () => ({ objective: '', metric: '', target: '' });
const control = { width: '100%', minHeight: 44, padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, boxSizing: 'border-box', font: 'inherit' };
const message = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e.message || 'Unable to complete this action.';

export default function KpiTemplate({ reviews, onUpdated }) {
  const [saved, setSaved] = useState(null);
  const [values, setValues] = useState({ name: 'Standard employee KPIs', goals: [blank(), blank(), blank()] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selection, setSelection] = useState([]);
  const [due, setDue] = useState('');
  const [result, setResult] = useState(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError('');
    (async () => {
      try {
        const response = await api.getKpiTemplate();
        const template = response?.data;
        if (template !== null && (!template?.version || !Array.isArray(template.goals))) throw new Error('Unable to load the KPI template.');
        if (!cancelled) { setSaved(template); if (template) setValues({ name: template.name, goals: template.goals }); }
      } catch (e) { if (!cancelled) setError(message(e)); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [reload]);
  const eligible = reviews.filter(r => r.workflow_version === 1 && r.cycle_type !== 'Probation' && ['Draft', 'Self_Draft'].includes(r.status) && !r.goals_acknowledged_at && !(r.section_a_kpis || []).length);
  const ids = selection.filter(id => eligible.some(r => r.id === id));
  const dirty = !saved || JSON.stringify(values) !== JSON.stringify({ name: saved.name, goals: saved.goals });
  const change = (index, key, value) => setValues(v => ({ ...v, goals: v.goals.map((goal, i) => i === index ? { ...goal, [key]: value } : goal) }));
  return <details style={{ background: '#fff', padding: 20, marginBottom: 20, borderRadius: 12 }}>
    <summary style={{ cursor: 'pointer', fontWeight: 700, padding: '8px 0' }}>Standard KPI template (HR)</summary>
    <p>Create the standard KPIs once, then copy them into selected employee reviews. Existing goals and assessments are preserved.</p>
    {loading ? <p role="status">Loading KPI template...</p> : <>
      {error && <div role="alert"><p>{error}</p><LeaveActionButton onClick={() => setReload(n => n + 1)} disabled={busy}>Reload template</LeaveActionButton></div>}
      <form onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError(''); setResult(null);
        try {
          const response = await api.saveKpiTemplate({ ...values, expected_version: saved?.version || null });
          if (!response?.data?.version) throw new Error('Template save could not be confirmed. Reload before retrying.');
          setSaved(response.data); setValues({ name: response.data.name, goals: response.data.goals });
        } catch (e) { setError(message(e)); } finally { setBusy(false); }
      }}>
        <label style={{ display: 'grid', gap: 6 }}>Template name<input required maxLength={150} style={control} value={values.name} onChange={e => setValues(v => ({ ...v, name: e.target.value }))} /></label>
        {values.goals.map((goal, index) => <fieldset key={index} style={{ border: '1px solid #e2e8f0', borderRadius: 10, padding: 14, margin: '14px 0' }}>
          <legend>KPI {index + 1}</legend>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 }}>
            {[['objective', 'Objective'], ['metric', 'Measurement'], ['target', 'Target']].map(([key, label]) => <label key={key} style={{ display: 'grid', gap: 6 }}>{label}<input aria-label={`${label} KPI ${index + 1}`} required maxLength={500} style={control} value={goal[key]} onChange={e => change(index, key, e.target.value)} /></label>)}
          </div>
          {values.goals.length > 3 && <LeaveActionButton disabled={busy} onClick={() => setValues(v => ({ ...v, goals: v.goals.filter((_, i) => i !== index) }))}>Remove KPI {index + 1}</LeaveActionButton>}
        </fieldset>)}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <LeaveActionButton disabled={busy || values.goals.length >= MAX_REVIEW_KPIS} onClick={() => setValues(v => ({ ...v, goals: [...v.goals, blank()] }))}>Add KPI</LeaveActionButton>
          <LeaveActionButton type="submit" variant="primary" disabled={busy}>Save KPI template</LeaveActionButton>
          {saved && !dirty && <span role="status">Template saved</span>}
        </div>
      </form>
      <form style={{ borderTop: '1px solid #e2e8f0', marginTop: 22, paddingTop: 16 }} onSubmit={async e => {
        e.preventDefault(); if (!saved || dirty || !ids.length || !due) return;
        setBusy(true); setError(''); setResult(null);
        try {
          const response = await api.applyKpiTemplate({ review_ids: ids, version: saved.version, due_on: due });
          if (!Array.isArray(response?.data?.applied) || !Array.isArray(response?.data?.skipped)) throw new Error('Application could not be confirmed. Refresh reviews before retrying. Existing KPIs will not be duplicated.');
          setResult(response.data); setSelection([]); await onUpdated();
        } catch (e) { setError(message(e)); } finally { setBusy(false); }
      }}>
        <h3>Apply standard KPIs</h3><p>Only empty, unsubmitted mid-year and year-end reviews are listed. Create employee reviews first if none are listed. Probation uses its separate assessment.</p>
        {dirty && <p>Save your template before applying it.</p>}
        <label style={{ display: 'grid', gap: 6, maxWidth: 300 }}>KPI due date<input required type="date" style={control} value={due} onChange={e => setDue(e.target.value)} /></label>
        <p><LeaveActionButton disabled={busy || !eligible.length} onClick={() => setSelection(eligible.slice(0, 100).map(r => r.id))}>Select all eligible reviews</LeaveActionButton> <LeaveActionButton disabled={busy} onClick={() => setSelection([])}>Clear selection</LeaveActionButton></p>
        {!eligible.length && <p>No empty reviews are available for this template.</p>}
        <div style={{ display: 'grid', gap: 8, maxHeight: 280, overflowY: 'auto', marginBottom: 16 }}>{eligible.map(r => <label key={r.id}><input type="checkbox" disabled={busy} checked={ids.includes(r.id)} onChange={e => setSelection(v => e.target.checked ? [...v, r.id].slice(0, 100) : v.filter(id => id !== r.id))} /> {r.employee_name || 'Employee'} — {r.cycle_type?.replaceAll('_', ' ')} {r.cycle_year}</label>)}</div>
        <LeaveActionButton type="submit" variant="primary" disabled={busy || dirty || !ids.length || !due}>{busy ? 'Working...' : `Apply KPIs to ${ids.length} reviews`}</LeaveActionButton>
        {result && <div role="status"><p>{result.applied.length} reviews updated; {result.skipped.length} skipped.</p><ul>{result.skipped.map(row => <li key={row.review_id}>{reviews.find(r => r.id === row.review_id)?.employee_name || 'Review'}: {row.reason}</li>)}</ul></div>}
      </form>
    </>}
  </details>;
}
