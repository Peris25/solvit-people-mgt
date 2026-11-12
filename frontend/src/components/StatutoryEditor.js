import React, { useEffect, useRef, useState } from 'react';
import * as api from '../services/api';

const fields = [
  ['national_id_number', 'National ID', 40], ['kra_pin', 'KRA PIN', 30],
  ['nssf_number', 'NSSF', 40], ['sha_number', 'SHA', 40],
  ['date_of_birth', 'Date of birth', 10], ['gender', 'Gender', 60],
];
const values = employee => Object.fromEntries(fields.map(([field]) => [field, employee[field] || '']));

export default function StatutoryEditor({ employee, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => values(employee));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const save = async event => {
    event.preventDefault(); setError(''); setSuccess('');
    const original = values(employee);
    const changes = Object.fromEntries(Object.entries(form).map(([field, value]) => [field, value.trim()])
      .filter(([field, value]) => value !== original[field]));
    if (!Object.keys(changes).length) { setEditing(false); return; }
    setSaving(true);
    try {
      const response = await api.updateEmployee(employee.id, changes);
      if (mounted.current) {
        onSaved({ ...changes, ...response.data }); setEditing(false); setSuccess('Statutory information saved.');
      }
    } catch (err) {
      if (mounted.current) {
        const detail = err?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Statutory information could not be saved. Please try again.');
      }
    } finally { if (mounted.current) setSaving(false); }
  };

  if (!editing) return <>
    <button type="button" onClick={() => { setForm(values(employee)); setError(''); setSuccess(''); setEditing(true); }} style={{ padding: '10px 14px', marginTop: 12 }}>Edit statutory information</button>
    {success && <p role="status">{success}</p>}
  </>;

  return <form onSubmit={save} aria-label="Edit statutory information" style={{ marginTop: 16 }}>
    <fieldset disabled={saving} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <legend style={{ fontWeight: 700, marginBottom: 12 }}>Edit personal &amp; statutory information</legend>
      {fields.map(([field, label, maxLength]) => <label key={field} style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
        {label}<input aria-label={label} type={field === 'date_of_birth' ? 'date' : 'text'} maxLength={maxLength}
          value={form[field]} onChange={event => setForm(previous => ({ ...previous, [field]: event.target.value }))}
          style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: 10, marginTop: 4 }} />
      </label>)}
      {error && <p role="alert">{error}</p>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button type="submit" style={{ padding: '10px 14px' }}>{saving ? 'Saving…' : 'Save statutory information'}</button>
        <button type="button" onClick={() => { setEditing(false); setError(''); }} style={{ padding: '10px 14px' }}>Cancel</button>
      </div>
    </fieldset>
  </form>;
}
