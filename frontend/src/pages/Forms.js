import React, { useState, useEffect } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Forms() {
  const { user } = useAuth();
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [schema, setSchema] = useState(null);
  const [responses, setResponses] = useState({});
  const [signature, setSignature] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [filter, setFilter] = useState('all');

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { const r = await api.getForms(); setForms(r.data); }
    finally { setLoading(false); }
  };

  const openForm = async (form) => {
    setResult(null);
    setResponses({});
    setSignature('');
    setSelected(form);
    try {
      const r = await api.getFormSchema(form.id);
      setSchema(r.data);
    } catch { setSchema(null); }
  };

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await api.submitForm(selected.id, {
        data: responses,
        signatures: signature ? { primary: signature } : {}
      });
      setResult(res.data);
    } catch (err) {
      alert(err.response?.data?.detail || 'Submission failed');
    } finally { setSubmitting(false); }
  };

  const setField = (id, val) => setResponses(p => ({ ...p, [id]: val }));

  const filtered = filter === 'all' ? forms : forms.filter(f => f.target_role === filter);

  const renderField = (field) => {
    const val = responses[field.id] || '';
    const baseStyle = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', fontFamily: 'Arial' };

    if (field.readonly || field.auto_populated || field.auto_calculated) {
      return <input data-testid={`field-${field.id}`} disabled value={val} placeholder={`(${field.auto_calculated ? 'auto-calculated' : 'auto-populated'})`} style={{ ...baseStyle, backgroundColor: '#F5F5F5', color: '#9CA3AF' }} />;
    }
    if (field.type === 'textarea') return <textarea data-testid={`field-${field.id}`} required={field.required} value={val} onChange={e => setField(field.id, e.target.value)} rows={3} style={{ ...baseStyle, resize: 'vertical' }} />;
    if (field.type === 'dropdown' || field.type === 'select') return <select data-testid={`field-${field.id}`} required={field.required} value={val} onChange={e => setField(field.id, e.target.value)} style={baseStyle}><option value="">Select...</option>{(field.options || []).map(o => <option key={o}>{o}</option>)}</select>;
    if (field.type === 'radio') return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {(field.options || []).map(o => (
          <label key={o} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', cursor: 'pointer' }}>
            <input type="radio" name={field.id} value={o} checked={val === o} onChange={e => setField(field.id, e.target.value)} required={field.required} />{o}
          </label>
        ))}
      </div>
    );
    if (field.type === 'multi_checkbox') return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {(field.options || []).map(o => {
          const arr = Array.isArray(val) ? val : [];
          return (
            <label key={o} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}>
              <input type="checkbox" checked={arr.includes(o)} onChange={() => setField(field.id, arr.includes(o) ? arr.filter(x => x !== o) : [...arr, o])} />{o}
            </label>
          );
        })}
      </div>
    );
    if (field.type === 'likert_5') return (
      <div style={{ display: 'flex', gap: '6px' }}>
        {[1, 2, 3, 4, 5].map(n => (
          <label key={n} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', cursor: 'pointer', padding: '8px', border: val === n ? '2px solid #FF353F' : '1px solid rgba(25,25,25,0.15)', backgroundColor: val === n ? '#FFEEEF' : 'transparent' }}>
            <input type="radio" name={field.id} checked={val === n} onChange={() => setField(field.id, n)} required={field.required} style={{ display: 'none' }} />
            <span style={{ fontSize: '16px', fontWeight: 900 }}>{n}</span>
            <span style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{['Strongly Disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly Agree'][n - 1]}</span>
          </label>
        ))}
      </div>
    );
    return <input data-testid={`field-${field.id}`} type={field.type === 'phone' ? 'tel' : field.type} required={field.required} value={val} onChange={e => setField(field.id, field.type === 'number' ? parseFloat(e.target.value) || '' : e.target.value)} min={field.min} max={field.max} style={baseStyle} />;
  };

  const roles = [...new Set(forms.map(f => f.target_role).filter(Boolean))];

  return (
    <div data-testid="forms-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Forms Library</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>{forms.length} form schemas — Intelligent Forms Engine</p>
      </div>

      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <button onClick={() => setFilter('all')} style={{ padding: '4px 10px', backgroundColor: filter === 'all' ? '#FF353F' : 'transparent', color: filter === 'all' ? '#fff' : '#525252', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.05em' }}>All ({forms.length})</button>
        {roles.map(r => (
          <button key={r} onClick={() => setFilter(r)} style={{ padding: '4px 10px', backgroundColor: filter === r ? '#191919' : 'transparent', color: filter === r ? '#fff' : '#525252', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{r} ({forms.filter(f => f.target_role === r).length})</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {filtered.map(f => (
            <div key={f.id} data-testid={`form-${f.id}`} onClick={() => openForm(f)} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px', cursor: 'pointer', transition: 'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#FF353F'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(25,25,25,0.08)'}
            >
              <div style={{ fontSize: '10px', fontWeight: 700, color: '#FF353F', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '4px' }}>{f.id}</div>
              <div style={{ fontSize: '13px', fontWeight: 900, color: '#191919', marginBottom: '6px', letterSpacing: '-0.02em' }}>{f.title}</div>
              <div style={{ fontSize: '11px', color: '#525252', lineHeight: 1.5 }}>{f.description}</div>
              {f.target_role && <div style={{ marginTop: '8px', fontSize: '10px', color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em' }}>For: {f.target_role}</div>}
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#fff', width: '700px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', position: 'sticky', top: 0, backgroundColor: '#fff', zIndex: 1 }}>
              <div>
                <div style={{ fontSize: '10px', fontWeight: 700, color: '#FF353F', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{selected.id}</div>
                <h3 style={{ margin: 0, fontWeight: 900, fontSize: '18px', letterSpacing: '-0.02em' }}>{schema?.title || selected.title}</h3>
                <p style={{ fontSize: '12px', color: '#525252', margin: '4px 0 0' }}>{schema?.description || selected.description}</p>
              </div>
              <button onClick={() => { setSelected(null); setSchema(null); setResult(null); }} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer' }}>×</button>
            </div>
            {result ? (
              <div style={{ padding: '32px', textAlign: 'center' }}>
                <div style={{ fontSize: '32px', fontWeight: 900, color: '#22C55E', marginBottom: '8px' }}>✓ Submitted</div>
                <p style={{ fontSize: '14px', color: '#525252' }}>Submission ID: <code>{result.id}</code></p>
                {result.score !== undefined && <p style={{ fontSize: '14px', marginTop: '12px' }}>Score: <strong style={{ fontSize: '20px', color: result.passed ? '#22C55E' : '#FF353F' }}>{result.score} / {result.pass_mark || schema?.total_marks}</strong> {result.passed ? '— PASSED' : '— FAILED'}</p>}
                <button onClick={() => { setSelected(null); setSchema(null); setResult(null); }} style={{ marginTop: '24px', padding: '10px 24px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Close</button>
              </div>
            ) : (
              <form onSubmit={submit} style={{ padding: '24px' }}>
                {!schema || !(schema.sections || []).length || (schema.sections || []).every(s => !(s.fields || []).length) ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px', backgroundColor: '#FAFAFA', border: '1px solid rgba(25,25,25,0.05)' }}>
                    Form schema not yet implemented — placeholder ready (FRD Section 7).
                  </div>
                ) : (schema.sections || []).map(section => (
                  <div key={section.id} style={{ marginBottom: '24px' }}>
                    <h4 style={{ fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#191919', marginBottom: '12px', paddingBottom: '6px', borderBottom: '1px solid rgba(25,25,25,0.1)' }}>{section.title}</h4>
                    {(section.fields || []).map(field => (
                      <div key={field.id} style={{ marginBottom: '14px' }}>
                        <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#191919', marginBottom: '6px' }}>{field.label}{field.required && <span style={{ color: '#FF353F' }}> *</span>}</label>
                        {renderField(field)}
                      </div>
                    ))}
                  </div>
                ))}
                {schema?.requires_signatures && (
                  <div style={{ marginBottom: '20px', padding: '14px', backgroundColor: '#FAFAFA', border: '1px solid rgba(25,25,25,0.08)' }}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '6px' }}>Digital Signature (type your full name)</label>
                    <input data-testid="form-signature" required value={signature} onChange={e => setSignature(e.target.value)} placeholder="Your full name" style={{ width: '100%', padding: '10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '14px', fontFamily: 'cursive', boxSizing: 'border-box' }} />
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <button type="button" onClick={() => { setSelected(null); setSchema(null); }} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                  <button data-testid="submit-form-btn" type="submit" disabled={submitting} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{submitting ? 'Submitting...' : 'Submit Form'}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
