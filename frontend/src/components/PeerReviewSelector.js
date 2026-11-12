import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import './PerformanceV3.css';

const blank = () => ({ scores: Array(5).fill(''), retain: '', relationship: 'Peer', comment: '' });
export default function PeerReviewSelector({ initialTaskId = '', onSubmitted }) {
  const [tasks, setTasks] = useState(null); const [taskId, setTaskId] = useState(initialTaskId);
  const [questions, setQuestions] = useState([]); const [values, setValues] = useState(blank);
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false); const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const response = await api.getPerformanceV3Tasks();
        if (active) { setTasks(response.data.peers); setQuestions(response.data.peer_questions); setError(''); }
      } catch { if (active) setError('Unable to load eligible colleagues. Please retry.'); }
    })();
    return () => { active = false; };
  }, [attempt]);
  const available = (tasks || []).filter(t => t.can_submit);
  const selected = available.find(t => t.id === taskId);
  const submit = async event => {
    event.preventDefault(); if (!selected) { setError('Choose an eligible colleague.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      await api.performanceV3Action('peers', selected.id, 'submit', values);
      setTasks(old => old.map(t => t.id === selected.id ? { ...t, status: 'Submitted', can_submit: false } : t));
      setTaskId(''); setValues(blank()); setMessage(`Peer review for ${selected.employee_name} submitted successfully.`);
      onSubmitted?.();
    } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Submission was not confirmed. Your answers have been kept; refresh your assignments before retrying.'); }
    finally { setBusy(false); }
  };
  return <section className="performance-v3" aria-label="Choose colleague for 360 peer review">
    <p>Choose a colleague from your open review assignments. Answers are confidential and use the approved 0–10 values scale. HR must assign colleagues outside your eligible review group.</p>
    {error && <p role="alert">{error} <button type="button" disabled={busy} onClick={() => setAttempt(n => n + 1)}>Refresh eligible colleagues</button></p>}
    {message && <p role="status">{message}</p>}
    {!tasks && !error && <p role="status">Loading eligible colleagues…</p>}
    {tasks && !available.length && <p>No peer reviews are currently open for you. Contact HR to confirm the cycle dates and reviewer assignments.</p>}
    {!!available.length && <form onSubmit={submit}>
      <label>Colleague to review<select required aria-label="Colleague to review" disabled={busy} value={selected ? taskId : ''} onChange={e => { setTaskId(e.target.value); setValues(blank()); setError(''); setMessage(''); }}>
        <option value="">Select a colleague…</option>{available.map(t => <option key={t.id} value={t.id}>{[t.employee_name, t.role_title, t.department].filter(Boolean).join(' — ')}</option>)}
      </select></label><p>Changing the colleague clears unsaved ratings.</p>
      {selected && <fieldset disabled={busy}><legend>Reviewing {selected.employee_name} · Due {selected.due_on}</legend>
        {questions.map((question, index) => <label key={question}>{question}<select required aria-label={`Peer value ${index + 1}`} value={values.scores[index]} onChange={e => setValues(old => ({ ...old, scores: old.scores.map((score, i) => i === index ? (e.target.value === '' ? '' : Number(e.target.value)) : score) }))}>
          <option value="">Select rating (0–10)</option>{Array.from({ length: 11 }, (_, i) => <option value={i} key={i}>{i}</option>)}
        </select></label>)}
        <label>Working relationship<select value={values.relationship} onChange={e => setValues(old => ({ ...old, relationship: e.target.value }))}><option value="Peer">Peer</option><option value="Direct_Report">Direct report</option><option value="Cross_Functional">Cross-functional colleague</option></select></label>
        <label>Would you fight to keep this person? (HR only)<select required value={values.retain} onChange={e => setValues(old => ({ ...old, retain: e.target.value === '' ? '' : Number(e.target.value) }))}><option value="">Choose</option><option value={10}>Yes</option><option value={5}>Maybe</option><option value={0}>No</option></select></label>
        <label>Optional anonymous comment<textarea maxLength={4000} value={values.comment} onChange={e => setValues(old => ({ ...old, comment: e.target.value }))} /></label>
        <p>Do not identify yourself or another reviewer in comments. You cannot submit a second review for the same assignment.</p><button className="primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit peer review'}</button>
      </fieldset>}
    </form>}
  </section>;
}
