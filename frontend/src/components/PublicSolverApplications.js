import React, { useCallback, useEffect, useState } from 'react';
import * as api from '../services/api';
import { Eye, X, RefreshCw, ExternalLink, Search } from 'lucide-react';
import './PublicSolverApplications.css';

export default function PublicSolverApplications({ canReview = false }) {
  const [rows, setRows] = useState([]);
  const [detail, setDetail] = useState(null);
  const [search, setSearch] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false; setLoading(true);
    api.getPublicSolverApplications().then(result => { if (!Array.isArray(result.data)) throw new Error('Unavailable'); if (!cancelled) { setRows(result.data); setError(''); } }).catch(() => { if (!cancelled) setError('Unable to load new applicant assessments.'); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [revision]);
  const close = () => { setDetail(null); setNotes(''); };
  const loadApplication = useCallback(async id => {
    setBusy(true); setError(''); setDetail(null);
    try { const row = (await api.getPublicSolverApplication(id)).data; setDetail(row); setNotes(row.review_notes || ''); }
    catch { setError('Unable to open this assessment.'); }
    finally { setBusy(false); }
  }, []);
  const open = id => { if (detail?.id === id) close(); else loadApplication(id); };
  useEffect(() => { const id = new URLSearchParams(window.location.search).get('application'); if (id) loadApplication(id); }, [loadApplication]);
  const review = async event => {
    event.preventDefault(); setBusy(true);
    try { await api.reviewPublicSolverApplication(detail.id, notes); setDetail(null); setRevision(value => value + 1); }
    catch { setError('Review could not be saved. Refresh and retry.'); }
    finally { setBusy(false); }
  };
  return <section className="solver-applications" aria-label="New applicant assessments" style={{ background: '#fff', border: '1px solid #ddd', borderRadius: 8, padding: 20 }}>
    <h2>New applicant assessments</h2><p>Public submissions are unverified applications. They do not create Active Solvers or award assessment scores.</p>
    <a className="solver-inbox-link" href="/solver-assessments" target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Open public questionnaire</a>
    <div className="solver-inbox-tools"><label><Search size={17} aria-hidden="true" />Find applicant <input value={search} onChange={e => setSearch(e.target.value)} style={{ padding: 10, marginLeft: 8 }} /></label><button className="solver-inbox-secondary" onClick={() => setRevision(v => v + 1)}><RefreshCw size={16} aria-hidden="true" />Refresh applications</button></div>
    {error && <p role="alert">{error}</p>}{loading && <p role="status">Loading applications...</p>}
    {!loading && rows.length === 0 && <p>No new applicant assessments received.</p>}
    <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', textAlign: 'left' }}><thead><tr><th>Applicant</th><th>Submitted</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.filter(row => row.full_name.toLowerCase().includes(search.toLowerCase())).map(row => <tr key={row.id}><td>{row.full_name}</td><td>{new Date(row.submitted_at).toLocaleString()}</td><td>{row.status}</td><td><button type="button" className={`solver-inbox-view${detail?.id === row.id ? ' is-open' : ''}`} disabled={busy} aria-expanded={detail?.id === row.id} aria-controls="solver-applicant-answers" onClick={() => open(row.id)}>{detail?.id === row.id ? <X size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}{detail?.id === row.id ? 'Close view' : 'View answers'}</button></td></tr>)}</tbody></table></div>
    {detail && <section id="solver-applicant-answers" className="solver-inbox-detail" aria-label="Applicant answers" style={{ marginTop: 24, padding: 20, border: '1px solid #ddd' }}><h3>{detail.full_name}</h3>
      {!!detail.pending_questions?.length && <p role="status">The source photo question is pending. Follow up before making a suitability decision.</p>}
      {detail.sections.map(section => <div key={section.id}><h4>{section.title}</h4>{section.questions.map(q => <div key={q.id} style={{ margin: '16px 0' }}><strong>{q.label}</strong><p style={{ whiteSpace: 'pre-wrap' }}>{q.availability ? 'Awaiting source photos / HR follow-up' : detail.answers[q.id] || 'No answer provided / not applicable'}</p></div>)}</div>)}
      {canReview && detail.status === 'Submitted' ? <form onSubmit={review}><label>HR review notes<textarea required minLength={3} maxLength={4000} value={notes} onChange={e => setNotes(e.target.value)} style={{ display: 'block', width: '100%', minHeight: 100 }} /></label><button disabled={busy} style={{ background: '#d91e30', color: 'white', border: 0, padding: '12px 20px', marginTop: 12 }}>Record review</button><p>This records HR review only; it does not assign a score, approve onboarding or activate a Solver.</p></form> : <p>{detail.status === 'Reviewed' ? (canReview ? `Review notes: ${detail.review_notes}` : 'HR review completed.') : 'HR will record the formal review. You can view the submitted answers here.'}</p>}
      <button type="button" className="solver-inbox-secondary" onClick={close}><X size={16} aria-hidden="true" />Close view</button>
    </section>}
  </section>;
}
