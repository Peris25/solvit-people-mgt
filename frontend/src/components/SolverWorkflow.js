import React, { useEffect, useState } from 'react';
import SolverCompetencies from './SolverCompetencies';
import * as api from '../services/api';

const categories = ['Contact and statutory form', 'Induction video confirmation', 'Code quiz result', 'Signed Solver agreement', 'Vehicle assessment', 'Other'];
const gates = ['contact', 'video', 'code_quiz', 'agreement', 'vehicle_assessment'];

export default function SolverWorkflow({ solverId, accountId }) {
  const [data, setData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [gate, setGate] = useState('contact');
  const [documentId, setDocumentId] = useState('');
  const [reference, setReference] = useState('');
  const [score, setScore] = useState('');
  const [outcome, setOutcome] = useState('');
  const [file, setFile] = useState(null);
  const [category, setCategory] = useState(categories[0]);
  const [visibility, setVisibility] = useState('hr_only');
  const key = `${accountId}:${solverId}`;
  const current = data?.key === key ? data.value : null;
  useEffect(() => {
    let cancelled = false;
    setError(''); setDocuments([]); setDocumentId('');
    Promise.all([api.getSolverWorkflow(solverId), api.getSolverDocuments(solverId)]).then(([workflow, docs]) => {
      if (cancelled) return;
      if (!workflow.data || !Array.isArray(docs.data)) throw new Error('Unavailable');
      setData({ key, value: workflow.data }); setDocuments(docs.data);
    }).catch(() => { if (!cancelled) { setData(null); setError('Could not load Solver workflow. Please retry.'); } });
    return () => { cancelled = true; };
  }, [solverId, key, revision]);
  const perform = async action => {
    setBusy(true); setError('');
    try { await action(); setRevision(value => value + 1); }
    catch (e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'The action could not be completed. Refresh before retrying.'); }
    finally { setBusy(false); }
  };
  const download = doc => perform(async () => {
    const result = await api.downloadSolverDocument(solverId, doc.id);
    const url = URL.createObjectURL(result.data);
    const link = document.createElement('a'); link.href = url; link.download = doc.file_name || 'Document'; link.click();
    URL.revokeObjectURL(url);
  });
  return <section style={{ gridColumn: '1 / -1', borderTop: '1px solid #ddd', marginTop: 16, paddingTop: 16 }}>
    <h3>Induction & assessments</h3>
    <p><a href="/solver-assessments">Assigned assessments & competency records</a></p>
    {error && <p role="alert">{error}</p>}
    {!current && !error && <p>Loading workflow...</p>}
    {error && <button onClick={() => setRevision(value => value + 1)}>Retry</button>}
    {current && <>
      {current.can_manage && <button disabled={busy} onClick={() => perform(() => api.initiateSolverInduction(solverId))}>Initialize induction checklist</button>}
      {current.tasks.length ? <ul>{current.tasks.map(task => <li key={task.id}>{task.title} — {task.status}</li>)}</ul> : <p>No induction checklist recorded.</p>}
      <h4>Verified requirements</h4>
      <ul>{gates.map(name => <li key={name}>{name.replaceAll('_', ' ')}: {current.verification.find(item => item.gate === name)?.verified ? 'Verified' : 'Awaiting verification'}</li>)}</ul>
      {current.can_manage && <form onSubmit={event => { event.preventDefault(); perform(() => api.verifySolverInduction(solverId, { gate, document_id: documentId, reference, ...(gate === 'code_quiz' ? { score: Number(score), maximum: 10 } : {}), ...(gate === 'vehicle_assessment' ? { outcome } : {}) })); }} style={{ display: 'grid', gap: 8 }}>
        <label>Requirement <select value={gate} onChange={e => setGate(e.target.value)}>{gates.map(name => <option key={name} value={name}>{name.replaceAll('_', ' ')}</option>)}</select></label>
        <label>Supporting document <select required value={documentId} onChange={e => setDocumentId(e.target.value)}><option value="">Choose authorized evidence</option>{documents.map(doc => <option key={doc.id} value={doc.id}>{doc.category} — {doc.file_name}</option>)}</select></label>
        <label>Verification reference <input required minLength={3} maxLength={300} value={reference} onChange={e => setReference(e.target.value)} /></label>
        {gate === 'code_quiz' && <label>Actual code quiz score / 10 <input required type="number" min="0" max="10" step="1" value={score} onChange={e => setScore(e.target.value)} /></label>}
        {gate === 'vehicle_assessment' && <label>Documented assessor decision (no score inferred) <select required value={outcome} onChange={e => setOutcome(e.target.value)}><option value="">Choose the evidenced outcome</option>{['Pass', 'Fail', 'Re-sit'].map(value => <option key={value}>{value}</option>)}</select></label>}
        <button disabled={busy}>Record verification</button>
      </form>}
      <h4>Recorded assessments</h4>
      {current.assessments.length ? <ul>{current.assessments.map(item => <li key={item.id}>{item.form_title || item.form_id}: {item.status || 'Recorded'}{item.score != null ? ` — score ${item.score}` : ''}{item.passed != null ? ` — ${item.passed ? 'Passed' : 'Not passed'}` : ''} — {item.reviewed ? 'Reviewed' : 'Awaiting review'}{current.can_manage && !item.reviewed && <button disabled={busy} onClick={() => perform(() => api.reviewSolverAssessment(solverId, item.id))}>Record review of existing result</button>}</li>)}</ul> : <p>No assessment results recorded.</p>}
      <p>{current.assessment_notice}</p>
      <SolverCompetencies key={`${solverId}:${revision}`} solverId={solverId} canManage={current.can_upload} perform={perform} busy={busy} />
      <h4>Authorized documents</h4>
      {documents.length ? <ul>{documents.map(doc => <li key={doc.id}><button disabled={busy} onClick={() => download(doc)}>{doc.file_name}</button> — {doc.category} / {doc.uploaded_at?.slice(0, 10) || 'Date not recorded'}</li>)}</ul> : <p>No documents shared with your role.</p>}
      {current.can_upload && <form onSubmit={event => { event.preventDefault(); perform(async () => { const form = new FormData(); form.append('file', file); form.append('category', category); form.append('visibility', visibility); form.append('confidential', String(visibility === 'hr_only')); await api.uploadSolverDocument(solverId, form); }); }} style={{ display: 'grid', gap: 8 }}>
        <label>Document category <select value={category} onChange={e => setCategory(e.target.value)}>{categories.map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Sharing <select value={visibility} onChange={e => setVisibility(e.target.value)}><option value="hr_only">HR only (default)</option><option value="hr_manager">Explicitly share non-confidential evidence with Solvers Manager</option><option value="hr_assessment">Explicitly share non-confidential evidence with this Solver and assigned assessors</option><option value="hr_solver">Explicitly share non-confidential document with this Solver</option></select></label>
        <label>File (PDF, JPG, PNG, DOCX, XLSX; maximum 20 MB) <input required type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx" onChange={e => setFile(e.target.files[0])} /></label>
        <button disabled={busy || !file}>Upload Solver document</button>
      </form>}
    </>}
  </section>;
}
