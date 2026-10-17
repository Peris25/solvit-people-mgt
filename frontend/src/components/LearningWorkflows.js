import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import EmployeePicker from './EmployeePicker';
import * as api from '../services/api';

const field = { display: 'grid', gap: 5, marginBottom: 12 };
const button = { minHeight: 44, padding: '8px 14px', cursor: 'pointer' };
const message = error => typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'The learning update could not be saved.';

export function TrainingCatalogue({ user, onUpdated }) {
  const hr = ['hr_admin', 'hr_manager'].includes(user?.role);
  const blank = { title:'', kind:'Course', parent_id:'', description:'', provider:'', delivery_method:'Internal', location:'', starts_on:'', ends_on:'', due_on:'', departments:[], employment_types:[], completion_requirements:'', evidence_required:false, cost_kes:0, duration_days:1, status:'Draft' };
  const [items, setItems] = useState([]);
  const [values, setValues] = useState(blank);
  const [editing, setEditing] = useState('');
  const [employee, setEmployee] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { setLoading(true); try { setItems((await api.getTrainingProgrammes()).data); } catch { setError('Unable to load the training catalogue.'); } finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const perform = async action => { setBusy(true); setError(''); try { await action(); await load(); await onUpdated(); } catch (e) { setError(message(e)); } finally { setBusy(false); } };
  const change = (key, value) => setValues(previous => ({ ...previous, [key]: value }));
  return <section style={{ background:'#fff', padding:20 }}>
    <h2>Training programmes, courses & sessions</h2>
    {error && <p role="alert">{error} <button onClick={load}>Retry</button></p>}
    {hr && <details open={Boolean(editing)}><summary>{editing ? 'Edit training catalogue item' : 'Create training catalogue item (HR)'}</summary>
      <form onSubmit={e => { e.preventDefault(); perform(async () => { const data = { ...values, parent_id:values.parent_id || null, departments:values.departments.map(v => v.trim()).filter(Boolean), employment_types:values.employment_types.map(v => v.trim()).filter(Boolean) }; if (editing) { await api.updateTrainingProgramme(editing, data); } else { await api.createTrainingProgramme(data); } setEditing(''); setValues(blank); }); }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))', gap:12 }}>
          <label style={field}>Type<select disabled={Boolean(editing)} value={values.kind} onChange={e => setValues(previous => ({ ...previous, kind:e.target.value, parent_id:'' }))}>{['Programme','Course','Session'].map(kind => <option key={kind}>{kind}</option>)}</select></label>
          <label style={field}>Parent<select disabled={Boolean(editing) || values.kind === 'Programme'} value={values.parent_id || ''} onChange={e => change('parent_id', e.target.value)}><option value="">No parent</option>{items.filter(item => item.kind === (values.kind === 'Session' ? 'Course' : 'Programme')).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
          {[['title','Title'],['provider','Provider'],['delivery_method','Delivery'],['location','Location']].map(([key,label]) => <label key={key} style={field}>{label}<input required={key !== 'location'} value={values[key] || ''} onChange={e => change(key,e.target.value)} /></label>)}
          {[['starts_on','Start date'],['ends_on','End date'],['due_on','Completion deadline']].map(([key,label]) => <label key={key} style={field}>{label}<input required={values.kind !== 'Programme'} type="date" value={values[key] || ''} onChange={e => change(key,e.target.value)} /></label>)}
          <label style={field}>Cost KES (0 for free)<input type="number" min="0" required value={values.cost_kes} onChange={e => change('cost_kes',Number(e.target.value))} /></label>
          <label style={field}>Duration (whole days)<input type="number" min="1" step="1" required value={values.duration_days} onChange={e => change('duration_days',Number(e.target.value))} /></label>
        </div>
        <label style={field}>Description<textarea required value={values.description} onChange={e => change('description',e.target.value)} /></label>
        <label style={field}>Completion requirements<textarea required value={values.completion_requirements} onChange={e => change('completion_requirements',e.target.value)} /></label>
        <label style={field}>Eligible departments (comma-separated; empty means all)<input value={values.departments.join(',')} onChange={e => change('departments',e.target.value.split(','))} /></label>
        <label style={field}>Employment types (comma-separated; empty means all)<input value={values.employment_types.join(',')} onChange={e => change('employment_types',e.target.value.split(','))} /></label>
        <label style={field}><span><input type="checkbox" checked={values.evidence_required} onChange={e => change('evidence_required',e.target.checked)} /> Authorized document evidence required</span></label>
        <label style={field}>Publication<select value={values.status} onChange={e => change('status',e.target.value)}>{['Draft','Published','Archived'].map(status => <option key={status}>{status}</option>)}</select></label>
        <p>Edits apply to future assignments. Existing training and document permissions remain intact.</p>
        <button style={button} disabled={busy}>{editing ? 'Save programme changes' : 'Create catalogue item'}</button>
        {editing && <button style={button} type="button" onClick={() => { setEditing(''); setValues(blank); }}>Cancel edit</button>}
      </form>
    </details>}
    {hr && <div style={{ margin:'20px 0' }}><label>Employee for assignment</label><EmployeePicker value={employee} onChange={value => setEmployee(value.id)} /></div>}
    {loading ? <p role="status">Loading catalogue...</p> : items.length === 0 ? <p>No eligible published training available.</p> : items.map(item => <article key={item.id} style={{ border:'1px solid #ddd', padding:16, marginTop:16 }}>
      <h3>{item.title} · {item.kind}</h3><p>{item.description}</p><p>{item.starts_on || 'Programme schedule pending'} to {item.ends_on || 'Awaiting HR'} · Due {item.due_on || 'Awaiting HR'}</p>
      <p>{item.completion_requirements}</p><p>{item.status} · {item.provider}</p>
      {hr ? <><button style={button} disabled={busy} onClick={() => { setEditing(item.id); setValues(Object.fromEntries(Object.keys(blank).map(key => [key,item[key] ?? blank[key]]))); }}>Edit catalogue item</button>
        {item.kind !== 'Programme' && item.status === 'Published' && <button style={button} disabled={busy || !employee} onClick={() => perform(() => api.assignTrainingProgramme(item.id,{ employee_ids:[employee], business_justification:'HR training nomination' }))}>Assign to employee</button>}</> : item.kind !== 'Programme' && <button style={button} disabled={busy || !user?.employee_id} onClick={() => perform(() => api.createTrainingRequest({ employee_id:user.employee_id, programme_id:item.id, business_justification:'Requested participation in published training' }))}>Request this training</button>}
    </article>)}
  </section>;
}

export function TrainingCompletion({ training, onUpdated }) {
  const [completedOn, setCompletedOn] = useState('');
  const [evidence, setEvidence] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [documents, setDocuments] = useState([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const perform = async action => { setBusy(true); setError(''); try { await action(); await onUpdated(); } catch(e) { setError(message(e)); } finally { setBusy(false); } };
  const submit = action => api.completeTraining(training.id,{ action, completed_on:completedOn, evidence, ...(documentId ? { document_id:documentId } : {}), ...(action === 'record' ? { requirements_met:true } : {}) });
  const download = async () => {
    const response = await api.downloadEmployeeDocument(training.completion_submission.document_id);
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a'); anchor.href=url; anchor.download='learning-evidence'; anchor.click(); URL.revokeObjectURL(url);
  };
  return <details><summary>Schedule, requirements & completion</summary>
    <p>{training.employee_name} · {training.proposed_start_date || 'Start awaiting confirmation'} to {training.proposed_end_date || 'End awaiting confirmation'}</p>
    <p>Deadline: {training.due_on || 'Awaiting confirmation'} · Completed: {training.completed_on || 'Not yet verified'}</p>
    <p>{training.completion_requirements || 'HR must confirm requirements for this historical record.'}</p>
    <Link to="/documents">Open Document Centre</Link>
    <p>Required files use existing HR upload and sharing approvals. No document is automatically published.</p>
    {error && <p role="alert">{error}</p>}
    {training.completion_return_reason && <p>HR feedback: {training.completion_return_reason}</p>}
    {training.completion_submission && <div><p>Completion declared: {training.completion_submission.completed_on}</p><p>{training.completion_submission.evidence}</p>
      {training.completion_submission.document_id && <button style={button} disabled={busy} onClick={() => perform(download)}>Download authorized evidence</button>}</div>}
    {(training.can_submit_completion || training.can_record_certificate) && <form onSubmit={e => { e.preventDefault(); perform(() => submit(training.can_submit_completion ? 'submit' : 'record')); }}>
      <label style={field}>Actual completion date<input type="date" required value={completedOn} onChange={e => setCompletedOn(e.target.value)} /></label>
      <label style={field}>Completion evidence<textarea required value={evidence} onChange={e => setEvidence(e.target.value)} /></label>
      <button style={button} type="button" disabled={busy} onClick={() => perform(async () => setDocuments((await api.getEmployeeDocuments(training.employee_id)).data))}>Load authorized documents</button>
      <label style={field}>Certificate / evidence<select required={training.evidence_required || training.can_record_certificate} value={documentId} onChange={e => setDocumentId(e.target.value)}><option value="">No document selected</option>{documents.filter(doc => doc.download_allowed).map(doc => <option key={doc.id} value={doc.id}>{doc.title || doc.file_name}</option>)}</select></label>
      <button style={button} disabled={busy}>{training.can_submit_completion ? 'Submit completion for HR verification' : 'Record verified external certificate'}</button>
    </form>}
    {training.can_verify_completion && <div><button style={button} disabled={busy} onClick={() => perform(() => api.completeTraining(training.id,{ action:'verify', requirements_met:true }))}>Verify requirements and completion</button>
      <label style={field}>Reason for returning<input value={reason} onChange={e => setReason(e.target.value)} /></label>
      <button style={button} disabled={busy || !reason.trim()} onClick={() => perform(() => api.completeTraining(training.id,{ action:'return', reason }))}>Return completion evidence</button></div>}
  </details>;
}
