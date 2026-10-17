import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
const panel = { background: '#fff', border: '1px solid #ddd', padding: 20, marginBottom: 16 };
const grid = { display: 'grid', gap: 12 };

export default function SolverCompetencies({ solverId, canManage, attempts = [], perform, busy }) {
  const [data, setData] = useState(null); const [error, setError] = useState('');
  const [documents, setDocuments] = useState([]);
  const [form, setForm] = useState({ kind: 'Competency', name: '', status: 'Pending', assessment_id: '', document_id: '', reference: '' });
  useEffect(() => { let cancelled = false; Promise.all([api.getSolverCompetencies(solverId), canManage ? api.getSolverDocuments(solverId) : { data: [] }]).then(([result, docs]) => { if (!cancelled) { if (!result.data) throw new Error(); setData(result.data); setDocuments(docs.data || []); } }).catch(() => { if (!cancelled) setError('Unable to load competency records.'); }); return () => { cancelled = true; }; }, [solverId, canManage]);
  return <section style={panel}><h2>Competencies, qualifications & certifications</h2>{error && <p role="alert">{error}</p>}{!data && !error && <p>Loading competency records...</p>}{data && <>
    {data.items.length ? <ul>{data.items.map(item => <li key={item.id}>{item.kind}: {item.name} — {item.status}{item.expires_on && ` / expiry ${item.expires_on}`}</li>)}</ul> : <p>No verified competency records recorded.</p>}<p>{data.legacy_notice}</p>
    {canManage && <form style={grid} onSubmit={e => { e.preventDefault(); perform(() => api.recordSolverCompetency(solverId, { ...form, assessment_id: form.assessment_id || undefined })); }}>
      {['kind', 'status'].map(key => <label key={key}>{key} <select value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}>{(key === 'kind' ? ['Competency', 'Qualification', 'Certification'] : ['Pending', 'Verified', 'Expired', 'Revoked']).map(value => <option key={value}>{value}</option>)}</select></label>)}
      <label>Documented name <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
      <label>Released assessment <select value={form.assessment_id} onChange={e => setForm({ ...form, assessment_id: e.target.value })}><option value="">Choose if required</option>{attempts.filter(item => item.subject_solver_id === solverId && item.status === 'Released').map(item => <option key={item.id} value={item.id}>{item.title} / {item.outcome}</option>)}</select></label>
      <label>Verified document <select required value={form.document_id} onChange={e => setForm({ ...form, document_id: e.target.value })}><option value="">Choose evidence</option>{documents.map(doc => <option key={doc.id} value={doc.id}>{doc.file_name}</option>)}</select></label>
      <label>Policy / verification reference <input required value={form.reference} onChange={e => setForm({ ...form, reference: e.target.value })} /></label>
      <label>Evidence expiry (if documented) <input type="date" value={form.expires_on || ''} onChange={e => { const next = { ...form }; if (e.target.value) next.expires_on = e.target.value; else delete next.expires_on; setForm(next); }} /></label>
      <button disabled={busy}>Record documented verification</button>
    </form>}
  </>}</section>;
}
