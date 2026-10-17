import React, { useState } from 'react';
import * as api from '../services/api';

const field = { display: 'grid', gap: 5, marginBottom: 12 };
const button = { minHeight: 44, padding: '8px 14px', cursor: 'pointer' };

export function CycleConfiguration({ cycles, onUpdated }) {
  const [values, setValues] = useState({ cycle_type: 'Year_End', cycle_year: new Date().getFullYear(), starts_on: '', self_due_on: '', manager_due_on: '', policy: 'handbook_frd', approval_reference: '' });
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = (key, value) => setValues(previous => ({ ...previous, [key]: value }));
  return <details style={{ background: '#fff', padding: 20, marginBottom: 20 }}><summary>Configure review cycle (HR)</summary>
    <p role="note">Policy conflict: Handbook/FRD specify 50/30/20 with Client Feedback; the Developer Brief specifies 60/25/15 with Alignment. Record HR approval before using either for a new cycle. Historical scores stay unchanged.</p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await api.configureReviewCycle(values); await onUpdated(); } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Unable to configure the cycle.'); } finally { setBusy(false); } }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <label style={field}>Cycle<select value={values.cycle_type} onChange={e => change('cycle_type', e.target.value)}><option value="Mid_Year">Mid-year</option><option value="Year_End">Year-end</option></select></label>
        <label style={field}>Year<input required type="number" min="2000" max="2100" value={values.cycle_year} onChange={e => change('cycle_year', Number(e.target.value))} /></label>
        {[['starts_on', 'Cycle start'], ['self_due_on', 'Self-assessment deadline'], ['manager_due_on', 'Manager deadline']].map(([key, label]) => <label key={key} style={field}>{label}<input required type="date" value={values[key]} onChange={e => change(key, e.target.value)} /></label>)}
      </div>
      <p>Each cycle lasts four weeks. HR review is due on its final day.</p>
      <label style={field}>Approved policy<select value={values.policy} onChange={e => change('policy', e.target.value)}><option value="handbook_frd">Handbook / FRD: 50 / 30 / 20</option><option value="developer_brief">Developer Brief: 60 / 25 / 15</option></select></label>
      <label style={field}>HR approval reference<input required maxLength={300} value={values.approval_reference} onChange={e => change('approval_reference', e.target.value)} /></label>
      <label style={field}><span><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> HR has approved this policy and the meaning of Section C for this cycle.</span></label>
      <button style={button} disabled={busy || !confirmed}>Configure cycle</button>
    </form>
    <ul>{cycles.map(cycle => <li key={cycle.id}>{cycle.cycle_type?.replaceAll('_', ' ')} {cycle.cycle_year}: {cycle.starts_on} to {cycle.ends_on}</li>)}</ul>
  </details>;
}

