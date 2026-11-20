import React, { useEffect, useRef, useState } from 'react';
import * as api from '../services/api';
import './PerformanceV3.css';

const blank = () => ({ scores: Array(5).fill(''), retain: '', relationship: 'Peer', strengthens_team: '', more_effective: '' });
const VALUE_NAMES = ['Integrity', 'Hard Work & Ownership', 'Teamwork & Decency', 'Solution Orientation', 'Timeliness'];
export default function PeerReviewSelector({ initialTaskId = '', onSubmitted }) {
  const [tasks, setTasks] = useState(null); const [taskId, setTaskId] = useState(initialTaskId);
  const [questions, setQuestions] = useState([]); const [values, setValues] = useState(blank);
  const [choices, setChoices] = useState([]); const [cycleId, setCycleId] = useState(''); const [colleagueId, setColleagueId] = useState('');
  const openedInitialTask = useRef('');
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false); const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const response = await api.getPerformanceV3Tasks();
        const initial = response.data.peers?.find(task => task.id === initialTaskId && task.can_submit);
        let opened = false;
        if (initial && active && openedInitialTask.current !== initialTaskId) {
          const started = await api.performanceV3Action('peers', initial.id, 'start', {});
          if (started?.data?.status !== 'Started') throw new Error('Review start not confirmed');
          initial.can_remove = false; initial.started = true;
          openedInitialTask.current = initialTaskId; opened = true;
        }
        if (active) {
          setTasks(response.data.peers); setChoices(response.data.peer_choices || []); setQuestions(response.data.peer_questions); setError('');
          setCycleId(old => old || response.data.peers?.find(task => task.id === initialTaskId)?.cycle_id || response.data.peer_choices?.[0]?.cycle_id || response.data.peers?.[0]?.cycle_id || '');
          if (opened) setValues({ ...blank(), ...initial.draft });
        }
      } catch { if (active) setError('Unable to load eligible colleagues. Please retry.'); }
    })();
    return () => { active = false; };
  }, [attempt, initialTaskId]);
  const cycleTasks = (tasks || []).filter(task => !cycleId || task.cycle_id === cycleId);
  const available = cycleTasks.filter(t => t.can_submit);
  const selected = available.find(t => t.id === taskId);
  const cycleChoices = choices.filter(choice => choice.cycle_id === cycleId);
  const unchosen = cycleChoices.filter(choice => !cycleTasks.some(task => task.employee_id === choice.employee_id));
  const cycles = [...new Map([...choices.map(choice => [choice.cycle_id, choice.cycle_title]), ...(tasks || []).map(task => [task.cycle_id, choices.find(choice => choice.cycle_id === task.cycle_id)?.cycle_title || 'Review cycle'])]).entries()].filter(([id]) => id);
  const minimumChosen = cycleTasks.length >= 5;
  const chooseTask = async task => {
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await api.performanceV3Action('peers', task.id, 'start', {});
      if (response?.data?.status !== 'Started') throw new Error('Review start not confirmed');
      setTaskId(task.id); setValues({ ...blank(), ...task.draft });
      setTasks(old => old.map(item => item.id === task.id ? { ...item, can_remove: false, started: true } : item));
    } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'This review could not be opened. Please retry.'); }
    finally { setBusy(false); }
  };
  const changeList = async (reference, action) => {
    setBusy(true); setError(''); setMessage('');
    try { const response = await api.performanceV3Action('peers', reference, action, {}); if (response?.data?.status !== (action === 'choose' ? 'Selected' : 'Removed')) throw new Error('List update not confirmed'); setAttempt(old => old + 1); }
    catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Your colleague list could not be updated. Please retry.'); }
    finally { setBusy(false); }
  };
  const saveDraft = async () => {
    if (!selected) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await api.performanceV3Action('peers', selected.id, 'draft', values);
      if (response?.data?.status !== 'Draft saved') throw new Error('Draft not confirmed');
      setTasks(old => old.map(task => task.id === selected.id ? { ...task, draft: values, can_remove: false } : task));
      setMessage('Peer review draft saved.');
    } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Draft could not be saved. Your answers have been kept.'); }
    finally { setBusy(false); }
  };
  const submit = async event => {
    event.preventDefault(); if (!selected) { setError('Choose an eligible colleague.'); return; }
    if (!minimumChosen) { setError('Choose at least five colleagues for this cycle before submitting.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await api.performanceV3Action('peers', selected.id, 'submit', values);
      if (response?.data?.status !== 'Submitted') throw new Error('Submission not confirmed');
      setTasks(old => old.map(t => t.id === selected.id ? { ...t, status: 'Submitted', can_submit: false } : t));
      setTaskId(''); setValues(blank()); setMessage(`Peer review for ${selected.employee_name} submitted successfully.`);
      onSubmitted?.();
    } catch (err) { setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Submission was not confirmed. Your answers have been kept; refresh your assignments before retrying.'); }
    finally { setBusy(false); }
  };
  return <section className="performance-v3" aria-label="Choose colleague for 360 peer review">
    <h2>Review your colleagues</h2><p>Choose at least 5 colleagues to review from anyone in the company. You can add as many more as you like. You cannot review yourself. Each colleague needs an open review in the selected cycle. Reviews use the approved 0–10 values scale.</p>
    {error && <p role="alert">{error} <button type="button" disabled={busy} onClick={() => setAttempt(n => n + 1)}>Refresh eligible colleagues</button></p>}
    {message && <p role="status">{message}</p>}
    {!tasks && !error && <p role="status" aria-live="polite">Loading peer review…</p>}
    {tasks && <section className="pv-card" aria-label="My colleagues to review"><h3>My colleagues to review</h3>
      {cycles.length > 1 && <label>Review cycle<select disabled={busy} value={cycleId} onChange={event => { setCycleId(event.target.value); setTaskId(''); setColleagueId(''); setValues(blank()); }}>{cycles.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>}
      <p aria-live="polite">{cycleTasks.filter(task => task.status === 'Submitted').length} of {cycleTasks.length} submitted · {minimumChosen ? 'Minimum of 5 chosen' : `${Math.max(0, 5 - cycleTasks.length)} more colleagues needed`}</p>
      <div className="pv-peer-add"><label>Add a colleague (anyone in the company)<select aria-label="Add colleague to review" value={colleagueId} disabled={busy} onChange={event => setColleagueId(event.target.value)}><option value="">Choose a colleague…</option>{unchosen.map(choice => <option key={choice.employee_id} value={choice.review_id || choice.employee_id} disabled={!choice.review_id}>{[choice.employee_name, choice.role_title].filter(Boolean).join(' · ')}{!choice.review_id ? ` — ${choice.unavailable_reason}` : ''}</option>)}</select></label><button type="button" disabled={busy || !colleagueId} onClick={async () => { await changeList(colleagueId, 'choose'); setColleagueId(''); }}>+ Add to my list</button></div>
      <div className="pv-peer-list">{cycleTasks.map(task => <div className="pv-peer-list-item" data-selected={task.id === taskId ? 'true' : undefined} key={task.id}><button type="button" disabled={busy || !task.can_submit} onClick={() => chooseTask(task)}>{task.employee_name}<span>{task.role_title}</span><span>{task.status === 'Submitted' ? 'Submitted' : task.started || task.draft ? 'In progress' : task.can_submit ? 'To do' : 'Closed'}</span></button>{task.can_remove && <button type="button" disabled={busy} aria-label={`Remove ${task.employee_name} from my list`} onClick={() => changeList(task.id, 'remove')}>Remove</button>}</div>)}</div>
      <p>You can remove an unstarted review from your list. Save your draft before changing colleagues. Submitted reviews are final.</p>
    </section>}
    {tasks && !available.length && <p>No peer reviews are currently open for you. Contact HR to confirm the cycle dates and reviewer assignments.</p>}
    {!!available.length && <form className="pv-peer-form" onSubmit={submit}>
      <label>Colleague to review<select required aria-label="Colleague to review" disabled={busy} value={selected ? taskId : ''} onChange={e => { const task = available.find(item => item.id === e.target.value); if (task) chooseTask(task); else { setTaskId(''); setValues(blank()); } }}>
        <option value="">Select a colleague…</option>{available.map(t => <option key={t.id} value={t.id}>{[t.employee_name, t.role_title, t.department].filter(Boolean).join(' — ')}</option>)}
      </select></label><p>Changing the colleague clears unsaved ratings.</p>
      {selected && <fieldset disabled={busy}><legend>Reviewing {selected.employee_name} · Due {selected.due_on}</legend>
        <p>Score 0–10: 10 = exemplary, 0 = never observed. Answers are confidential. Only averages from at least three responses are shared; individual responses are not shown to HR or the manager.</p>
        {questions.map((question, index) => <fieldset className="peer-rating" key={question}>
          <legend><strong>{VALUE_NAMES[index]}</strong><br />{question} <span aria-hidden="true">*</span></legend>
          <div className="peer-rating-options">
            {Array.from({ length: 11 }, (_, score) => <label className="peer-rating-choice" key={score}>
              <input type="radio" required name={`peer-value-${index}`} aria-label={`${question}: ${score} out of 10`} value={score} checked={values.scores[index] === score} onChange={() => setValues(old => ({ ...old, scores: old.scores.map((value, i) => i === index ? score : value) }))} />
              <span className="peer-rating-card"><strong>{score}</strong><span>{values.scores[index] === score ? 'Selected' : 'out of 10'}</span></span>
            </label>)}
          </div>
        </fieldset>)}
        <label>Working relationship<select value={values.relationship} onChange={e => setValues(old => ({ ...old, relationship: e.target.value }))}><option value="Peer">Peer</option><option value="Direct_Report">Direct report</option><option value="Cross_Functional">Cross-functional colleague</option></select></label>
        <label>Would you fight to keep this person on the team?<select required value={values.retain} onChange={e => setValues(old => ({ ...old, retain: e.target.value === '' ? '' : Number(e.target.value) }))}><option value="">Choose</option><option value={10}>Yes</option><option value={5}>Maybe</option><option value={0}>No</option></select></label><p>Seen by HR only. Not part of anyone’s score.</p>
        <label>What does this person do that most strengthens the team? (optional)<textarea maxLength={4000} value={values.strengthens_team} onChange={e => setValues(old => ({ ...old, strengthens_team: e.target.value }))} /></label>
        <label>What is one thing that would make this person more effective? (optional)<textarea maxLength={4000} value={values.more_effective} onChange={e => setValues(old => ({ ...old, more_effective: e.target.value }))} /></label>
        <p>Do not name yourself or other reviewers in comments. You can submit once per colleague.</p><button type="button" disabled={busy} onClick={saveDraft}>Save draft</button><button className="primary" disabled={busy || !minimumChosen}>{busy ? 'Submitting…' : 'Submit peer review'}</button>
      </fieldset>}
    </form>}
  </section>;
}
