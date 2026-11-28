import ActionButton from './ActionButton';
import React, { useState } from 'react';
import * as api from '../services/api';
import { errorText } from './PerformanceV3Panel';
import './PerformanceV3.css';

const VALUES = ['Integrity', 'Hard Work & Ownership', 'Teamwork & Decency', 'Solution Orientation', 'Timeliness'];
const KPI_SCORES = [1, 1.5, 2, 2.5, 3];
const scoreText = (value, places = 1) => value != null && value !== '' && Number.isFinite(Number(value)) ? Number(value).toFixed(places) : 'Not available';
const gapText = value => value != null && Number.isFinite(Number(value)) ? `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(1)}` : 'Not available';
const displayActual = value => value === true ? 'Done' : value === false ? 'Not done' : value ?? 'Not provided';
const managerAverage = (goals, entries, groups) => {
  if (!goals.length || goals.some(goal => !KPI_SCORES.includes(entries[goal.id]?.score))) return null;
  const weighted = rows => rows.reduce((sum, goal) => sum + Number(goal.weight), 0) === 100
    ? rows.reduce((sum, goal) => sum + entries[goal.id].score * Number(goal.weight), 0) / 100 : null;
  if (!groups || !Object.keys(groups).length) return weighted(goals);
  if (Object.values(groups).reduce((sum, weight) => sum + Number(weight), 0) !== 100 || goals.some(goal => !(goal.group in groups))) return null;
  let total = 0;
  for (const [group, weight] of Object.entries(groups)) {
    const score = weighted(goals.filter(goal => goal.group === group));
    if (score === null) return null;
    total += score * Number(weight) / 100;
  }
  return total;
};
const localTime = value => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '';

function ActualInput({ goal, value, onChange, label }) {
  return <label>{label}{goal.direction === 'Binary' ? <select value={value === undefined ? '' : String(value)} onChange={e => onChange(e.target.value === '' ? undefined : e.target.value === 'true')}><option value="">Choose</option><option value="true">Done</option><option value="false">Not done</option></select> :
    <input type="number" step="any" min={goal.direction === 'Rated' ? 1 : 0} max={goal.direction === 'Rated' ? 3 : undefined} value={value ?? ''} onChange={e => onChange(e.target.value === '' ? undefined : Number(e.target.value))} />}</label>;
}