export default function PerformanceWorkflow({ review, onUpdated }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [goal, setGoal] = useState({ objective: '', metric: '', target: '', due_on: '' });
  const [self, setSelf] = useState({ summary: review.self_assessment?.summary || '', achievements: review.self_assessment?.achievements || '', support_needed: review.self_assessment?.support_needed || '' });
  const [managerSummary, setManagerSummary] = useState('');
  const [scores, setScores] = useState({});
  const [hr, setHr] = useState({ section_b_score: '', section_c_score: '', evidence_reference: '', summary: '' });
  const [legacyReference, setLegacyReference] = useState('');
  const [progress, setProgress] = useState({});
  const [evidence, setEvidence] = useState({});
  const goals = review.section_a_kpis || [];
  const perform = async action => { setBusy(true); setError(''); try { await action(); await onUpdated(); } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'The assessment could not be saved.'); } finally { setBusy(false); } };
  if (review.workflow_version !== 1) return <section><p>Historical review. Existing scores are preserved; updates require an approved reconciliation process.</p>
    {error && <p role="alert">{error}</p>}
    {review.can_hr_review && ['Completed', 'Imported'].includes(review.status) && !review.scores_released && <form onSubmit={e => { e.preventDefault(); perform(() => api.submitReviewAssessment(review.id, 'legacy-release', { approval_reference: legacyReference })); }}>
      <label style={field}>Historical publication approval reference<input required value={legacyReference} onChange={e => setLegacyReference(e.target.value)} /></label>
      <button style={button} disabled={busy}>Release original historical scores</button></form>}
  </section>;
  return <section style={{ borderTop: '2px solid #FF353F', paddingTop: 16 }}>
    <h3>Review workflow</h3>
    <p>Self-assessment: {review.self_due_on || 'Awaiting HR'} · Manager: {review.manager_due_on || 'Awaiting HR'} · HR: {review.review_due_on || 'Awaiting HR'}</p>
    {!review.scores_released && <p>Final scores remain private until HR releases this review.</p>}
    {error && <p role="alert">{error}</p>}
    <h4>Agreed goals / KPIs / OKRs</h4>
    {goals.length === 0 && <p>No goals assigned. Your manager must agree measurable targets with you.</p>}
    {goals.map(item => <article key={item.id} style={{ border: '1px solid #ddd', padding: 12, marginBottom: 12 }}>
      <strong>{item.objective}</strong><p>{item.metric}: {item.target}</p><p>Due {item.due_on} · {item.progress}% · {item.status}</p>
      {review.can_update_goal_progress && item.status !== 'Completed' && <div>
        <label style={field}>Progress (%)<input type="number" min="0" max="100" value={progress[item.id] ?? item.progress} onChange={e => setProgress(previous => ({ ...previous, [item.id]: Number(e.target.value) }))} /></label>
        <label style={field}>Progress evidence<input value={evidence[item.id] || ''} onChange={e => setEvidence(previous => ({ ...previous, [item.id]: e.target.value }))} /></label>
        <button style={button} disabled={busy} onClick={() => perform(() => api.updateReviewGoals(review.id, { action: 'progress', goal_id: item.id, progress: progress[item.id] ?? item.progress, evidence: evidence[item.id] }))}>Save progress</button>
      </div>}
      {(review.can_manage || review.can_hr_review) && item.status === 'Pending_Review' && <button style={button} disabled={busy} onClick={() => perform(() => api.updateReviewGoals(review.id, { action: 'review', goal_id: item.id }))}>Verify goal completion</button>}
    </article>)}
    {(review.can_manage || review.can_hr_review) && ['Draft', 'Self_Draft'].includes(review.status) && !review.goals_acknowledged_at && <form onSubmit={e => { e.preventDefault(); perform(async () => { await api.updateReviewGoals(review.id, { action: 'assign', ...goal }); setGoal({ objective: '', metric: '', target: '', due_on: '' }); }); }}>
      <h4>Assign an agreed goal</h4>{[['objective','Objective'],['metric','Measurement'],['target','Target'],['due_on','Due date']].map(([key, label]) => <label key={key} style={field}>{label}<input required type={key === 'due_on' ? 'date' : 'text'} value={goal[key]} onChange={e => setGoal(previous => ({ ...previous, [key]: e.target.value }))} /></label>)}
      <button style={button} disabled={busy || goals.length >= 5}>Assign goal</button>
    </form>}
    {review.goals_acknowledged_at && <p>Goals acknowledged: {review.goals_acknowledged_at.slice(0, 10)}</p>}
    {review.can_self_assess && !review.goals_acknowledged_at && goals.length >= 3 && <button style={button} disabled={busy} onClick={() => perform(() => api.updateReviewGoals(review.id, { action: 'acknowledge' }))}>Acknowledge agreed goals</button>}
    {review.self_assessment && <div><h4>Employee self-assessment</h4><p>{review.self_assessment.summary}</p><p>{review.self_assessment.achievements}</p><p>{review.self_assessment.support_needed}</p></div>}
    {review.can_self_assess && <form onSubmit={e => { e.preventDefault(); perform(() => api.submitReviewAssessment(review.id, 'self', { ...self, submit: true })); }}>
      <h4>My self-assessment</h4>{[['summary','Summary'],['achievements','Achievements'],['support_needed','Support needed']].map(([key, label]) => <label key={key} style={field}>{label}<textarea required maxLength={4000} value={self[key]} onChange={e => setSelf(previous => ({ ...previous, [key]: e.target.value }))} /></label>)}
      <button style={button} type="button" disabled={busy} onClick={() => perform(() => api.submitReviewAssessment(review.id, 'self', { ...self, submit: false }))}>Save self-assessment draft</button>
      <button style={button} disabled={busy || goals.length < 3 || !review.goals_acknowledged_at}>Submit self-assessment</button>
    </form>}
    {review.can_manage && review.status === 'Self_Submitted' && <form onSubmit={e => { e.preventDefault(); perform(() => api.submitReviewAssessment(review.id, 'manager', { summary: managerSummary, kpi_scores: goals.map(item => ({ goal_id: item.id, score: Number(scores[item.id]?.score), evidence: scores[item.id]?.evidence })) })); }}>
      <h4>Manager assessment</h4><label style={field}>Assessment summary<textarea required value={managerSummary} onChange={e => setManagerSummary(e.target.value)} /></label>
      {goals.map(item => <div key={item.id}><strong>{item.objective}</strong><label style={field}>Score (1–3)<input required type="number" min="1" max="3" step="0.1" value={scores[item.id]?.score || ''} onChange={e => setScores(previous => ({ ...previous, [item.id]: { ...previous[item.id], score: e.target.value } }))} /></label><label style={field}>Evidence<textarea required value={scores[item.id]?.evidence || ''} onChange={e => setScores(previous => ({ ...previous, [item.id]: { ...previous[item.id], evidence: e.target.value } }))} /></label></div>)}
      <button style={button} disabled={busy}>Submit manager assessment</button>
    </form>}
    {review.manager_assessment && <div><h4>Manager assessment</h4><p>{review.manager_assessment.summary}</p></div>}
    {review.can_hr_review && review.status === 'Manager_Submitted' && <form onSubmit={e => { e.preventDefault(); perform(() => api.submitReviewAssessment(review.id, 'hr', { ...hr, section_b_score: Number(hr.section_b_score), section_c_score: Number(hr.section_c_score) })); }}>
      <h4>HR review</h4><p>Approved policy: {review.scoring_policy?.weights?.join(' / ')} · Section C: {review.scoring_policy?.section_c}. Use verified normalized evidence; do not infer missing feedback.</p>
      {[['section_b_score','Section B score'],['section_c_score','Section C score']].map(([key, label]) => <label key={key} style={field}>{label}<input required type="number" min="1" max="3" step="0.1" value={hr[key]} onChange={e => setHr(previous => ({ ...previous, [key]: e.target.value }))} /></label>)}
      {[['evidence_reference','Verified score-source reference'],['summary','Employee-facing HR summary']].map(([key, label]) => <label key={key} style={field}>{label}<textarea required value={hr[key]} onChange={e => setHr(previous => ({ ...previous, [key]: e.target.value }))} /></label>)}
      <button style={button} disabled={busy}>Approve HR review</button>
    </form>}
    {review.can_hr_review && review.status === 'HR_Reviewed' && <button style={button} disabled={busy} onClick={() => perform(() => api.submitReviewAssessment(review.id, 'release', {}))}>Release scores to employee</button>}
    {review.hr_summary && <p>{review.hr_summary}</p>}
  </section>;
}
