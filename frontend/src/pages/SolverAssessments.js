import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Competencies from '../components/SolverCompetencies';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

const panel = { background: '#fff', border: '1px solid #ddd', padding: 20, marginBottom: 16 };
const grid = { display: 'grid', gap: 12 };
const button = { background: '#FF353F', color: '#fff', border: 0, padding: '10px 16px', cursor: 'pointer' };
const emptyConfiguration = () => ({ title: '', approval_reference: '', pass_mark: '', resit_wait_days: '', time_limits: {}, eligibility: {}, certification_categories: [], sections: ['A', 'B'].map(part => ({ id: `part_${part}`, title: `Part ${part}`, part, weight: '', questions: [] })) });
const copy = value => JSON.parse(JSON.stringify(value));
const errorText = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'The action could not be completed. Refresh before retrying.';
const download = async (id, documentId) => {
  const response = await api.downloadSolverAssessmentEvidence(id, documentId);
  const url = URL.createObjectURL(response.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'Assessment evidence'; anchor.click(); URL.revokeObjectURL(url);
};

export default function SolverAssessments() {
  const { user } = useAuth();
  return <Workspace key={`${user?.id}:${user?.role}`} user={user} />;
}

function Workspace({ user }) {
  const [capabilities, setCapabilities] = useState(null);
  const [attempts, setAttempts] = useState([]);
  const [configurations, setConfigurations] = useState([]);
  const [options, setOptions] = useState({ assessors: [] });
  const [solvers, setSolvers] = useState([]);
  const [selected, setSelected] = useState(new URLSearchParams(window.location.search).get('assessment') || '');
  const [filter, setFilter] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError('');
    const load = async () => {
      try {
        const caps = (await api.getSolverAssessmentCapabilities()).data;
        if (!caps) throw new Error();
        const [rows, configs, admin, people] = await Promise.all([
          api.getSolverAssessmentAttempts(),
          caps.can_configure ? api.getSolverAssessmentConfigurations() : { data: [] },
          caps.can_assign ? api.getSolverAssessmentOptions() : { data: { assessors: [] } },
          caps.can_assign ? api.getSolvers() : { data: [] },
        ]);
        if (cancelled) return;
        if (!Array.isArray(rows.data) || !Array.isArray(configs.data) || !admin.data || !Array.isArray(people.data)) throw new Error();
        setCapabilities(caps); setAttempts(rows.data); setConfigurations(configs.data); setOptions(admin.data); setSolvers(people.data);
      } catch { if (!cancelled) { setCapabilities(null); setAttempts([]); setError('Unable to load authorized Solver assessments. Please retry.'); } }
      finally { if (!cancelled) setLoading(false); }
    };
    load(); return () => { cancelled = true; };
  }, [revision]);
  const perform = async action => {
    setBusy(true); setError('');
    try { const result = await action(); if (result?.data?.id && result.data.revision != null) { setAttempts(previous => [result.data, ...previous.filter(item => item.id !== result.data.id)]); setSelected(result.data.id); } else setRevision(value => value + 1); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const current = attempts.find(row => row.id === selected);
  return <div style={{ fontFamily: 'Arial, Helvetica, sans-serif', ...grid }}>
    <h1>Solver assessments & competencies</h1>
    <p>Assigned assessments use approved, versioned settings. Existing assessment history remains in Solver profiles.</p>
    <Link to="/solvers">Solver profiles, induction & documents</Link>
    {error && <p role="alert">{error}</p>}
    {loading && <p>Loading assessments...</p>}
    {!loading && !capabilities && <button onClick={() => setRevision(value => value + 1)}>Retry</button>}
    {capabilities && <>
      {capabilities.can_configure && <ConfigurationEditor configurations={configurations} canPublish={capabilities.can_publish} perform={perform} busy={busy} />}
      {capabilities.can_assign && <Assignment configurations={configurations} options={options} solvers={solvers} perform={perform} busy={busy} />}
      <section style={panel}>
        <h2>{capabilities.is_solver ? 'My assigned assessments' : 'Assessment oversight'}</h2>
        <label>Status <select value={filter} onChange={e => setFilter(e.target.value)}><option value="">All statuses</option>{['Assigned', 'InProgress', 'AwaitingScoring', 'Scored', 'Released', 'Needs administrator review'].map(value => <option key={value}>{value}</option>)}</select></label>
        {attempts.filter(row => !filter || row.status === filter).length === 0 && <p>No assessments recorded for this view.</p>}
        <div style={{ ...grid, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', marginTop: 16 }}>{attempts.filter(row => !filter || row.status === filter).map(row => <button key={row.id} onClick={() => setSelected(row.id)} style={{ ...panel, textAlign: 'left', cursor: 'pointer' }}><strong>{row.title}</strong><div>Version {row.configuration_version} / {row.status}</div><div>Deadline: {row.due_at ? new Date(row.due_at).toLocaleString() : 'Not recorded'}</div>{row.score != null && <div>Score: {row.score} / 100 — {row.outcome}</div>}</button>)}</div>
      </section>
      {current && <Attempt key={`${current.id}:${current.revision}`} row={current} isSolver={capabilities.is_solver} perform={perform} busy={busy} />}
      {current && (capabilities.is_solver || capabilities.can_assign) && <Competencies key={`${current.subject_solver_id}:${revision}`} solverId={current.subject_solver_id} canManage={capabilities.can_assign} attempts={attempts} perform={perform} busy={busy} />}
    </>}
  </div>;
}

function ConfigurationEditor({ configurations, canPublish, perform, busy }) {
  const [open, setOpen] = useState(false);
  const [previous, setPrevious] = useState('');
  const [settings, setSettings] = useState(emptyConfiguration);
  const sequence = useRef(0);
  const update = (key, value) => setSettings(old => ({ ...old, [key]: value }));
  const section = (index, key, value) => setSettings(old => ({ ...old, sections: old.sections.map((item, i) => i === index ? { ...item, [key]: value } : item) }));
  const question = (si, qi, key, value) => section(si, 'questions', settings.sections[si].questions.map((item, i) => i === qi ? { ...item, [key]: value } : item));
  const save = event => {
    event.preventDefault();
    const draft = copy(settings);
    for (const key of ['pass_mark', 'resit_wait_days']) if (draft[key] === '') delete draft[key]; else draft[key] = Number(draft[key]);
    if (!draft.approval_reference) delete draft.approval_reference;
    Object.keys(draft.time_limits).forEach(key => { if (draft.time_limits[key] === '') delete draft.time_limits[key]; else draft.time_limits[key] = Number(draft.time_limits[key]); });
    if (draft.borderline) draft.borderline = { minimum: Number(draft.borderline.minimum), maximum: Number(draft.borderline.maximum) };
    for (const item of draft.sections) {
      if (item.weight === '') delete item.weight; else item.weight = Number(item.weight);
      for (const q of item.questions) {
        if (q.scoring === 'none') { delete q.points; delete q.rubric; delete q.correct_answer; delete q.tolerance_bands; }
        if (q.scoring === 'manual') { delete q.correct_answer; delete q.tolerance_bands; }
        if (q.type !== 'choice') delete q.options;
      }
    }
    perform(async () => {
      const response = await api.saveSolverAssessmentConfiguration(draft, previous || undefined);
      if (response.data?.id) setPrevious(response.data.id);
      return response;
    });
  };
  return <section style={panel}>
    <h2>Approved assessment settings</h2>
    <p>No live questions, weights or pass marks are supplied by the application. Drafts cannot be assigned. Changes create a new version.</p>
    <button onClick={() => setOpen(value => !value)}>{open ? 'Close settings editor' : 'Open settings editor'}</button>
    {configurations.map(item => <div key={item.id} style={{ padding: '12px 0' }}>{item.title} — v{item.version} / {item.status}
      <button disabled={busy} onClick={() => { setSettings({ ...emptyConfiguration(), ...copy(item.settings) }); setPrevious(item.id); setOpen(true); }}>Create revised version</button>
      {canPublish && item.status === 'Draft' && item.publication_state === 'Ready' && <button disabled={busy} onClick={() => perform(() => api.publishSolverAssessmentConfiguration(item.id))}>Publish approved version</button>}
    </div>)}
    {open && <form onSubmit={save} style={grid}>
      <label>Assessment title <input required value={settings.title} onChange={e => update('title', e.target.value)} /></label>
      <label>HR approval reference <input value={settings.approval_reference || ''} onChange={e => update('approval_reference', e.target.value)} /></label>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{['pass_mark', 'resit_wait_days'].map(key => <label key={key}>{key === 'pass_mark' ? 'Approved pass mark (%)' : 'Approved re-sit wait (days)'} <input type="number" min="0" value={settings[key] ?? ''} onChange={e => update(key, e.target.value)} /></label>)}</div>
      <div style={{ display: 'flex', gap: 12 }}>{['A', 'B'].map(part => <label key={part}>Part {part} time limit (minutes) <input type="number" min="0.01" step="any" value={settings.time_limits[part] ?? ''} onChange={e => update('time_limits', { ...settings.time_limits, [part]: e.target.value })} /></label>)}</div>
      <fieldset><legend>Approved lifecycle eligibility</legend>{['Registering', 'Active'].map(state => <label key={state}><input type="checkbox" checked={(settings.eligibility.states || []).includes(state)} onChange={e => { const states = e.target.checked ? [...(settings.eligibility.states || []), state] : settings.eligibility.states.filter(item => item !== state); update('eligibility', states.length ? { ...settings.eligibility, states } : {}); }} />{state}</label>)}</fieldset>
      <label>Eligible regions (optional; one per line) <textarea value={(settings.eligibility.regions || []).join('\n')} onChange={e => { const next = { ...settings.eligibility }; const values = e.target.value.split('\n').filter(Boolean); if (values.length) next.regions = values; else delete next.regions; update('eligibility', next); }} /></label>
      <fieldset><legend>Approved vehicle-category certification rules</legend><p>Select only categories explicitly authorized by the approved assessment policy. A pass never assigns a certificate automatically.</p>{['Saloon', 'SUV', 'Pick-Up', 'Van', 'Truck', 'Motorcycle'].map(value => <label key={value}><input type="checkbox" checked={(settings.certification_categories || []).includes(value)} onChange={e => update('certification_categories', e.target.checked ? [...settings.certification_categories, value] : settings.certification_categories.filter(item => item !== value))} />{value}</label>)}</fieldset>
      <label><input type="checkbox" checked={!!settings.borderline} onChange={e => { const next = { ...settings }; if (e.target.checked) next.borderline = { minimum: '', maximum: '' }; else delete next.borderline; setSettings(next); }} />Approved borderline range requires independent Technical Manager review</label>
      {settings.borderline && <div>{['minimum', 'maximum'].map(key => <label key={key}>Borderline {key} (%) <input required type="number" min="0" max="100" step="any" value={settings.borderline[key]} onChange={e => update('borderline', { ...settings.borderline, [key]: e.target.value })} /></label>)}</div>}
      {settings.sections.map((item, si) => <fieldset key={item.id} style={grid}><legend>{item.title} — component {item.part}</legend>
        <label>Section title <input required value={item.title} onChange={e => section(si, 'title', e.target.value)} /></label>
        <label>Approved weight (%) <input type="number" min="0.0001" max="100" step="any" value={item.weight ?? ''} onChange={e => section(si, 'weight', e.target.value)} /></label>
        {item.questions.map((q, qi) => <div key={q.id} style={{ ...grid, borderTop: '1px solid #ddd', paddingTop: 12 }}>
          <label>Approved question <textarea required value={q.label} onChange={e => question(si, qi, 'label', e.target.value)} /></label>
          <label>Answer type <select value={q.type} onChange={e => question(si, qi, 'type', e.target.value)}>{['text', 'choice', 'number', 'document'].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Scoring <select value={q.scoring} onChange={e => question(si, qi, 'scoring', e.target.value)}><option value="manual">Assessor rubric</option><option value="auto">Approved answer key</option><option value="none">Unscored</option></select></label>
          <label><input type="checkbox" checked={q.required} onChange={e => question(si, qi, 'required', e.target.checked)} />Required answer</label>
          {q.scoring !== 'none' && <label>Maximum approved points <input required type="number" min="0.0001" step="any" value={q.points ?? ''} onChange={e => question(si, qi, 'points', e.target.value === '' ? undefined : Number(e.target.value))} /></label>}
          {q.type === 'choice' && <label>Approved choices (one per line) <textarea required value={(q.options || []).join('\n')} onChange={e => question(si, qi, 'options', e.target.value.split('\n'))} /></label>}
          {q.scoring === 'auto' && <label>Confidential approved answer key <input required type={q.type === 'number' ? 'number' : 'text'} step="any" value={q.correct_answer ?? ''} onChange={e => question(si, qi, 'correct_answer', q.type === 'number' ? Number(e.target.value) : e.target.value)} /></label>}
          {q.scoring === 'auto' && q.type === 'number' && <div><p>Approved absolute-difference tolerance bands (optional; otherwise exact match).</p>{(q.tolerance_bands || []).map((band, bi) => <div key={bi}>{['max_difference', 'points'].map(key => <label key={key}>{key === 'points' ? 'Awarded points' : 'Maximum difference from reference'} <input required type="number" min="0" step="any" value={band[key] ?? ''} onChange={e => question(si, qi, 'tolerance_bands', q.tolerance_bands.map((item, index) => index === bi ? { ...item, [key]: Number(e.target.value) } : item))} /></label>)}</div>)}<button type="button" onClick={() => question(si, qi, 'tolerance_bands', [...(q.tolerance_bands || []), {}])}>Add approved tolerance band</button></div>}
          {q.scoring === 'manual' && <label>Approved assessor rubric <textarea required value={q.rubric || ''} onChange={e => question(si, qi, 'rubric', e.target.value)} /></label>}
          <label>Documented competency (optional) <input value={q.competency || ''} onChange={e => { const next = { ...q }; if (e.target.value) next.competency = e.target.value; else delete next.competency; section(si, 'questions', item.questions.map((value, index) => index === qi ? next : value)); }} /></label>
          <button type="button" onClick={() => section(si, 'questions', item.questions.filter((_, index) => index !== qi))}>Retire from this new version</button>
        </div>)}
        <button type="button" onClick={() => { sequence.current += 1; section(si, 'questions', [...item.questions, { id: `q_${Date.now()}_${sequence.current}`, label: '', type: 'text', scoring: 'manual', required: false }]); }}>Add approved question to {item.title}</button>
      </fieldset>)}
      {['A', 'B'].map(part => <button key={part} type="button" onClick={() => { sequence.current += 1; update('sections', [...settings.sections, { id: `section_${Date.now()}_${sequence.current}`, title: '', part, weight: '', questions: [] }]); }}>Add Part {part} section</button>)}
      <button style={button} disabled={busy}>Save new draft version</button>
      <button type="button" onClick={() => { setSettings(emptyConfiguration()); setPrevious(''); }}>Start separate assessment bank</button>
    </form>}
  </section>;
}

function Assignment({ configurations, options, solvers, perform, busy }) {
  const [form, setForm] = useState({ configuration_id: '', solver_id: '', assessor_id: '', reviewer_id: '', due_at: '', interview_reference: '' });
  return <section style={panel}><h2>Assign an approved assessment</h2><form style={grid} onSubmit={e => { e.preventDefault(); perform(() => api.assignSolverAssessment({ ...form, due_at: new Date(form.due_at).toISOString(), reviewer_id: form.reviewer_id || undefined })); }}>
    <label>Published version <select required value={form.configuration_id} onChange={e => setForm({ ...form, configuration_id: e.target.value })}><option value="">Choose approved version</option>{configurations.filter(item => item.status === 'Published' && item.publication_state === 'Ready').map(item => <option key={item.id} value={item.id}>{item.title} / v{item.version}</option>)}</select></label>
    <label>Solver <select required value={form.solver_id} onChange={e => setForm({ ...form, solver_id: e.target.value })}><option value="">Choose Solver</option>{solvers.map(item => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label>
    {['assessor_id', 'reviewer_id'].map(key => <label key={key}>{key === 'assessor_id' ? 'Assigned assessor' : 'Independent Technical Manager (if required)'} <select required={key === 'assessor_id'} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}><option value="">Choose authorized account</option>{options.assessors.filter(item => key === 'assessor_id' || item.technical_reviewer).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>)}
    <label>Deadline (your local time) <input required type="datetime-local" value={form.due_at} onChange={e => setForm({ ...form, due_at: e.target.value })} /></label>
    <label>Passed-interview verification reference <input required value={form.interview_reference} onChange={e => setForm({ ...form, interview_reference: e.target.value })} /></label>
    <button style={button} disabled={busy}>Assign assessment</button>
  </form></section>;
}

function Attempt({ row, isSolver, perform, busy }) {
  const [answers, setAnswers] = useState(row.answers || {});
  const [marks, setMarks] = useState(row.marks || {});
  const [notes, setNotes] = useState('');
  const [documents, setDocuments] = useState([]);
  useEffect(() => { let cancelled = false; if (isSolver) api.getSolverDocuments(row.subject_solver_id).then(result => { if (!cancelled) setDocuments((result.data || []).filter(doc => doc.visibility === 'hr_assessment')); }).catch(() => {}); return () => { cancelled = true; }; }, [isSolver, row.subject_solver_id]);
  return <section style={panel}><h2>{row.title} — {row.status}</h2>
    {row.score != null ? <p>Score {row.score} / 100 — {row.outcome}</p> : <p>Results will be visible after authorized release.</p>}
    {row.section_scores?.length > 0 && <ul aria-label="Assessment section results">{row.section_scores.map(section => <li key={section.id}>Part {section.part} / {section.title}: {section.points} / {section.maximum} ({Number(section.percentage).toFixed(2)}%)</li>)}</ul>}
    {['A', 'B'].map(part => {
      const info = row.parts?.[part]; const sections = row.configuration.sections.filter(item => item.part === part);
      const ended = info ? Math.min(new Date(row.due_at).getTime(), new Date(info.started_at).getTime() + row.configuration.time_limits[part] * 60000) : null;
      const canAnswer = isSolver && info && !info.submitted_at && ['Assigned', 'InProgress'].includes(row.status);
      const values = Object.fromEntries(sections.flatMap(item => item.questions).filter(q => Object.prototype.hasOwnProperty.call(answers, q.id)).map(q => [q.id, answers[q.id] === '' ? null : answers[q.id]]));
      return <fieldset key={part} style={{ ...grid, marginBottom: 16 }}><legend>Part {part}</legend>
        <p>Approved time limit: {row.configuration.time_limits[part]} minutes. {ended && `Ends: ${new Date(ended).toLocaleString()}`}{info?.submitted_at && ` / Submitted ${new Date(info.submitted_at).toLocaleString()}`}</p>
        {isSolver && !info && ['Assigned', 'InProgress'].includes(row.status) && <button disabled={busy || part === 'B' && !row.parts?.A?.submitted_at} onClick={() => perform(() => api.progressSolverAssessment(row.id, part, 'start', { revision: row.revision }))}>Start Part {part}</button>}
        {sections.map(section => <div key={section.id} style={grid}><h3>{section.title}</h3>{section.questions.map(q => <div key={q.id} style={grid}>
          <label>{q.label}{q.required ? ' (required)' : ''}
            {canAnswer ? q.type === 'choice' ? <select value={answers[q.id] ?? ''} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}><option value="">Choose an answer</option>{q.options.map(value => <option key={value}>{value}</option>)}</select> : q.type === 'document' ? <select value={answers[q.id] ?? ''} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}><option value="">Choose HR-shared assessment evidence</option>{documents.map(doc => <option key={doc.id} value={doc.id}>{doc.file_name}</option>)}</select> : q.type === 'number' ? <input type="number" step="any" value={answers[q.id] ?? ''} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value === '' ? '' : Number(e.target.value) })} /> : <textarea value={answers[q.id] ?? ''} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })} /> : <p>{row.answers?.[q.id] ?? 'No answer recorded'}</p>}
          </label>
          {!isSolver && q.rubric && <p>Approved rubric: {q.rubric}</p>}
          {!isSolver && q.correct_answer != null && <p>Confidential reference: {String(q.correct_answer)}</p>}
          {q.type === 'document' && row.answers?.[q.id] && <button disabled={busy} onClick={() => perform(() => download(row.id, row.answers[q.id]))}>Download authorized assessment evidence</button>}
          {row.can_score && q.scoring === 'manual' && <label>Assessor mark / {q.points} <input type="number" min="0" max={q.points} step="any" value={marks[q.id] ?? ''} onChange={e => setMarks({ ...marks, [q.id]: Number(e.target.value) })} /></label>}
        </div>)}</div>)}
        {canAnswer && <div><button disabled={busy} onClick={() => perform(() => api.progressSolverAssessment(row.id, part, 'save', { revision: row.revision, answers: values }))}>Save Part {part} progress</button><button disabled={busy} onClick={() => perform(() => api.progressSolverAssessment(row.id, part, 'submit', { revision: row.revision, answers: Date.now() >= ended ? {} : values }))}>Submit Part {part}</button></div>}
      </fieldset>;
    })}
    {(row.can_score || row.can_review) && <label>Assessment / review notes <textarea value={notes} onChange={e => setNotes(e.target.value)} /></label>}
    {row.can_score && <button style={button} disabled={busy} onClick={() => perform(() => api.decideSolverAssessment(row.id, 'score', { revision: row.revision, marks, notes }))}>Submit assessor scoring</button>}
    {row.can_review && <button disabled={busy} onClick={() => perform(() => api.decideSolverAssessment(row.id, 'review', { revision: row.revision, notes }))}>Confirm independent borderline review</button>}
    {row.can_release && <button style={button} disabled={busy} onClick={() => perform(() => api.decideSolverAssessment(row.id, 'release', { revision: row.revision }))}>Release approved result</button>}
  </section>;
}
