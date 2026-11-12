import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../services/api';
import './PerformanceV3.css';
import PeerReviewSelector from './PeerReviewSelector';

export const errorText = error => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'Unable to complete the action. Your input has been kept; please retry.';
const dateAfter = (start, days) => start ? new Date(new Date(`${start}T12:00:00Z`).getTime() + days * 86400000).toISOString().slice(0, 10) : 'Select a start date';

export function V3CycleDialog({ employees, cycles = [], questions = [], onClose, onCreated }) {
  const [selected, setSelected] = useState([]);
  const [existing, setExisting] = useState('');
  const [form, setForm] = useState({ cycle_type: 'Year_End', cycle_year: new Date().getFullYear(), starts_on: '', approval_reference: '', alignment_confirmed: false });
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const firstControl = useRef(null);
  useEffect(() => {
    const previous = document.activeElement; firstControl.current?.focus();
    return () => previous?.focus?.();
  }, []);
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }));
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      let id = existing;
      if (!id) { const response = await api.performanceV3Action('cycles', 'new', 'create', form); id = response.data.id; setExisting(id); }
      await api.performanceV3Action('cycles', id, 'open', { employee_ids: selected });
      await onCreated();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return <div className="performance-v3"><div className="pv-modal"><section role="dialog" aria-modal="true" aria-labelledby="pv-create-title" className="pv-dialog" onKeyDown={e => {
    if (e.key === 'Escape' && !busy) onClose();
    if (e.key === 'Tab') {
      const controls = [...e.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')];
      if (document.activeElement === (e.shiftKey ? controls[0] : controls[controls.length - 1])) {
        e.preventDefault(); (e.shiftKey ? controls[controls.length - 1] : controls[0])?.focus();
      }
    }
  }}>
    <h2 id="pv-create-title">Create and send performance reviews</h2><p>Select employees with approved KPIs and a saved line manager. The four-week cycle includes self-review, peer feedback, manager assessment and meetings.</p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={submit}><label>Cycle<select ref={firstControl} value={existing} onChange={e => setExisting(e.target.value)}><option value="">Create a new cycle</option>{cycles.filter(c => c.status !== 'Archived').map(c => <option key={c.id} value={c.id}>{c.cycle_type.replaceAll('_', ' ')} {c.cycle_year} · {c.starts_on}</option>)}{existing && !cycles.some(c => c.id === existing) && <option value={existing}>Prepared cycle — retry sending</option>}</select></label>
      {!existing && <><div className="pv-grid"><label>Review type<select value={form.cycle_type} onChange={e => set('cycle_type', e.target.value)}><option value="Year_End">Year-end</option><option value="Mid_Year">Mid-year</option></select></label><label>Year<input required type="number" min="2000" max="2100" value={form.cycle_year} onChange={e => set('cycle_year', Number(e.target.value))} /></label><label>Start date<input required type="date" value={form.starts_on} onChange={e => set('starts_on', e.target.value)} /></label></div>
        <p className="pv-note">Self and peer deadline: {dateAfter(form.starts_on, 6)}<br />Manager deadline: {dateAfter(form.starts_on, 13)}<br />Meetings and HR release by: {dateAfter(form.starts_on, 27)}<br />Scoring: KPIs 50% · Values 30% · Company NPS/CSAT 20%.</p>
        <label>MD/HR policy approval reference<input required value={form.approval_reference} onChange={e => set('approval_reference', e.target.value)} /></label>
        <details><summary>Alignment Survey questions</summary><ol>{questions.map(q => <li key={q.id}>{q.text}</li>)}</ol></details>
        <label><span><input type="checkbox" required checked={form.alignment_confirmed} onChange={e => set('alignment_confirmed', e.target.checked)} /> HR confirms the fixed scoring policy and the displayed Alignment Survey questions.</span></label></>}
      <label>Employees<select aria-label="Review employee" multiple required size={Math.min(8, Math.max(3, employees.length))} value={selected} onChange={e => setSelected([...e.target.selectedOptions].map(o => o.value))}>{employees.map(e => <option key={e.id} value={e.id}>{e.name || e.full_name} — {e.role || e.role_title}</option>)}</select></label>
      <p>Use Ctrl/Cmd to select several employees. MD reviews remain Board-administered. Probation reviews remain separate.</p>
      <button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" disabled={busy || !selected.length}>{busy ? 'Sending…' : 'Create and send reviews'}</button>
    </form></section></div></div>;
}

