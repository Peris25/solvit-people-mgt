import React, { useEffect, useRef, useState } from 'react';
import { Pencil, X, Plus, Trash2 } from 'lucide-react';
import * as api from '../services/api';
import { FieldError, FormNotice, fieldErrorsFrom } from './FormDialog';
import './ProfileCardEditor.css';

export const PROFILE_SECTIONS = {
  statutory: { title: 'Personal & statutory', saved: 'Statutory information saved.', fields: [
    ['national_id_number', 'National ID', 'text', 40], ['kra_pin', 'KRA PIN', 'text', 30],
    ['nssf_number', 'NSSF', 'text', 40], ['sha_number', 'SHA', 'text', 40],
    ['date_of_birth', 'Date of birth', 'date'], ['gender', 'Gender', ['Female', 'Male', 'Other', 'Prefer not to say']],
  ] },
  employment: { title: 'Employment', fields: [
    ['staff_id', 'Staff ID', 'text', 60], ['employment_type', 'Employment type', ['Full_Time', 'Part_Time', 'Fixed_Term']],
    ['start_date', 'Start date', 'date'], ['probation_end_date', 'Probation end date', 'date'],
    ['lifecycle_state', 'Lifecycle', ['Candidate', 'Onboarding', 'Probation', 'Active', 'Inactive', 'On_Leave', 'PIP', 'Realignment', 'Suspended', 'Notice_Period', 'Exiting', 'Exited']],
    ['project_ownership_eligible', 'Project eligible', 'checkbox'],
  ] },
  contacts: { title: 'Contacts & personal information', fields: [
    ['personal_email', 'Personal email', 'email', 254], ['phone_number', 'Phone number', 'tel', 30],
    ['next_of_kin', 'Next of kin', 'contact'], ['emergency_contact', 'Emergency contact', 'contact'],
    ['education', 'Education', 'education'],
  ] },
  bank: { title: 'Bank & payment', fields: [
    ['bank_name', 'Bank name', 'text', 120], ['bank_branch', 'Bank branch', 'text', 120],
    ['bank_account_number', 'Bank account number', 'text', 60], ['mpesa_number', 'M-Pesa number', 'tel', 30],
    ['payment_method', 'Payment method', ['Bank Transfer', 'M-Pesa']],
  ] },
};
const initialValues = (employee, fields) => Object.fromEntries(fields.map(([field, , type]) => {
  const legacy = { staff_id: 'employee_number', bank_account_number: 'bank_account', payment_method: 'preferred_payment_method' };
  const value = employee[field] ?? employee[legacy[field]] ?? (type === 'checkbox' ? false : type === 'contact' ? {} : type === 'education' ? [] : '');
  return [field, type === 'education' && Array.isArray(value)
    ? value.map(row => Object.fromEntries(['institution', 'qualification', 'year'].filter(key => row[key] != null).map(key => [key, String(row[key])]))) : value];
}));

