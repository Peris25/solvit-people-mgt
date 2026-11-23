import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../services/api';
import './PerformanceV3.css';
import PeerReviewSelector from './PeerReviewSelector';
import TalentDensityCard from './TalentDensityCard';

export const errorText = error => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'Unable to complete the action. Your input has been kept; please retry.';
const ALIGNMENT_PILLARS = ['Environment', 'Values Alignment', 'Rewards & Recognition'];
const ALIGNMENT_SCALE = ['Strongly Disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly Agree'];
const dateAfter = (start, days) => start ? new Date(new Date(`${start}T12:00:00Z`).getTime() + days * 86400000).toISOString().slice(0, 10) : 'Select a start date';

export function V3CycleDialog({ employees, cycles = [], questions = [], onClose, onCreated, onArchived }) {
  const [selected, setSelected] = useState([]);
  const [receipt, setReceipt] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteReason, setDeleteReason] = useState('');
  const [archived, setArchived] = useState(null);
  const receiptControl = useRef(null);
  const [existing, setExisting] = useState('');
  const [form, setForm] = useState({ cycle_type: 'Year_End', cycle_year: new Date().getFullYear(), starts_on: '', approval_reference: '', alignment_confirmed: false });
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const firstControl = useRef(null);
  useEffect(() => {
    const previous = document.activeElement; firstControl.current?.focus();
    return () => previous?.focus?.();
  }, []);
  useEffect(() => { if (receipt || archived) receiptControl.current?.focus(); }, [receipt, archived]);
  const chosenCycle = cycles.find(cycle => cycle.id === existing);
  const earlierCycle = !!chosenCycle && chosenCycle.workflow_version !== 3;
  const readyEmployees = employees.filter(employee => employee.review_ready !== false);
  const blockedEmployees = employees.filter(employee => employee.review_ready === false);
  const set = (key, value) => setForm(old => ({ ...old, [key]: value }));
  const submit = async event => {
    event.preventDefault(); if (busy || confirmDelete || archived || receipt || earlierCycle) return;
    if (selected.some(id => blockedEmployees.some(employee => employee.id === id))) { setError('Correct the employee details listed below before sending. No reviews sent.'); return; }
    setBusy(true); setError('');
    try {
      let id = existing;
      if (!id) { const response = await api.performanceV3Action('cycles', 'new', 'create', form); id = response?.data?.id; if (!id) throw new Error('SEND_UNCONFIRMED'); setExisting(id); }
      const response = await api.performanceV3Action('cycles', id, 'open', { employee_ids: selected });
      if (response?.data?.id !== id || response?.data?.status !== 'Open') throw new Error('SEND_UNCONFIRMED');
      setReceipt({ count: selected.length, cycleId: id });
    } catch (err) { setError(err?.message === 'SEND_UNCONFIRMED' ? 'Sending could not be confirmed. Check the review cycle tracker before trying again. Your selection has been kept.' : errorText(err)); } finally { setBusy(false); }
  };
  const finishArchive = () => onArchived ? onArchived(archived) : onClose();
  const deleteUnused = async () => {
    if (!existing || busy || deleteReason.trim().length < 10) return;
    setBusy(true); setError('');
    try {
      const response = await api.performanceV3Action('cycles', existing, 'archive', { reason: deleteReason.trim() });
      if (response?.data?.status !== 'Archived' || response?.data?.id !== existing) throw new Error('ARCHIVE_UNCONFIRMED');
      setArchived({ cycleId: existing });
    } catch (err) { setError(err?.message === 'ARCHIVE_UNCONFIRMED' ? 'Cycle deletion could not be confirmed. Refresh the tracker before trying again.' : errorText(err)); }
    finally { setBusy(false); }
  };
  return <div className="performance-v3"><div className="pv-modal"><section role="dialog" aria-modal="true" aria-labelledby="pv-create-title" className="pv-dialog" onKeyDown={e => {
    if (e.key === 'Escape' && !busy) { if (archived) finishArchive(); else if (receipt) onCreated(receipt); else onClose(); }
    if (e.key === 'Tab') {
      const controls = [...e.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')];
      if (!controls.includes(document.activeElement) || document.activeElement === (e.shiftKey ? controls[0] : controls[controls.length - 1])) {
        e.preventDefault(); (e.shiftKey ? controls[controls.length - 1] : controls[0])?.focus();
      }
    }
  }}>
    <h2 id="pv-create-title">{archived ? 'Unused cycle deleted' : receipt ? 'Review requests confirmed' : 'Create and send performance reviews'}</h2>
    {archived && <div role="status" tabIndex={-1} ref={receiptControl}><p>The unused cycle has been removed from active use. Its audit history is retained.</p><button type="button" className="primary" onClick={finishArchive}>Done</button></div>}
    {receipt && <div role="status" tabIndex={-1} ref={receiptControl}><p><strong>Reviews are available for {receipt.count} selected {receipt.count === 1 ? 'employee' : 'employees'}.</strong></p><p>Follow their progress in the review cycle tracker. Email delivery is handled by the configured notification service.</p><button type="button" className="primary" onClick={() => onCreated(receipt)}>Done - view tracker</button></div>}
    {!receipt && !archived && <><p>Select employees with approved KPIs and a saved line manager. The four-week cycle includes self-review, peer feedback, manager assessment and meetings.</p>
    <p className="pv-note">Notifications are queued when you click Create and send reviews. A future start date does not delay sending. To notify staff on Monday morning, complete this action then.</p>
    {error && <p role="alert" style={{whiteSpace:'pre-line'}}>{error}</p>}
    <form onSubmit={submit}><label>Cycle<select ref={firstControl} disabled={busy || confirmDelete} value={existing} onChange={e => { setExisting(e.target.value); setConfirmDelete(false); setDeleteReason(''); }}><option value="">Create a new cycle</option>{cycles.filter(c => c.status !== 'Archived').map(c => <option key={c.id} value={c.id}>{c.cycle_type.replaceAll('_', ' ')} {c.cycle_year} · {c.starts_on}{c.workflow_version !== 3 ? ' - Earlier setup (manage only)' : ''}</option>)}{existing && !cycles.some(c => c.id === existing) && <option value={existing}>Prepared cycle — retry sending</option>}</select></label>
      {earlierCycle && <p role="note">This is an earlier cycle setup. It can be deleted here only if it has no review records or responses. Sending through this popup requires a new-workflow cycle.</p>}
      {existing && <><button type="button" disabled={busy || confirmDelete} onClick={() => { setConfirmDelete(true); setError(''); }}>Delete unused cycle</button>
        {confirmDelete && <section className="pv-card" aria-label="Delete cycle confirmation"><h3>Delete this unused cycle?</h3><p><strong>{(chosenCycle?.cycle_type || form.cycle_type).replaceAll('_', ' ')} {chosenCycle?.cycle_year || form.cycle_year}</strong><br />Start: {chosenCycle?.starts_on || form.starts_on}<br />End: {chosenCycle?.ends_on || dateAfter(form.starts_on,27)}</p><p>Only a cycle with no assessment work can be deleted. Unused review requests will close and the audit history will be retained. Emails already processed may still arrive.</p><label>Reason for deleting this cycle<textarea aria-label="Cycle deletion reason" disabled={busy} minLength={10} maxLength={1500} value={deleteReason} onChange={event => setDeleteReason(event.target.value)} /></label><button type="button" disabled={busy} onClick={() => setConfirmDelete(false)}>Keep cycle</button><button type="button" disabled={busy || deleteReason.trim().length < 10} onClick={deleteUnused}>{busy ? 'Deleting...' : 'Confirm delete unused cycle'}</button></section>}</>}
      {!existing && <><div className="pv-grid"><label>Review type<select disabled={busy} value={form.cycle_type} onChange={e => set('cycle_type', e.target.value)}><option value="Year_End">Year-end</option><option value="Mid_Year">Mid-year</option></select></label><label>Year<input disabled={busy} required type="number" min="2000" max="2100" value={form.cycle_year} onChange={e => set('cycle_year', Number(e.target.value))} /></label><label>Start date<input disabled={busy} required type="date" value={form.starts_on} onChange={e => set('starts_on', e.target.value)} /></label></div>
        <p className="pv-note">Self and peer deadline: {dateAfter(form.starts_on, 6)}<br />Manager deadline: {dateAfter(form.starts_on, 13)}<br />Meetings and HR release by: {dateAfter(form.starts_on, 27)}<br />Scoring: KPIs 50% · Values 30% · Company NPS/CSAT 20%.</p>
        <label>MD/HR policy approval reference<input disabled={busy} required value={form.approval_reference} onChange={e => set('approval_reference', e.target.value)} /></label>
        <details><summary>Alignment Survey questions</summary><p>1 = Strongly Disagree; 2 = Disagree; 3 = Neutral; 4 = Agree; 5 = Strongly Agree.</p>{ALIGNMENT_PILLARS.map((title, index) => <section key={title} aria-label={title}><h3>{title}</h3><ol>{questions.filter(q => q.pillar === index + 1).map(q => <li key={q.id}>{q.text}</li>)}</ol></section>)}</details>
        <label><span><input disabled={busy} type="checkbox" required checked={form.alignment_confirmed} onChange={e => set('alignment_confirmed', e.target.checked)} /> HR confirms the fixed scoring policy and the displayed Alignment Survey questions.</span></label></>}
      {!!blockedEmployees.length && <section className="pv-card" aria-label="Employee details to correct"><h3>{blockedEmployees.length} employees not included in the Annual cycle</h3><p>Employees in onboarding or probation use Create probation review. For other listed issues, correct the KPI assignment or reporting line before sending.</p><ul>{blockedEmployees.map(employee => <li key={employee.id}><strong>{employee.name || employee.full_name}</strong><ul>{(employee.review_issues || []).map((issue,index) => <li key={index}>{issue}</li>)}</ul></li>)}</ul></section>}
      <div style={{display:'flex',gap:10,flexWrap:'wrap',marginBottom:10}}><button type="button" disabled={busy || !readyEmployees.length} onClick={() => setSelected(readyEmployees.map(employee => employee.id))}>{blockedEmployees.length ? 'Select all ready employees' : 'Select all listed employees'}</button><button type="button" disabled={busy || !selected.length} onClick={() => setSelected([])}>Clear selection</button></div>
      <p role="status">{selected.length} of {employees.length} employees selected. {readyEmployees.length} ready to send{blockedEmployees.length ? `; ${blockedEmployees.length} need corrections` : ''}.</p>
      <fieldset className="pv-employee-picker" disabled={busy}><legend>Employees</legend><div className="pv-employee-options">{employees.map(employee => <label className="pv-employee-option" key={employee.id}><input type="checkbox" value={employee.id} checked={selected.includes(employee.id)} disabled={employee.review_ready === false} onChange={event => { const checked = event.target.checked; setSelected(current => checked ? [...new Set([...current, employee.id])] : current.filter(id => id !== employee.id)); }} /><span><strong>{employee.name || employee.full_name}</strong><small>{employee.role || employee.role_title}{employee.employment_status ? ` · Status: ${employee.employment_status}` : ''}{employee.expected_kpi_scope ? ` · ${employee.expected_kpi_scope} KPIs` : ''}{employee.review_ready === false ? employee.expected_kpi_scope === 'Probation' ? ' · Use probation review' : ' · Needs corrections' : ''}</small></span></label>)}</div></fieldset>
      <p>Tick employees to select them; untick to remove them. MD reviews remain Board-administered. Probation reviews remain separate.</p>
      <button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" disabled={busy || confirmDelete || earlierCycle || !selected.length}>{busy ? 'Sending…' : 'Create and send reviews'}</button>
    </form></>}</section></div></div>;
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
    {createOpen && hr && setup && <V3CycleDialog employees={setup.employees} cycles={setup.cycles} questions={tasks?.questions || setup.questions || []} onClose={onCloseCreate} onCreated={async receipt => { setMessage(`Review requests confirmed for ${receipt.count} selected employees.`); onCloseCreate(); await load(); await onUpdated(); }} onArchived={async () => { setMessage('Unused cycle deleted. Audit history retained.'); onCloseCreate(); await load(); await onUpdated(); }} />}
    {hr && setup && <>
      <details className="pv-card"><summary>1. Assign approved KPIs to employees</summary><p>Choose a published role. HR can make approved individual changes before the cycle locks the KPIs.</p>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('employees', employeeId, 'assign', { role_id: role, expected_version: employee?.assignment?.version || null, reason, role_change: roleChange, ...(individual ? { individual } : {}) })); }}>
          <div className="pv-grid"><label>Employee<select required value={employeeId} onChange={e => { setEmployeeId(e.target.value); setIndividual(null); setRole(setup.employees.find(employee => employee.id === e.target.value)?.assignment?.values?.role_id || ''); }}><option value="">Choose employee</option>{setup.employees.map(e => <option key={e.id} value={e.id}>{e.name} — {e.review_ready === true ? 'Ready to send' : e.review_ready === false ? 'Needs corrections' : e.assignment ? 'KPIs assigned' : 'Needs KPIs'}</option>)}</select></label>
          <label>Approved role<select required value={role} onChange={e => { setRole(e.target.value); setIndividual(null); }}><option value="">Choose published role</option>{setup.roles.filter(r => r.has_published_version).map(r => <option key={r.role_id} value={r.role_id}>{r.name}</option>)}</select></label></div>
          {employee && <p role="note">Employment status: {employee.employment_status || 'Not recorded'} · Onboarding: {employee.onboarding_status || 'Not recorded'} · KPI scope: {employee.expected_kpi_scope || employee.assignment?.values?.scope || 'Not recorded'}. Scope follows the employee status; the approved role supplies the KPI targets and weights.</p>}
          {employee?.review_issues?.length > 0 && <div role="note"><strong>Annual review eligibility</strong><ul>{employee.review_issues.map((issue,index) => <li key={index}>{issue}</li>)}</ul></div>}
          <label>Reason / approval reference<input required minLength={10} value={reason} onChange={e => setReason(e.target.value)} /></label>
          <label><span><input type="checkbox" checked={roleChange} onChange={e => setRoleChange(e.target.checked)} /> Approved role change during an open cycle (unsubmitted reviews only)</span></label>
          {employee?.assignment && role === employee.assignment.values.role_id && <button type="button" onClick={() => setIndividual(JSON.parse(JSON.stringify(employee.assignment.values)))}>Edit individual targets and weights</button>}
          {individual && <><label>Individual KPI approval reference<input required value={individual.approval_reference} onChange={e => setIndividual(old => ({ ...old, approval_reference: e.target.value }))} /></label>{individual.goals.map((g, i) => <fieldset key={g.id} className="pv-card"><legend>{g.objective}</legend><div className="pv-grid">{[['objective', 'Objective'], ['metric', 'Measurement'], ['target', 'Target description'], ['target_value', 'Numeric target'], ['weight', 'Weight %'], ['data_source', 'Data source'], ['owner', 'Owner']].map(([key, label]) => <label key={key}>{label}<input value={g[key] ?? ''} type={['weight', 'target_value'].includes(key) ? 'number' : 'text'} step="any" onChange={e => changeIndividual(i, key, ['weight', 'target_value'].includes(key) ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)} /></label>)}</div></fieldset>)}</>}
          <button className="primary" disabled={busy || !employeeId || !role}>Save employee KPIs</button>
        </form></details>
      <section className="pv-card"><h2>2. Review cycle tracker</h2><p>Use Create Review to send a cycle to selected employees. Open an employee review below to assess, arrange the meeting or release it.</p>
        <button onClick={load} disabled={busy}>Refresh tracker</button>
        <section aria-label="Anonymous peer review progress"><h3>Peer review progress</h3><p>Counts only. Minimums: 3 received, 5 colleagues chosen and 5 reviews submitted. No reviewer names, scores or comments are shown.</p>
          <label>Progress cycle<select value={cycleId} onChange={e => setCycleId(e.target.value)}><option value="">All cycles</option>{setup.cycles.filter(c => c.workflow_version === 3 && !['Archived', 'Cancelled'].includes(c.status)).map(c => <option key={c.id} value={c.id}>{c.cycle_type.replaceAll('_', ' ')} {c.cycle_year}</option>)}</select></label>
          <div className="pv-manager-table-wrap"><table className="pv-manager-table"><thead><tr>{['Employee', 'Cycle', 'Received', 'Chosen to review', 'Submitted'].map(heading => <th scope="col" key={heading}>{heading}</th>)}</tr></thead><tbody>{(setup.peer_progress || []).filter(row => !cycleId || row.cycle_id === cycleId).map(row => <tr key={`${row.cycle_id}-${row.employee_id}`}><th scope="row">{row.employee_name}</th><td>{setup.cycles.find(c => c.id === row.cycle_id)?.cycle_type.replaceAll('_', ' ')} {setup.cycles.find(c => c.id === row.cycle_id)?.cycle_year}</td>{[['received', 3], ['chosen', 5], ['submitted', 5]].map(([key, minimum]) => <td key={key}>{row[key]}{row[`below_${key}_minimum`] && <small className="pv-score-gap">Below {minimum}</small>}</td>)}</tr>)}</tbody></table></div>
          {!(setup.peer_progress || []).length && <p>Peer progress will appear when a cycle is configured.</p>}
        </section>
        {setup.reviews.length === 0 ? <p>No V3 reviews have been sent.</p> : setup.reviews.map(r => <details key={r.id}><summary>{r.employee_name} · {r.cycle_type.replaceAll('_', ' ')} {r.cycle_year} · {r.status.replaceAll('_', ' ')}</summary><p>Self: {r.self_due_on} · Manager: {r.manager_due_on} · Peer: {r.peer_due_on}</p><button onClick={() => onOpenReview(r)}>Open review</button>{r.outcomes?.filter(o => o.status !== 'Completed').map(o => <p key={o.key}>{o.title} · {o.due_on}<button disabled={busy} onClick={() => { const notes = window.prompt('Completion notes'); if (notes) perform(() => api.performanceV3Action('reviews', r.id, 'followup', { expected_version: r.version, key: o.key, notes })); }}>Mark completed</button></p>)}</details>)}
      </section>
      <details className="pv-card"><summary>3. Peer assignments and company feedback</summary>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('reviews', reviewId, 'peers', { reviewer_ids: reviewerIds, extend_days: extend, reason: peerReason })); }}>
          <label>Employee review<select required value={reviewId} onChange={e => setReviewId(e.target.value)}><option value="">Choose review</option>{setup.reviews.filter(r => !r.scores_released).map(r => <option key={r.id} value={r.id}>{r.employee_name}</option>)}</select></label>
          <label>Add eligible reviewers<select multiple value={reviewerIds} onChange={e => setReviewerIds([...e.target.selectedOptions].map(o => o.value))}>{setup.reviewers.map(r => <option key={r.id} value={r.id}>{r.name} — {r.department}</option>)}</select></label>
          <label>Extend peer deadline<select value={extend} onChange={e => setExtend(Number(e.target.value))}><option value={0}>No extension</option>{[1, 2, 3].map(n => <option key={n} value={n}>{n} days after original deadline</option>)}</select></label>
          <label>Reason<input required minLength={10} value={peerReason} onChange={e => setPeerReason(e.target.value)} /></label><button disabled={busy}>Save peer collection</button>
        </form><hr />
        <label>Cycle<select value={cycleId} onChange={e => { setCycleId(e.target.value); setReport(null); }}><option value="">Choose cycle</option>{setup.cycles.filter(c => c.workflow_version === 3 && !['Archived', 'Cancelled'].includes(c.status)).map(c => <option key={c.id} value={c.id}>{c.cycle_type.replaceAll('_', ' ')} {c.cycle_year} · {c.status}</option>)}</select></label>
        <form onSubmit={e => { e.preventDefault(); perform(() => api.performanceV3Action('cycles', cycleId, 'feedback', { ...feedback, nps: Number(feedback.nps), csat: Number(feedback.csat) })); }}><div className="pv-grid"><label>Verified company NPS<input required type="number" min="-100" max="100" step="any" value={feedback.nps} onChange={e => setFeedback(old => ({ ...old, nps: e.target.value }))} /></label><label>Verified company CSAT<input required type="number" min="1" max="5" step="any" value={feedback.csat} onChange={e => setFeedback(old => ({ ...old, csat: e.target.value }))} /></label></div><label>Verified source reference<input required value={feedback.source_reference} onChange={e => setFeedback(old => ({ ...old, source_reference: e.target.value }))} /></label><button disabled={busy || !cycleId}>Save company feedback</button></form>
        <label>Reason if correcting company feedback<input value={feedback.reason} onChange={e => setFeedback(old => ({ ...old, reason: e.target.value }))} /></label>
        <button disabled={busy || !cycleId} onClick={() => perform(async () => { const response = await api.getPerformanceV3AlignmentReport(cycleId); setReport(response.data); })}>View anonymous Alignment and talent density</button>{report && <><p>Responses: {report.response_count} · Alignment: {report.score ?? 'Not enough responses'}</p><TalentDensityCard data={{ score_pct: report.talent_density, target_pct: report.target ?? 85, components: report.components || { alignment_survey_pct: report.score } }} /></>}
        <button disabled={busy || !cycleId} onClick={() => { const reason = window.prompt('Reason for archiving this unused cycle'); if (reason) perform(() => api.performanceV3Action('cycles', cycleId, 'archive', { reason })); }}>Archive unused cycle</button>
      </details>
    </>}
    {tasks && <section className="pv-card"><h2>My peer reviews and Alignment Survey</h2><p>Peer answers are confidential. Do not identify yourself or other reviewers in comments. Averages are shared only after the window closes and at least three peers respond.</p>
      {tasks.team_cycles?.map(c => <p key={c.id}>{c.title}<button disabled={busy} onClick={() => perform(async () => { const response = await api.getPerformanceV3AlignmentReport(c.id); setReport(response.data); })}>View my team’s anonymous Alignment score</button></p>)}
      {!hr && report && <p>Team responses: {report.response_count} · Team Alignment: {report.score ?? 'At least three responses are required'}{report.score != null && '%'}</p>}
      {tasks.peers.length === 0 && !tasks.peer_choices?.length && tasks.alignment.length === 0 && <p>No peer or Alignment tasks are assigned.</p>}
      {tasks.peers.map(t => <p key={t.id}>{t.employee_name} · Due {t.due_on} · {t.status}<button disabled={!t.can_submit} onClick={() => setPeerId(t.id)}>Complete peer review</button></p>)}
      {(tasks.peer_choices?.length > 0 || tasks.peers.length > 0) && <PeerReviewSelector key={peerId} initialTaskId={peerId} onSubmitted={async () => { await load(); await onUpdated(); }} />}
      {tasks.alignment.map(w => <p key={w.id}>{w.title} Alignment · Due {w.due_on}<button disabled={w.submitted} onClick={() => { setAlignmentId(w.id); setAnswers({}); }}>{w.submitted ? 'Submitted' : 'Complete Alignment Survey'}</button></p>)}
      {tasks.alignment.some(w => w.id === alignmentId && !w.submitted) && <form onSubmit={e => { e.preventDefault(); perform(async () => { await api.performanceV3Action('cycles', alignmentId, 'alignment', { answers }); setAlignmentId(''); }); }}>{ALIGNMENT_PILLARS.map((title, index) => <fieldset key={title}><legend>{title}</legend>{tasks.questions.filter(q => q.pillar === index + 1).map(q => <label key={q.id}>{q.text}<select required value={answers[q.id] || ''} onChange={e => setAnswers(old => ({ ...old, [q.id]: Number(e.target.value) }))}><option value="">Choose score</option>{ALIGNMENT_SCALE.map((label, i) => <option key={label} value={i + 1}>{i + 1} - {label}</option>)}</select></label>)}</fieldset>)}<button className="primary" disabled={busy}>Submit Alignment Survey</button></form>}
    </section>}
  </section>;
}