export default function PerformanceV3Review({ review, onUpdated }) {
  const [self, setSelf] = useState({ actuals: review.self_assessment?.actuals || {}, values: VALUES.map((_, i) => review.self_assessment?.values?.[i] || { score: '', example: '' }), accomplishments: [0, 1, 2].map(i => review.self_assessment?.accomplishments?.[i] || ''), challenge: review.self_assessment?.challenge || '', do_differently: review.self_assessment?.do_differently || '', support: review.self_assessment?.support || '' });
  const [actuals, setActuals] = useState(review.manager_assessment?.actuals || Object.fromEntries((review.section_a_kpis || []).map(g => [g.id, { actual: review.self_assessment?.actuals?.[g.id]?.actual, comment: '' }])));
  const [managerScores, setManagerScores] = useState(Object.fromEntries((review.section_a_kpis || []).map(goal => [goal.id, { score: review.manager_assessment?.actuals?.[goal.id]?.score, comment: review.manager_assessment?.actuals?.[goal.id]?.comment || '' }])));
  const sectionAPreview = managerAverage(review.section_a_kpis || [], managerScores, review.group_weights);
  const [summary, setSummary] = useState(''); const [notes, setNotes] = useState(''); const [dispute, setDispute] = useState('');
  const [meeting, setMeeting] = useState({ scheduled_at: localTime(review.review_meeting?.scheduled_at || review.meeting_proposal?.scheduled_at), location: review.review_meeting?.location || review.meeting_proposal?.location || '' });
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const [dateOptions, setDateOptions] = useState(null);
  const act = async (action, data) => { setBusy(true); setError(''); setMessage(''); try { const response = await api.performanceV3Action('reviews', review.id, action, { expected_version: review.version, ...data }); if (response?.data?.id !== review.id) throw new Error('Save not confirmed'); setMessage('Saved successfully.'); await onUpdated(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const updateActual = (id, key, value) => setSelf(old => ({ ...old, actuals: { ...old.actuals, [id]: { ...old.actuals[id], [key]: value } } }));
  const downloadEvidence = async id => {
    try {
      const response = await api.downloadEmployeeDocument(id);
      const url = URL.createObjectURL(response.data); const link = document.createElement('a');
      link.href = url; link.download = 'performance-evidence'; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    } catch (err) { setError(errorText(err)); }
  };
  return <section className="performance-v3" aria-label="V3 performance assessment">
    <p className="pv-note">Self-review by {review.self_due_on} · Manager by {review.manager_due_on} · Meetings/release by {review.review_due_on}. Final scoring is calculated automatically using 50% KPIs, 30% Values and 20% company feedback.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {review.kpi_revision_note&&<p className="pv-note" role="note">{review.kpi_revision_note}</p>}
    {!!review.kpi_draft_revisions?.length&&<details className="pv-card"><summary>Previous KPI draft entries</summary><p>These entries are retained for reference. They do not contribute to the updated review score.</p>{review.kpi_draft_revisions.map((revision,index)=><section key={index}><h3>KPI update · {new Date(revision.recorded_at).toLocaleDateString('en-GB')}</h3><p>{revision.reason}</p>{(revision.goals||[]).map(goal=>{const previous=revision.actuals?.[goal.id];return previous&&<div key={goal.id}><strong>{goal.objective}</strong><p>Previous actual: {displayActual(previous.actual)} · Previous self-score: {previous.self_score??'Not provided'}</p>{typeof previous.evidence==='string'&&<p>{previous.evidence}</p>}</div>;})}</section>)}</details>}
    {review.can_self_assess && <form onSubmit={e => e.preventDefault()}><h2>My self-review</h2>
      <h3>Section A · KPIs (50%)</h3><p>Measurement, target and weight are set for your role and are read-only. Enter your actual result and select your self-score for each KPI. 1.0 is best; 3.0 is lowest.</p>
      <p className="pv-note" id="self-kpi-score-guide">Self-score guide: {"1.0 = met or beat target \u00b7 1.5 \u2248 90% \u00b7 2.0 \u2248 80% \u00b7 2.5 \u2248 70% \u00b7 3.0 = 60% or less"}</p>
      <div className="pv-card pv-manager-table-wrap"><table className="pv-manager-table pv-self-kpi-table"><thead><tr>{['KPI / How it is measured', 'Target', 'Weight', 'My actual', 'Self-score'].map(heading => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{(review.section_a_kpis || []).map(goal => <tr key={goal.id}><th scope="row">{goal.objective}<small>{goal.metric || 'Measurement not specified'}</small></th><td>{goal.target ?? 'Not specified'}</td><td>{goal.weight}%</td><td><ActualInput goal={goal} label={<span className="pv-visually-hidden">My actual for {goal.objective}</span>} value={self.actuals[goal.id]?.actual} onChange={value => updateActual(goal.id, 'actual', value)} /></td><td><label><span className="pv-visually-hidden">Self-score for {goal.objective}</span><select aria-describedby="self-kpi-score-guide" disabled={busy} value={self.actuals[goal.id]?.self_score ?? ''} onChange={event => updateActual(goal.id, 'self_score', event.target.value === '' ? undefined : Number(event.target.value))}><option value="">Choose</option>{KPI_SCORES.map(score => <option key={score} value={score}>{score.toFixed(1)}</option>)}</select></label></td></tr>)}</tbody></table></div>
      <section className="pv-card" aria-labelledby="self-values-heading">
        <h3 id="self-values-heading">Section B · Values: my self-assessment</h3>
        <p id="self-values-guidance">Score yourself 0–10 on each value (10 = exemplary), with one specific example from this year. Only your colleagues’ 360° average counts towards your score; your self-score is compared with it.</p>
        <div className="pv-self-values-grid">{VALUES.map((name, i) => <div className="pv-self-value-card" key={name}>
          <div className="pv-self-value-heading"><label htmlFor={`self-value-score-${i}`}>{name}<span className="pv-visually-hidden">: self-score (0–10)</span></label><input id={`self-value-score-${i}`} aria-describedby="self-values-guidance" type="number" min="0" max="10" step="any" disabled={busy} value={self.values[i]?.score ?? ''} onChange={e => setSelf(old => ({ ...old, values: old.values.map((v, n) => n === i ? { ...v, score: e.target.value === '' ? '' : Number(e.target.value) } : v) }))} /></div>
          <label className="pv-visually-hidden" htmlFor={`self-value-example-${i}`}>Specific example for {name}</label><textarea id={`self-value-example-${i}`} placeholder="One specific example from this year" disabled={busy} value={self.values[i]?.example || ''} onChange={e => setSelf(old => ({ ...old, values: old.values.map((v, n) => n === i ? { ...v, example: e.target.value } : v) }))} />
        </div>)}</div>
      </section>
      <h3>Reflection questions</h3>
      {['First accomplishment', 'Second accomplishment', 'Third accomplishment'].map((label, i) => <label key={label}>{label}<textarea value={self.accomplishments[i] || ''} onChange={e => setSelf(old => ({ ...old, accomplishments: old.accomplishments.map((v, n) => i === n ? e.target.value : v) }))} /></label>)}
      {[['challenge', 'Biggest challenge'], ['do_differently', 'What I would do differently'], ['support', 'Support I need']].map(([key, label]) => <label key={key}>{label}<textarea value={self[key]} onChange={e => setSelf(old => ({ ...old, [key]: e.target.value }))} /></label>)}
      <button type="button" disabled={busy} onClick={() => {
        const draft = { ...self, actuals: Object.fromEntries(Object.entries(self.actuals).map(([id, v]) => [id, Object.fromEntries(Object.entries(v).filter(([, value]) => value !== undefined))])) };
        act('self', { assessment: draft, submit: false });
      }}>Save draft</button><button className="primary" type="button" disabled={busy} onClick={() => act('self', { assessment: self, submit: true })}>Submit to line manager</button>
    </form>}
    {review.self_assessment && !review.can_self_assess && <details className="pv-card"><summary>Employee self-assessment</summary>{(review.section_a_kpis || []).map(g => { const a = review.self_assessment.actuals[g.id]; return <div key={g.id}><h3>{g.objective}</h3><p>Actual: {String(a?.actual ?? 'Not provided')} · Self-rating: {a?.self_score ?? 'Not provided'}</p><p>{a?.evidence}</p></div>; })}{review.self_assessment.accomplishments.map((a, i) => <p key={i}>{a}</p>)}<p>Challenge: {review.self_assessment.challenge}</p><p>Different approach: {review.self_assessment.do_differently}</p><p>Support: {review.self_assessment.support}</p></details>}
    {review.self_assessment && !review.can_self_assess && Object.values(review.self_assessment.actuals || {}).some(item => item.documents?.length) && <details className="pv-card"><summary>Attached evidence documents</summary><p>Downloads use the Document Centre’s current authorization and audit checks.</p>{Object.entries(review.self_assessment.actuals).flatMap(([goalId, item]) => (item.documents || []).map((id, index) => <button key={`${goalId}-${id}`} type="button" onClick={() => downloadEvidence(id)}>Download evidence {index + 1} — {review.section_a_kpis.find(g => g.id === goalId)?.objective}</button>))}</details>}
    {review.can_manage && review.status === 'Self_Submitted' && <form className="pv-card" onSubmit={e => { e.preventDefault(); act('manager', { actuals: managerScores, summary: review.manager_assessment?.summary || '', submit: true }); }}>
      <h2>Section A · KPIs (50%)</h2>
      <p className="pv-note">Review the employee’s actual and self-score, then give your manager score: 1.0 = met or beat target · 1.5 ≈ 90% · 2.0 ≈ 80% · 2.5 ≈ 70% · 3.0 = 60% or less. Add a comment when your score differs from the self-score.</p>
      <div className="pv-manager-table-wrap"><table className="pv-manager-table"><thead><tr>{['KPI (weight)', 'Target', 'Employee’s actual', 'Self-score', 'Manager score', 'Comment'].map(heading => <th key={heading} scope="col">{heading}</th>)}</tr></thead>
        <tbody>{(review.section_a_kpis || []).map(goal => {
          const employee = review.self_assessment?.actuals?.[goal.id];
          const entry = managerScores[goal.id] || {};
          const differs = entry.score != null && employee?.self_score != null && Number(entry.score) !== Number(employee.self_score);
          return <tr key={goal.id} data-score-differs={differs ? 'true' : undefined}>
            <th scope="row">{goal.objective} <span>({goal.weight}%)</span></th><td>{goal.target}</td><td>{displayActual(employee?.actual)}</td><td>{employee?.self_score != null ? Number(employee.self_score).toFixed(1) : 'Not provided'}</td>
            <td className="pv-manager-score-cell"><select aria-label={`Manager score for ${goal.objective}`} aria-describedby={differs ? `manager-difference-${goal.id}` : undefined} required disabled={busy} value={entry.score ?? ''} onChange={e => setManagerScores(old => ({ ...old, [goal.id]: { ...old[goal.id], score: e.target.value === '' ? undefined : Number(e.target.value) } }))}><option value="">Choose</option>{KPI_SCORES.map(score => <option key={score} value={score}>{score.toFixed(1)}</option>)}</select>{differs && <span className="pv-score-difference" id={`manager-difference-${goal.id}`}>Differs from self-score</span>}</td>
            <td><input aria-label={`Comment for ${goal.objective}`} required={differs} disabled={busy} value={entry.comment || ''} onChange={e => setManagerScores(old => ({ ...old, [goal.id]: { ...old[goal.id], comment: e.target.value } }))} /></td>
          </tr>;
        })}</tbody>
      </table></div>
      <div className="pv-section-a-total"><span>Section A = weighted average of manager scores (calculated automatically) · 1.0 best, 3.0 lowest</span><strong>{sectionAPreview === null ? 'Complete all scores' : sectionAPreview.toFixed(2)}</strong></div>
      <div className="pv-grid"><section className="pv-note"><h3>Section B · Values</h3><p>Peer 360° results stay hidden until HR releases the review. You’ll then see the averages and any self-versus-peer gaps.</p></section><section className="pv-note"><h3>Next step</h3><p>After you submit, HR adds company NPS and CSAT and arranges the review meeting.</p></section></div>
      <div className="pv-manager-actions"><button type="button" disabled={busy} onClick={() => act('manager', { actuals: managerScores, summary: review.manager_assessment?.summary || '', submit: false })}>Save draft</button><button className="primary" disabled={busy}>Submit to HR</button></div>
    </form>}
    {review.can_hr_review && review.status === 'Manager_Submitted' && <form className="pv-card" onSubmit={e => { e.preventDefault(); act('compile', { summary }); }}><h2>HR assessment</h2><p>Requires the manager assessment, at least three peer responses after collection closes, and verified company NPS/CSAT. HR cannot type a final score.</p><label>HR review summary<textarea required value={summary} onChange={e => setSummary(e.target.value)} /></label><button className="primary" disabled={busy}>Calculate and confirm HR assessment</button></form>}
    {review.can_hr_review && ['Manager_Submitted', 'HR_Reviewed'].includes(review.status) && !review.meeting_completed_at && <details className="pv-card"><summary>Correct a verified KPI actual (HR)</summary><p>Changes require a reason, preserve the manager submission in history and require HR assessment to be calculated again.</p><form onSubmit={e => { e.preventDefault(); act('correct', { actuals: Object.fromEntries(Object.entries(actuals).map(([id, item]) => [id, item.actual])), reason: notes }); }}>{review.section_a_kpis.map(g => <ActualInput key={g.id} goal={g} label={g.objective} value={actuals[g.id]?.actual} onChange={value => setActuals(old => ({ ...old, [g.id]: { ...old[g.id], actual: value } }))} />)}<label>Correction reason<textarea required minLength={10} value={notes} onChange={e => setNotes(e.target.value)} /></label><button disabled={busy}>Save audited actual correction</button></form></details>}
    {review.peer_summary && (!review.can_manage || review.can_hr_review || review.scores_released) && <section className="pv-values-results" aria-labelledby="peer-results-title">
      <h2 id="peer-results-title">Section B · Values (30%)</h2><p>Based on {review.peer_summary.response_count} colleagues’ reviews. Individual reviewers are never shown.</p>
      <div className="pv-card"><div className="pv-manager-table-wrap"><table className="pv-manager-table"><thead><tr>{['Value', 'My self-score (0–10)', 'Peer average (0–10)', 'Gap', 'Score (1–3)'].map(heading => <th key={heading} scope="col">{heading}</th>)}</tr></thead><tbody>{VALUES.map((name, i) => {
        const gap = review.peer_summary.gaps?.[i];
        const flagged = gap != null && Math.abs(gap) > 2;
        return <tr key={name}><th scope="row">{name}</th><td>{review.self_assessment?.values?.[i]?.score ?? 'Not available'}</td><td>{scoreText(review.peer_summary.averages?.[i])}</td><td><span className={flagged ? 'pv-gap-flagged' : ''}>{gapText(gap)}</span>{flagged && <span className="pv-gap-badge">Gap over 2 · Discuss in the review meeting</span>}</td><td><strong>{scoreText(review.peer_summary.dimension_scores?.[i], 2)}</strong></td></tr>;
      })}</tbody></table></div>
      <div className="pv-section-a-total"><span>Section B = average of the five scores. Only the peer average counts; your self-score is for comparison.</span><strong>{scoreText(review.peer_summary.score, 2)}</strong></div>
      <p className="pv-result-help">How peer averages convert: 10 → 1.0 · 9 → 1.5 · 8 → 2.0 · 7 → 2.5 · 6 or below → 3.0</p></div>
      <section className="pv-card"><h3>What colleagues said</h3><p className="pv-result-help">Comments are shown unattributed and in random order.</p>
        <div className="pv-peer-comment-grid">{[['strengthens_team', 'Strengths'], ['more_effective', 'To be more effective']].map(([field, title]) => <section className="pv-peer-comment-panel" key={field}><h4>{title}</h4>{review.peer_summary[field]?.length ? review.peer_summary[field].map((comment, i) => <blockquote key={i}>{comment}</blockquote>) : <p className="pv-result-help">No comments provided.</p>}</section>)}</div>
        {!!review.peer_summary.comments?.length && <section className="pv-peer-comment-panel"><h4>Other colleague feedback</h4>{review.peer_summary.comments.map((comment, i) => <blockquote key={i}>{comment}</blockquote>)}</section>}
        <p className="pv-result-help">The “Would you fight to keep this person?” answers are seen by HR only and are not shown here.</p>
      </section>
      {review.can_hr_review && review.peer_summary.retention_average != null && <p>HR-only retention signal: {review.peer_summary.retention_average} / 10</p>}
    </section>}
    {review.manager_assessment && review.status !== 'Self_Submitted' && <details className="pv-card"><summary>Confirmed manager assessment</summary><p>{review.manager_assessment.summary}</p>{review.section_a_kpis.map(g => <p key={g.id}>{g.objective}: confirmed actual {String(review.manager_assessment.actuals[g.id]?.actual ?? 'Not provided')} · Score {review.section_a_kpi_scores?.[g.id] ?? 'Not available'} · {review.manager_assessment.actuals[g.id]?.comment}</p>)}</details>}
    {review.status === 'HR_Reviewed' && (review.can_manage || review.can_hr_review) && <section className="pv-card"><h2>Review meeting</h2><p>The line manager proposes a date in Weeks 3–4. HR arranges the meeting manually, then confirms it here. No Outlook meeting is created.</p>
      <button type="button" disabled={busy} onClick={async () => { try { const result = await api.getReviewMeetingOptions(review.id); setDateOptions(result.data); } catch (err) { setError(errorText(err)); } }}>Suggest available meeting dates</button>
      {dateOptions && <div><p>{dateOptions.notice}</p>{dateOptions.dates.map(d => <button key={d} type="button" onClick={() => setMeeting(old => ({ ...old, scheduled_at: `${d}T10:00` }))}>{d}</button>)}</div>}
      <form onSubmit={e => { e.preventDefault(); act(review.can_hr_review ? 'schedule' : 'propose', { scheduled_at: new Date(meeting.scheduled_at).toISOString(), location: meeting.location }); }}><div className="pv-grid"><label>Meeting date and time<input required type="datetime-local" min={`${new Date(new Date(`${review.manager_due_on}T12:00:00Z`).getTime() + 86400000).toISOString().slice(0, 10)}T00:00`} max={`${review.review_due_on}T23:59`} value={meeting.scheduled_at} onChange={e => setMeeting(old => ({ ...old, scheduled_at: e.target.value }))} /></label><label>Location / meeting details<input required value={meeting.location} onChange={e => setMeeting(old => ({ ...old, location: e.target.value }))} /></label></div><ActionButton disabled={busy || !!review.meeting_completed_at} disabledReason={review.meeting_completed_at ? 'This review meeting is already completed. Contact HR if its record needs correcting.' : ''}>{review.can_hr_review ? 'HR: meeting arranged — notify participants' : 'Propose date — notify HR and employee'}</ActionButton></form>
      {review.can_hr_review && review.review_meeting && !review.meeting_completed_at && <form onSubmit={e => { e.preventDefault(); act('complete', { notes }); }}><label>Meeting completion notes<textarea required value={notes} onChange={e => setNotes(e.target.value)} /></label><button disabled={busy}>Record meeting completed</button></form>}
      {review.can_hr_review && review.meeting_completed_at && <form onSubmit={e => { e.preventDefault(); act('release', { late_reason: notes }); }}><label>Reason if release is more than 48 hours after meeting<textarea value={notes} onChange={e => setNotes(e.target.value)} /></label><button className="primary" disabled={busy}>Release review to employee</button></form>}
    </section>}
    {review.review_meeting && <p className="pv-note">Confirmed meeting: {new Date(review.review_meeting.scheduled_at).toLocaleString()} · {review.review_meeting.location}</p>}
    {review.can_hr_review && review.dispute?.status === 'Pending_HR' && <form className="pv-card" onSubmit={e => { e.preventDefault(); act('resolve-dispute', { resolution: notes }); }}><h2>Employee dispute</h2><p>{review.dispute.statement}</p><label>HR written resolution<textarea required value={notes} onChange={e => setNotes(e.target.value)} /></label><button disabled={busy}>Record resolution and notify employee</button></form>}
    {review.dispute?.resolution && <p className="pv-note">HR dispute response: {review.dispute.resolution}</p>}
    {review.can_hr_review && review.actual_corrections?.length > 0 && <details className="pv-card"><summary>HR actual-correction history</summary>{review.actual_corrections.map((c, i) => <p key={i}>{new Date(c.at).toLocaleString()} · {c.reason}</p>)}</details>}
    {review.scores_released && <section className="pv-card"><h2>Released review</h2><p>Overall: {review.overall_score} · {review.rating} · {review.nine_box_placement?.replaceAll('_', ' ')}</p><p>{review.hr_summary}</p>{!review.can_hr_review && !review.can_manage && <><p>Acknowledge by {review.ack_due_on}. Acknowledgement confirms receipt, not agreement.</p>{review.acknowledged_at ? <p>Acknowledged {new Date(review.acknowledged_at).toLocaleDateString()}</p> : <button className="primary" disabled={busy} onClick={() => act('acknowledge', { confirmed: true })}>Acknowledge review</button>}{review.dispute ? <p>Your written dispute is with HR.</p> : <form onSubmit={e => { e.preventDefault(); act('acknowledge', { dispute }); }}><label>Written dispute to HR<textarea required value={dispute} onChange={e => setDispute(e.target.value)} /></label><button disabled={busy}>Submit dispute</button></form>}</>}</section>}
  </section>;
}
