import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pencil } from 'lucide-react';
import * as api from '../services/api';

const style = { padding: '10px', border: '1px solid #aaa', width: '100%', boxSizing: 'border-box' };
const buttonStyle = { padding: '9px 14px', minHeight: '40px', border: '1px solid #191919', background: '#fff', color: '#191919', fontSize: '12px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' };
const labels = { leave_type: 'Leave type', status: 'Status', day_basis: 'Day basis', start_date: 'Start date', end_date: 'End date', resumption_date: 'Resumption date', working_days: 'Recorded days', reason: 'Reason for correction' };
const fail = error => typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Could not save. Reload records and preview again before retrying.';
export default function LeaveHistory({ rows, onSaved }) {
  const editTrigger = useRef(null);
  const [batch, setBatch] = useState(null);
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const run = async action => { setBusy(true); setError(''); setMessage(''); try { await action(); } catch (error) { setError(fail(error)); } finally { setBusy(false); } };
  const read = async event => {
    setBatch(null); setPreview(null); setError(''); setMessage('');
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 250000) { setError('Select a prepared JSON import smaller than 250 KB.'); return; }
    try { const data = JSON.parse(await file.text()); if (!Array.isArray(data.rows) || !data.rows.length || data.rows.length > 100) throw new Error(); setBatch({ rows: data.rows }); }
    catch { setError('Select a prepared historical leave JSON file containing 1â€“100 rows.'); }
  };
  const open = (row, trigger) => { editTrigger.current = trigger; setError(''); setEditing({ id: row.id, revision: row.revision, employee_name: row.employee_name, leave_type: row.leave_type,
    start_date: row.start_date, end_date: row.end_date, resumption_date: row.resumption_date || '', working_days: row.working_days,
    status: row.status, day_basis: row.day_basis || 'Recorded units', reason: '' }); };
  return <section style={{ padding: '20px', background: '#fff' }}>
    <h3>Historical leave records</h3>
    <p>HR can record and correct historical leave. Recorded units are preserved; blank source approvals appear as Recorded. These entries do not send approval notifications or change saved balance snapshots.</p>
    <label>Prepared source file <input aria-label="Historical leave import file" type="file" accept=".json,application/json" disabled={busy} onChange={read} /></label>
    {batch && <button style={buttonStyle} disabled={busy} onClick={() => run(async () => { setPreview(null); const response = await api.previewLeaveHistory(batch); if (!response.data?.preview_digest) throw new Error(); setPreview(response.data); })}>Preview import</button>}
    {preview && <div>
      <p>Review {preview.rows.length} source rows. Already imported rows will be skipped.</p>
      <div style={{ overflowX: 'auto' }}><table><thead><tr>{['Employee', 'Type', 'From', 'To', 'Days', 'Status', 'Source', 'Import'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
        {preview.rows.map(row => <tr key={row.source_key}>{[row.employee_name, row.leave_type, row.start_date, row.end_date, row.working_days, row.status, row.source_reference, row.already_imported ? 'Skip existing' : 'New'].map((value, i) => <td key={i} style={{ padding: '8px' }}>{value}</td>)}</tr>)}
      </tbody></table></div>
      <button style={buttonStyle} disabled={busy} onClick={() => run(async () => { const data = { ...batch, preview_digest: preview.preview_digest }; setPreview(null); const response = await api.importLeaveHistory(data); if (!Number.isInteger(response.data?.created)) throw new Error(); setMessage(`${response.data.created} imported; ${response.data.skipped} already present.`); setBatch(null); onSaved(); })}>Import reviewed records</button>
    </div>}
    {error && !editing && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div style={{ overflowX: 'auto', marginTop: '20px' }}><table style={{ width: '100%', fontSize: '13px' }}><thead><tr>{['Employee', 'Type', 'From', 'To', 'Days', 'Status', 'Action'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
      {rows.map(row => <tr key={row.id}>{[row.employee_name, row.leave_type, row.start_date, row.end_date, row.working_days, row.status].map((value, i) => <td key={i} style={{ padding: '10px' }}>{value}</td>)}<td>{row.can_correct_history && <button style={buttonStyle} disabled={busy} aria-label={`Edit historical record for ${row.employee_name}`} onClick={event => open(row, event.currentTarget)}><Pencil size={14} aria-hidden="true" style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: '6px' }} />Edit historical record</button>}</td></tr>)}
    </tbody></table>{!rows.length && <p>No historical records imported.</p>}</div>
    {editing && <HistoryDialog busy={busy} onClose={() => { setEditing(null); setError(''); }} trigger={editTrigger}>
        <h3 id="historical-correction-title" style={{ margin: '0 0 10px', fontWeight: 800, fontSize: '20px' }}>Edit historical leave - {editing.employee_name}</h3>
        <p id="historical-correction-description" style={{ marginBottom: '20px', color: '#525252', fontSize: '13px' }}>Update the recorded leave details and explain the correction. Changes are audited.</p>
        <form aria-label="Historical leave correction" onSubmit={event => { event.preventDefault(); run(async () => {
      const { id, employee_name, ...data } = editing;
      const response = await api.correctLeaveHistory(id, { ...data, resumption_date: data.resumption_date || null, working_days: Number(data.working_days) });
      if (!response.data?.id) throw new Error(); setEditing(null); setMessage('Historical record corrected.'); onSaved();
    }); }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: '12px' }}>
        {['leave_type', 'status', 'day_basis'].map(field => <label key={field}>{labels[field]}<select aria-label={`Historical ${field}`} style={style} disabled={busy} value={editing[field]} onChange={event => setEditing({ ...editing, [field]: event.target.value })}>
          {(field === 'leave_type' ? ['Annual', 'Sick', 'Paternity', 'Maternity', 'Compassionate', 'Unpaid'] : field === 'status' ? ['Approved', 'Pending', 'Recorded', 'Rejected', 'Cancelled'] : ['Recorded units', 'Calendar days']).map(value => <option key={value}>{value}</option>)}
        </select></label>)}
        {['start_date', 'end_date', 'resumption_date', 'working_days', 'reason'].map(field => <label key={field}>{labels[field]}<input aria-label={`Historical ${field}`} style={style} disabled={busy} type={field.endsWith('date') ? 'date' : field === 'working_days' ? 'number' : 'text'} required={field !== 'resumption_date'} step={field === 'working_days' ? 'any' : undefined} min={field === 'working_days' ? '0.01' : undefined} minLength={field === 'reason' ? 5 : undefined} maxLength={field === 'reason' ? 1000 : undefined} value={editing[field]} onChange={event => setEditing({ ...editing, [field]: event.target.value })} /></label>)}
      </div>
      {error && <p role="alert" style={{ color: '#991B1B', marginTop: '16px' }}>{error}</p>}
      <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '24px' }}>
        <button style={buttonStyle} type="button" disabled={busy} onClick={() => { setEditing(null); setError(''); }}>Cancel</button>
        <button style={{ ...buttonStyle, background: '#FF353F', borderColor: '#FF353F', color: '#fff' }} type="submit" disabled={busy}>{busy ? 'Saving...' : 'Save correction'}</button>
      </div>
    </form>
    </HistoryDialog>}
  </section>;
}


function HistoryDialog({ busy, onClose, trigger, children }) {
  const dialog = useRef(null);
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const returnFocus = trigger.current;
    document.body.style.overflow = 'hidden';
    dialog.current.showModal();
    return () => { document.body.style.overflow = previousOverflow; returnFocus?.focus(); };
  }, [trigger]);
  return createPortal(<>
    <style>{'.leave-history-dialog::backdrop { background: rgba(0,0,0,0.5); }'}</style>
    <dialog ref={dialog} className="leave-history-dialog" aria-modal="true" aria-labelledby="historical-correction-title" aria-describedby="historical-correction-description"
      onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
      style={{ position: 'fixed', inset: 0, margin: 'auto', width: 'min(620px, calc(100vw - 32px))', maxHeight: '90vh', overflowY: 'auto', background: '#fff', border: '1px solid #aaa', padding: '24px', boxSizing: 'border-box', boxShadow: '0 16px 48px rgba(0,0,0,0.25)' }}>
      {children}
    </dialog>
  </>, document.body);
}