export default function PerformanceV3Panel({ user, onUpdated, createOpen, onCloseCreate, onOpenReview }) {
  const hr = ['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role);
  const [setup, setSetup] = useState(null); const [tasks, setTasks] = useState(null);
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const [employeeId, setEmployeeId] = useState(''); const [role, setRole] = useState(''); const [reason, setReason] = useState('');
  const [individual, setIndividual] = useState(null); const [roleChange, setRoleChange] = useState(false);
  const [peerId, setPeerId] = useState(new URLSearchParams(window.location.search).get('peer') || '');
  const [alignmentId, setAlignmentId] = useState(new URLSearchParams(window.location.search).get('alignment') || ''); const [answers, setAnswers] = useState({});
  const [cycleId, setCycleId] = useState(''); const [feedback, setFeedback] = useState({ nps: '', csat: '', source_reference: '', reason: '' });
  const [reviewId, setReviewId] = useState(''); const [reviewerIds, setReviewerIds] = useState([]); const [extend, setExtend] = useState(0); const [peerReason, setPeerReason] = useState('');
  const [report, setReport] = useState(null);
  const load = useCallback(async () => {
    try {
      const [own, admin] = await Promise.all([user?.employee_id ? api.getPerformanceV3Tasks() : Promise.resolve({ data: null }), hr ? api.getPerformanceV3Setup() : Promise.resolve({ data: null })]);
      setTasks(own.data); setSetup(admin.data);
    } catch (err) { setError(errorText(err)); }
  }, [hr, user?.employee_id]);
  useEffect(() => { load(); }, [load]);
  const perform = async action => { setBusy(true); setError(''); setMessage(''); try { await action(); setMessage('Saved successfully.'); await load(); await onUpdated(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const employee = setup?.employees.find(e => e.id === employeeId);
  const changeIndividual = (index, key, value) => setIndividual(old => ({ ...old, goals: old.goals.map((g, i) => i === index ? { ...g, [key]: value } : g) }));
  return <section className="performance-v3" aria-label="Performance review workflow">
    {error && <div role="alert">{error} <button onClick={load}>Retry loading</button></div>}{message && <p role="status">{message}</p>}
    {hr && !setup && !error && <p>Loading review preparation…</p>}
    {createOpen && hr && setup && <V3CycleDialog employees={setup.employees} cycles={setup.cycles} questions={tasks?.questions || setup.questions || []} onClose={onCloseCreate} onCreated={async () => { onCloseCreate(); await load(); await onUpdated(); }} />}
    {hr && setup && <>
      <details className="pv-card"><summary>1. Assign approved KPIs to employees</summary><p>Choose a published role. HR can make approved individual changes before the cycle locks the KPIs.</p>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('employees', employeeId, 'assign', { role_id: role, expected_version: employee?.assignment?.version || null, reason, role_change: roleChange, ...(individual ? { individual } : {}) })); }}>
          <div className="pv-grid"><label>Employee<select required value={employeeId} onChange={e => { setEmployeeId(e.target.value); setIndividual(null); setRole(''); }}><option value="">Choose employee</option>{setup.employees.map(e => <option key={e.id} value={e.id}>{e.name} — {e.assignment ? 'KPIs assigned' : 'Needs KPIs'}</option>)}</select></label>
          <label>Approved role<select required value={role} onChange={e => { setRole(e.target.value); setIndividual(null); }}><option value="">Choose published role</option>{setup.roles.filter(r => r.has_published_version).map(r => <option key={r.role_id} value={r.role_id}>{r.name}</option>)}</select></label></div>
          <label>Reason / approval reference<input required minLength={10} value={reason} onChange={e => setReason(e.target.value)} /></label>
          <label><span><input type="checkbox" checked={roleChange} onChange={e => setRoleChange(e.target.checked)} /> Approved role change during an open cycle (unsubmitted reviews only)</span></label>
          {employee?.assignment && role === employee.assignment.values.role_id && <button type="button" onClick={() => setIndividual(JSON.parse(JSON.stringify(employee.assignment.values)))}>Edit individual targets and weights</button>}
          {individual && <><label>Individual KPI approval reference<input required value={individual.approval_reference} onChange={e => setIndividual(old => ({ ...old, approval_reference: e.target.value }))} /></label>{individual.goals.map((g, i) => <fieldset key={g.id} className="pv-card"><legend>{g.objective}</legend><div className="pv-grid">{[['objective', 'Objective'], ['metric', 'Measurement'], ['target', 'Target description'], ['target_value', 'Numeric target'], ['weight', 'Weight %'], ['data_source', 'Data source'], ['owner', 'Owner']].map(([key, label]) => <label key={key}>{label}<input value={g[key] ?? ''} type={['weight', 'target_value'].includes(key) ? 'number' : 'text'} step="any" onChange={e => changeIndividual(i, key, ['weight', 'target_value'].includes(key) ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)} /></label>)}</div></fieldset>)}</>}
          <button className="primary" disabled={busy || !employeeId || !role}>Save employee KPIs</button>
        </form></details>
      <section className="pv-card"><h2>2. Review cycle tracker</h2><p>Use Create Review to send a cycle to selected employees. Open an employee review below to assess, arrange the meeting or release it.</p>
        <button onClick={load} disabled={busy}>Refresh tracker</button>
        {setup.reviews.length === 0 ? <p>No V3 reviews have been sent.</p> : setup.reviews.map(r => <details key={r.id}><summary>{r.employee_name} · {r.cycle_type.replaceAll('_', ' ')} {r.cycle_year} · {r.status.replaceAll('_', ' ')}</summary><p>Self: {r.self_due_on} · Manager: {r.manager_due_on} · Peer: {r.peer_due_on}</p><p>{r.peer_tasks.filter(t => t.status === 'Submitted').length} peer responses collected</p><ul>{r.peer_tasks.map(t => <li key={t.id}>{t.name}: {t.status} · {t.due_on}</li>)}</ul><button onClick={() => onOpenReview(r)}>Open review</button>{r.outcomes?.filter(o => o.status !== 'Completed').map(o => <p key={o.key}>{o.title} · {o.due_on}<button disabled={busy} onClick={() => { const notes = window.prompt('Completion notes'); if (notes) perform(() => api.performanceV3Action('reviews', r.id, 'followup', { expected_version: r.version, key: o.key, notes })); }}>Mark completed</button></p>)}</details>)}
      </section>
      <details className="pv-card"><summary>3. Peer assignments and company feedback</summary>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('reviews', reviewId, 'peers', { reviewer_ids: reviewerIds, extend_days: extend, reason: peerReason })); }}>
          <label>Employee review<select required value={reviewId} onChange={e => setReviewId(e.target.value)}><option value="">Choose review</option>{setup.reviews.filter(r => !r.scores_released).map(r => <option key={r.id} value={r.id}>{r.employee_name}</option>)}</select></label>
          <label>Add eligible reviewers<select multiple value={reviewerIds} onChange={e => setReviewerIds([...e.target.selectedOptions].map(o => o.value))}>{setup.reviewers.map(r => <option key={r.id} value={r.id}>{r.name} — {r.department}</option>)}</select></label>
          <label>Extend peer deadline<select value={extend} onChange={e => setExtend(Number(e.target.value))}><option value={0}>No extension</option>{[1, 2, 3].map(n => <option key={n} value={n}>{n} days after original deadline</option>)}</select></label>
          <label>Reason<input required minLength={10} value={peerReason} onChange={e => setPeerReason(e.target.value)} /></label><button disabled={busy}>Save peer collection</button>
        </form><hr />
        <label>Cycle<select value={cycleId} onChange={e => { setCycleId(e.target.value); setReport(null); }}><option value="">Choose cycle</option>{setup.cycles.map(c => <option key={c.id} value={c.id}>{c.cycle_type.replaceAll('_', ' ')} {c.cycle_year} · {c.status}</option>)}</select></label>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('cycles', cycleId, 'feedback', { ...feedback, nps: Number(feedback.nps), csat: Number(feedback.csat) })); }}><div className="pv-grid"><label>Verified company NPS<input required type="number" min="-100" max="100" step="any" value={feedback.nps} onChange={e => setFeedback(old => ({ ...old, nps: e.target.value }))} /></label><label>Verified company CSAT<input required type="number" min="1" max="5" step="any" value={feedback.csat} onChange={e => setFeedback(old => ({ ...old, csat: e.target.value }))} /></label></div><label>Verified source reference<input required value={feedback.source_reference} onChange={e => setFeedback(old => ({ ...old, source_reference: e.target.value }))} /></label><button disabled={busy || !cycleId}>Save company feedback</button></form>
        <label>Reason if correcting company feedback<input value={feedback.reason} onChange={e => setFeedback(old => ({ ...old, reason: e.target.value }))} /></label>
        <button disabled={busy || !cycleId} onClick={() => perform(async () => { const response = await api.getPerformanceV3AlignmentReport(cycleId); setReport(response.data); })}>View anonymous Alignment and talent density</button>{report && <p>Responses: {report.response_count} · Alignment: {report.score ?? 'Not enough responses'}{report.talent_density != null && ` · Talent density: ${report.talent_density}% (target 85%)`}</p>}
        <button disabled={busy || !cycleId} onClick={() => { const reason = window.prompt('Reason for archiving this unused cycle'); if (reason) perform(() => api.performanceV3Action('cycles', cycleId, 'archive', { reason })); }}>Archive unused cycle</button>
      </details>
    </>}
    {tasks && <section className="pv-card"><h2>My peer reviews and Alignment Survey</h2><p>Peer answers are confidential. Do not identify yourself or other reviewers in comments. Averages are shared only after the window closes and at least three peers respond.</p>
      {tasks.team_cycles?.map(c => <p key={c.id}>{c.title}<button disabled={busy} onClick={() => perform(async () => { const response = await api.getPerformanceV3AlignmentReport(c.id); setReport(response.data); })}>View my team’s anonymous Alignment score</button></p>)}
      {!hr && report && <p>Team responses: {report.response_count} · Team Alignment: {report.score ?? 'At least three responses are required'}{report.score != null && '%'}</p>}
      {tasks.peers.length === 0 && tasks.alignment.length === 0 && <p>No peer or Alignment tasks are assigned.</p>}
      {tasks.peers.map(t => <p key={t.id}>{t.employee_name} · Due {t.due_on} · {t.status}<button disabled={!t.can_submit} onClick={() => setPeerId(t.id)}>Complete peer review</button></p>)}
      {tasks.peers.some(t => t.status === 'Assigned') && <PeerReviewSelector key={peerId} initialTaskId={peerId} onSubmitted={async () => { await load(); await onUpdated(); }} />}
      {tasks.alignment.map(w => <p key={w.id}>{w.title} Alignment · Due {w.due_on}<button disabled={w.submitted} onClick={() => { setAlignmentId(w.id); setAnswers({}); }}>{w.submitted ? 'Submitted' : 'Complete Alignment Survey'}</button></p>)}
      {tasks.alignment.some(w => w.id === alignmentId && !w.submitted) && <form onSubmit={e => { e.preventDefault(); perform(async () => { await api.performanceV3Action('cycles', alignmentId, 'alignment', { answers }); setAlignmentId(''); }); }}>{tasks.questions.map(q => <label key={q.id}>{q.text}<select required value={answers[q.id] || ''} onChange={e => setAnswers(old => ({ ...old, [q.id]: Number(e.target.value) }))}><option value="">Choose score</option>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}</select></label>)}<button className="primary" disabled={busy}>Submit Alignment Survey</button></form>}
    </section>}
  </section>;
}
