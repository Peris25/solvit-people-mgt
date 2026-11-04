import React, { useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

export default function SolverApplicantEditor({ applicant, stages, onClose, onSaved }) {
  const [values, setValues] = useState({ full_name: applicant.full_name || '', email: applicant.email || '', phone_number: applicant.phone_number || '', county: applicant.county || '', town_area: applicant.town_area || '', stage: stages.includes(applicant.recruitment_stage) ? applicant.recruitment_stage : '', reason: '', confirm_active: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = (field, value) => setValues(v => ({ ...v, [field]: value }));
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const payload = { ...values, expected_version: applicant.edit_version };
      if (!payload.stage) delete payload.stage;
      const response = await api.updateEligibleSolver(applicant.id, payload);
      if (!response?.data?.id) throw new Error('The update could not be confirmed. Reopen the applicant before retrying.');
      await onSaved(response.data);
    } catch (e) { setError(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e.message || 'Applicant could not be saved.'); }
    finally { setBusy(false); }
  };
  const control = { padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, width: '100%', boxSizing: 'border-box', font: 'inherit' };
  return <div role="dialog" aria-modal="true" aria-labelledby="applicant-editor-title" style={{ position: 'fixed', inset: 0, background: '#0008', zIndex: 110, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
    <form onSubmit={submit} style={{ background: '#fff', padding: 24, borderRadius: 18, maxWidth: 650, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}>
      <h2 id="applicant-editor-title">Edit eligible Solver</h2>
      <p>Update applicant details and the recruitment stage. Assessment answers and original eligibility checks stay unchanged.</p>
      {error && <p role="alert">{error}</p>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 14 }}>
        {[['full_name', 'Full name'], ['email', 'Email'], ['phone_number', 'Phone'], ['county', 'County'], ['town_area', 'Town / area']].map(([field, title]) => <label key={field}>{title}<input style={control} aria-label={title} type={field === 'email' ? 'email' : 'text'} required={['full_name', 'email', 'phone_number'].includes(field)} value={values[field]} onChange={e => change(field, e.target.value)} /></label>)}
      </div>
      <label style={{ display: 'block', marginTop: 16 }}>Recruitment stage<select style={control} aria-label="Recruitment stage" value={values.stage} onChange={e => { change('stage', e.target.value); change('confirm_active', false); }}>
        {!stages.includes(applicant.recruitment_stage) && <option value="">Keep existing stage: {applicant.recruitment_stage}</option>}
        {stages.filter(s => s !== 'Active' || applicant.can_confirm).map(s => <option key={s}>{s}</option>)}
      </select></label>
      {values.stage === 'Active' && <label style={{ display: 'block', padding: 14, marginTop: 12, background: '#fff4df' }}><input type="checkbox" required checked={values.confirm_active} onChange={e => change('confirm_active', e.target.checked)} /> HR confirms this applicant has passed and is approved to become an Active Solver. This creates their Solver directory record; it does not create a login account.</label>}
      <label style={{ display: 'block', margin: '16px 0' }}>Reason / HR confirmation notes<textarea style={control} aria-label="Applicant change reason" required minLength={10} maxLength={1500} rows={3} value={values.reason} onChange={e => change('reason', e.target.value)} /></label>
      <div style={{ display: 'flex', gap: 12 }}><LeaveActionButton type="submit" variant="primary" disabled={busy}>{busy ? 'Saving…' : 'Save applicant'}</LeaveActionButton><LeaveActionButton disabled={busy} onClick={onClose}>Cancel</LeaveActionButton></div>
    </form>
  </div>;
}