export default function ProfileCardEditor({ employee, section, user, onSaved }) {
  const config = PROFILE_SECTIONS[section];
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const mounted = useRef(true);
  const dialog = useRef(null);
  const trigger = useRef(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!success) return undefined;
    const timer = setTimeout(() => setSuccess(''), 4500);
    return () => clearTimeout(timer);
  }, [success]);
  useEffect(() => {
    if (!editing) return undefined;
    const element = dialog.current;
    if (element.showModal) element.showModal(); else element.setAttribute('open', '');
    element.querySelector('input:not([disabled]),select:not([disabled]),textarea:not([disabled])')?.focus();
    const button = trigger.current;
    return () => { if (element.close) element.close(); button?.focus(); };
  }, [editing]);
  const setField = (field, value) => {
    setForm(previous => ({ ...previous, [field]: value }));
    setFieldErrors(previous => ({ ...previous, [field]: undefined }));
  };
  const save = async event => {
    event.preventDefault(); setError(''); setSuccess(''); setFieldErrors({});
    const original = initialValues(employee, config.fields);
    const changes = Object.fromEntries(Object.entries(form).map(([field, value]) => [field, typeof value === 'string' ? value.trim() : value])
      .filter(([field, value]) => JSON.stringify(value) !== JSON.stringify(original[field])));
    if (!Object.keys(changes).length) { setEditing(false); return; }
    setSaving(true);
    try {
      const response = await api.updateEmployee(employee.id, changes);
      if (!response?.data || response.status >= 400) throw new Error('Save could not be confirmed');
      if (mounted.current) {
        onSaved({ ...changes, ...response.data }); setEditing(false); setSuccess(config.saved || `${config.title} saved.`);
      }
    } catch (err) {
      if (mounted.current) {
        const detail = err?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Changes could not be saved. Please check the fields and try again.');
        setFieldErrors(fieldErrorsFrom(err));
      }
    } finally { if (mounted.current) setSaving(false); }
  };
  const contactInput = (field, label) => {
    const contact = typeof form[field] === 'string' ? { name: form[field] } : form[field] || {};
    return <fieldset className="profile-editor-group" key={field}><legend>{label}</legend>
      {['name', 'relationship', 'phone_number', 'email'].map(key => <label key={key}>{key.replaceAll('_', ' ')}
        <input aria-label={`${label} ${key.replaceAll('_', ' ')}`} type={key === 'email' ? 'email' : key === 'phone_number' ? 'tel' : 'text'}
          value={contact[key] || ''} onChange={event => setField(field, { ...contact, [key]: event.target.value })} />
      </label>)}
    </fieldset>;
  };
  const educationInput = field => {
    if (typeof form[field] === 'string') return <label className="profile-editor-wide" key={field}>Education
      <textarea aria-label="Education" maxLength={1000} value={form[field]} onChange={event => setField(field, event.target.value)} />
    </label>;
    const entries = form[field] || [];
    return <fieldset key={field} className="profile-editor-group"><legend>Education</legend>
      {entries.map((entry, index) => <div key={index} className="profile-editor-education">
        {['institution', 'qualification', 'year'].map(key => <label key={key}>{key}<input aria-label={`Education ${index + 1} ${key}`} maxLength={key === 'year' ? 4 : 160}
          value={entry[key] || ''} onChange={event => setField(field, entries.map((row, i) => i === index ? { ...row, [key]: event.target.value } : row))} /></label>)}
        <button className="profile-editor-icon" type="button" aria-label={`Remove education ${index + 1}`} onClick={() => setField(field, entries.filter((_, i) => i !== index))}><Trash2 size={16} /></button>
      </div>)}
      <button type="button" className="profile-editor-secondary" disabled={entries.length >= 20} onClick={() => setField(field, [...entries, { institution: '', qualification: '', year: '' }])}><Plus size={16} /> Add education</button>
    </fieldset>;
  };
  return <>
    <button ref={trigger} type="button" className="profile-editor-icon" aria-label={`Edit ${config.title}`} title={`Edit ${config.title}`}
      onClick={() => { setForm(initialValues(employee, config.fields)); setError(''); setFieldErrors({}); setSuccess(''); setEditing(true); }}><Pencil size={16} aria-hidden="true" /></button>
    <FormNotice message={success} onDismiss={setSuccess} />
    {editing && <dialog ref={dialog} className="profile-editor-dialog" aria-labelledby={`profile-editor-${section}-title`}
      onCancel={event => { event.preventDefault(); if (!saving) setEditing(false); }}>
      <form onSubmit={save} aria-label={`Edit ${config.title}`}>
        <header className="profile-editor-heading"><div><h2 id={`profile-editor-${section}-title`}>{config.title}</h2><p>{employee.full_name || 'Employee'} · Update employee information</p></div>
          <button type="button" className="profile-editor-icon" aria-label="Close editor" disabled={saving} onClick={() => setEditing(false)}><X size={20} /></button>
        </header>
        <fieldset disabled={saving} className="profile-editor-fields">
          <p className="profile-editor-guidance">Update the details you need. Only changed fields are saved.{section === 'bank' && ' Keep any leading zeroes in the account number.'}</p>
          {config.fields.map(([field, label, type, maxLength]) => {
            if (type === 'contact') return contactInput(field, label);
            if (type === 'education') return educationInput(field);
            const disabled = field === 'lifecycle_state' && !['hr_admin', 'general_manager'].includes(user?.role);
            return <label key={field} className={type === 'checkbox' ? 'profile-editor-checkbox' : ''}>{label}
              {Array.isArray(type) ? <select aria-label={label} aria-invalid={!!fieldErrors[field]} aria-describedby={fieldErrors[field] ? `form-error-${field}` : undefined} value={form[field]} disabled={disabled} onChange={event => setField(field, event.target.value)}>
                <option value="">Not specified</option>{[...new Set([...type, ...(form[field] ? [form[field]] : [])])].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
              </select> : <input aria-label={label} aria-invalid={!!fieldErrors[field]} aria-describedby={fieldErrors[field] ? `form-error-${field}` : undefined} type={type} maxLength={maxLength} value={type === 'checkbox' ? undefined : form[field]} checked={type === 'checkbox' ? form[field] : undefined}
                onChange={event => setField(field, type === 'checkbox' ? event.target.checked : event.target.value)} />}
              {disabled && <small>Lifecycle changes require an HR admin.</small>}
              <FieldError field={field} errors={fieldErrors} />
            </label>;
          })}
        </fieldset>
        {error && <p className="profile-editor-error" role="alert">{error}</p>}
        <footer className="profile-editor-footer"><button type="button" className="profile-editor-secondary" disabled={saving} onClick={() => setEditing(false)}>Cancel</button>
          <button type="submit" className="profile-editor-primary" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button></footer>
      </form>
    </dialog>}
  </>;
}
