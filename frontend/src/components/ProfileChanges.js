import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../services/api';

const fields = { full_name: 'Full name', preferred_name: 'Preferred name', personal_email: 'Personal email', phone_number: 'Personal phone',
  date_of_birth: 'Date of birth', gender: 'Gender', national_id_number: 'National ID', kra_pin: 'KRA PIN', nssf_number: 'NSSF number', sha_number: 'SHA number',
  next_of_kin: 'Next of kin', emergency_contact: 'Emergency contact', education: 'Education', bank_name: 'Bank name', bank_branch: 'Bank branch',
  bank_account_number: 'Bank account number', mpesa_number: 'M-Pesa number', payment_method: 'Payment method' };
const errorMessage = error => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : 'Profile changes are unavailable. Please retry.';
const inputStyle = { width: '100%', boxSizing: 'border-box', padding: '10px', border: '1px solid #D4D4D4', margin: '6px 0 14px' };
const buttonStyle = { padding: '10px 16px', margin: '4px 8px 4px 0', background: '#FF353F', color: '#fff', border: 0, cursor: 'pointer' };

export default function ProfileChanges({ employee, user, selfService, onApplied }) {
  const key = `${user?.id}:${user?.role}:${employee.id}:${selfService}`;
  const active = useRef(key); active.current = key;
  const [loaded, setLoaded] = useState(null);
  const [rows, setRows] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [field, setField] = useState('phone_number');
  const [value, setValue] = useState('');
  const [structured, setStructured] = useState({});
  const [reason, setReason] = useState('');
  const canReview = ['hr_admin', 'hr_manager', 'finance'].includes(user?.role);
  const load = useCallback(async () => {
    setLoaded(null); setRows([]); setInbox([]); setError('');
    try {
      const response = await (selfService ? api.getMyProfileChanges() : api.getProfileChanges(employee.id));
      if (!Array.isArray(response.data)) throw new Error('Unavailable');
      const reviews = selfService && canReview ? await api.getProfileChangeInbox() : { data: [] };
      if (!Array.isArray(reviews.data)) throw new Error('Unavailable');
      if (active.current === key) { setRows(response.data); setInbox(reviews.data); setLoaded(key); }
    } catch (failure) { if (active.current === key) setError(errorMessage(failure)); }
  }, [key, selfService, employee.id, canReview]);
  useEffect(() => { setNotice(''); setValue(''); setStructured({}); setReason(''); load(); }, [load]);
  const submit = async event => {
    event.preventDefault(); setError(''); setNotice(''); setBusy(true);
    const change = ['next_of_kin', 'emergency_contact'].includes(field) ? structured : field === 'education' ? [structured] : value;
    try {
      const response = await api.requestProfileChange({ [field]: change });
      if (!response.data?.id) throw new Error('Unconfirmed');
      if (active.current !== key) return;
      setNotice('Change requested. Your saved profile remains unchanged until approval. Bank changes also require Finance approval.');
      setValue(''); setStructured({}); await load();
    } catch (failure) { if (active.current === key) setError(errorMessage(failure)); }
    finally { if (active.current === key) setBusy(false); }
  };
  const decide = async (row, decision) => {
    setBusy(true); setError('');
    try {
      const response = await api.reviewProfileChange(row.id, decision, reason);
      if (!response.data?.id) throw new Error('Unconfirmed');
      if (active.current !== key) return;
      setNotice(response.data.status === 'Approved' ? 'Profile change approved and applied.' : `Profile change: ${response.data.status}.`);
      setReason(''); await load(); if (response.data.status === 'Approved') onApplied?.();
    } catch (failure) { if (active.current === key) setError(errorMessage(failure)); }
    finally { if (active.current === key) setBusy(false); }
  };
  const renderRows = values => values.map(row => <article key={row.id} style={{ border: '1px solid #D4D4D4', padding: '14px', marginTop: '12px' }}>
    {row.employee_name && <strong>{row.employee_name}</strong>}<p>Status: {row.status}</p>
    <dl>{Object.entries(row.changes || {}).map(([name, detail]) => <React.Fragment key={name}><dt>{fields[name] || name}</dt><dd style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{typeof detail === 'object' ? JSON.stringify(detail) : detail}</dd></React.Fragment>)}</dl>
    {row.review_reason && <p>Review: {row.review_reason}</p>}
    {row.employee_id !== user?.employee_id && ((['hr_admin', 'hr_manager'].includes(user?.role) && row.status === 'Pending_HR') || (user?.role === 'finance' && row.status === 'Pending_Finance')) && <>
      <button disabled={busy} style={buttonStyle} onClick={() => decide(row, 'Approve')}>{row.status === 'Pending_Finance' ? 'Finance approve and apply' : 'HR approve'}</button>
      <button disabled={busy} style={buttonStyle} onClick={() => decide(row, 'Reject')}>Reject</button>
    </>}
  </article>);
  const nestedFields = ['next_of_kin', 'emergency_contact'].includes(field) ? ['name', 'relationship', 'phone_number', 'email'] : field === 'education' ? ['institution', 'qualification', 'year'] : null;
  return <section data-testid="profile-changes" style={{ background: '#fff', padding: '24px', maxWidth: '900px' }}>
    <h2>{selfService ? 'Request a profile change' : 'Profile change requests'}</h2>
    <p>HR approves personal changes. Bank changes require HR followed by Finance. Employment details, work email, department, salary and reporting relationships remain under HR administration.</p>
    {error && <p role="alert">{error} <button onClick={load}>Retry</button></p>}
    {notice && <p role="status">{notice}</p>}
    {loaded !== key ? !error && <p>Loading profile changes…</p> : <>
      {selfService && <form onSubmit={submit}>
        <label htmlFor="profile-change-field">Field to change</label>
        <select id="profile-change-field" value={field} style={inputStyle} onChange={event => { setField(event.target.value); setValue(''); setStructured({}); }}>
          {Object.entries(fields).map(([name, label]) => <option key={name} value={name}>{label}</option>)}
        </select>
        {nestedFields ? nestedFields.map(name => <label key={name} style={{ display: 'block' }}>{name.replaceAll('_', ' ')}
          <input aria-label={`New ${name}`} maxLength={160} style={inputStyle} value={structured[name] || ''} onChange={event => setStructured(previous => ({ ...previous, [name]: event.target.value }))} />
        </label>) : <label>Requested value<input aria-label="Requested value" type={field === 'date_of_birth' ? 'date' : field === 'personal_email' ? 'email' : 'text'} maxLength={254} style={inputStyle} value={value} onChange={event => setValue(event.target.value)} /></label>}
        {field === 'education' && <p>This requests an additional education record. Existing entries are retained; ask HR to correct an existing entry.</p>}
        <button style={buttonStyle} disabled={busy || rows.some(row => ['Pending_HR', 'Pending_Finance', 'Applying'].includes(row.status))}>Submit change request</button>
      </form>}
      {canReview && <label>Review reason (required to reject)<textarea aria-label="Review reason" maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} style={inputStyle} /></label>}
      <h3>Request history</h3>{rows.length ? renderRows(rows) : <p>No profile change requests.</p>}
      {selfService && canReview && <><h3>Awaiting your review</h3>{inbox.length ? renderRows(inbox) : <p>No profile changes awaiting your review.</p>}</>}
    </>}
  </section>;
}
