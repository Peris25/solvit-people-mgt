import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import './PublicSolverAssessment.css';

const errorMessage = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Unable to complete this request. Please try again.';

export default function PublicSolverAssessment() {
  const [bank, setBank] = useState(null);
  const [challenge, setChallenge] = useState(null);
  const [answers, setAnswers] = useState({});
  const [verification, setVerification] = useState('');
  const [consent, setConsent] = useState(false);
  const [website, setWebsite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getPublicSolverQuestionnaire(), api.getPublicSolverChallenge()]).then(([questions, proof]) => {
      if (!Array.isArray(questions.data?.sections) || !proof.data?.token) throw new Error('Unavailable');
      if (!cancelled) { setBank(questions.data); setChallenge(proof.data); setError(''); }
    }).catch(e => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [retry]);
  const refreshVerification = async () => {
    try { setChallenge((await api.getPublicSolverChallenge()).data); setVerification(''); setError(''); }
    catch (e) { setError(errorMessage(e)); }
  };
  const submit = async event => {
    event.preventDefault(); if (busy) return; setBusy(true); setError('');
    try {
      const result = await api.submitPublicSolverAssessment({ version: bank.version, answers, challenge_token: challenge.token, challenge_answer: verification, website, consent });
      setReceipt(result.data); setAnswers({}); setVerification('');
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  return <main className="public-assessment">
    <header><a href="/login" aria-label="Solvit People sign in"><strong>Solvit<span> People</span></strong></a><span>NEW SOLVER APPLICATION</span></header>
    <div className="assessment-intro"><span className="assessment-eyebrow">SOLVIT ? PEOPLE & OPPORTUNITY</span><h1>Motor Vehicle Solver Assessment</h1><p>Tell us about your vehicle knowledge and how you work with clients. No portal account is required.</p></div>
    {error && <div role="alert" className="assessment-error">{error}</div>}
    {receipt ? <section className="assessment-section" role="status"><h2>Assessment received</h2><p>Your answers have been sent to HR for review.</p><p>Reference: <strong>{receipt.reference}</strong></p><p>This is an application assessment, not a certification or an active Solver account. HR may follow up on the photo question.</p></section> : !bank || !challenge ? <section className="assessment-section"><p role="status">Loading questionnaire?</p>{error && <button onClick={() => setRetry(v => v + 1)}>Retry</button>}</section> : <form onSubmit={submit}>
      <p>Fields marked * are required. Your name and answers will be available only to authorized reviewers. Answers are not saved until you submit.</p>
      {bank.sections.map(section => {
        const questions = section.questions.filter(q => !q.unless_answer || answers[q.unless_answer.id] !== q.unless_answer.value);
        if (!questions.length) return null;
        return <section className="assessment-section" key={section.id}><h2>{section.title}</h2>{questions.map(q => <fieldset key={q.id}><legend>{q.label}{q.required && !q.availability ? ' *' : ''}</legend>
          {q.availability ? <p className="assessment-note">The two reference photos are awaiting publication. HR will follow up on this question; no answer is being recorded for it.</p> : q.type === 'text' || q.type === 'paragraph' ? React.createElement(q.type === 'text' ? 'input' : 'textarea', { 'aria-label': q.label, required: q.required, maxLength: q.type === 'text' ? 200 : 6000, value: answers[q.id] || '', onChange: e => setAnswers(old => ({ ...old, [q.id]: e.target.value })) }) : <>
            {q.scale_labels && <p className="assessment-note">{q.options[0]} = {q.scale_labels[0]} ? {q.options[q.options.length - 1]} = {q.scale_labels[1]}</p>}
            <div className={q.type === 'scale' ? 'assessment-scale' : 'assessment-choices'}>{q.options.map(option => <label key={option}><input type="radio" name={q.id} value={option} required={q.required} checked={answers[q.id] === option} onChange={() => setAnswers(old => { const next = { ...old, [q.id]: option }; for (const part of bank.sections) for (const dependent of part.questions) if (dependent.unless_answer?.id === q.id && dependent.unless_answer.value === option) delete next[dependent.id]; return next; })} />{option}</label>)}</div>
          </>}
        </fieldset>)}</section>;
      })}
      <section className="assessment-section"><h2>Submit your assessment</h2>
        <div className="assessment-trap" aria-hidden="true"><label>Website<input tabIndex={-1} autoComplete="off" value={website} onChange={e => setWebsite(e.target.value)} /></label></div>
        <label className="assessment-consent"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} />I agree that Solvit may use my name and answers to review this application.</label>
        <label className="assessment-verification">Verification: {challenge.question}<input required inputMode="numeric" maxLength={3} value={verification} onChange={e => setVerification(e.target.value)} /></label>
        <button type="button" className="assessment-secondary" disabled={busy} onClick={refreshVerification}>Refresh verification</button>
        <button type="submit" disabled={busy}>{busy ? 'Submitting?' : 'Submit assessment'}</button>
      </section>
    </form>}
    <footer>Solvit People ? New Solver assessments</footer>
  </main>;
}
