import React, { useState } from 'react';
import * as api from '../services/api';

const style = { padding: '10px', border: '1px solid #aaa', width: '100%', boxSizing: 'border-box' };
const fail = error => typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Could not save. Reload records and preview again before retrying.';
export default function LeaveHistory({ rows, onSaved }) {
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
    catch { setError('Select a prepared historical leave JSON file containing 1–100 rows.'); }
  };
  const open = row => setEditing({ id: row.id, revision: row.revision, employee_name: row.employee_name, leave_type: row.leave_type,
    start_date: row.start_date, end_date: row.end_date, resumption_date: row.resumption_date || '', working_days: row.working_days,
    status: row.status, day_basis: row.day_basis || 'Recorded units', reason: '' });
  return <section style={{ padding: '20px', background: '#fff' }}>
    <h3>Historical leave records</h3>
    <p>HR can record and correct historical leave. Recorded units are preserved; blank source approvals appear as Recorded. These entries do not send approval notifications or change saved balance snapshots.</p>
    <label>Prepared source file <input aria-label="Historical leave import file" type="file" accept=".json,application/json" disabled={busy} onChange={read} /></label>
    {batch && <button disabled={busy} onClick={() => run(async () => { setPreview(null); const response = await api.previewLeaveHistory(batch); if (!response.data?.preview_digest) throw new Error(); setPreview(response.data); })}>Preview import</button>}
    {preview && <div>
      <p>Review {preview.rows.length} source rows. Already imported rows will be skipped.</p>
      <div style={{ overflowX: 'auto' }}><table><thead><tr>{['Employee', 'Type', 'From', 'To', 'Days', 'Status', 'Source', 'Import'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
        {preview.rows.map(row => <tr key={row.source_key}>{[row.employee_name, row.leave_type, row.start_date, row.end_date, row.working_days, row.status, row.source_reference, row.already_imported ? 'Skip existing' : 'New'].map((value, i) => <td key={i} style={{ padding: '8px' }}>{value}</td>)}</tr>)}
      </tbody></table></div>
      <button disabled={busy} onClick={() => run(async () => { const data = { ...batch, preview_digest: preview.preview_digest }; setPreview(null); const response = await api.importLeaveHistory(data); if (!Number.isInteger(response.data?.created)) throw new Error(); setMessage(`${response.data.created} imported; ${response.data.skipped} already present.`); setBatch(null); onSaved(); })}>Import reviewed records</button>
    </div>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div style={{ overflowX: 'auto', marginTop: '20px' }}><table style={{ width: '100%', fontSize: '13px' }}><thead><tr>{['Employee', 'Type', 'From', 'To', 'Days', 'Status', 'Action'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>
      {rows.map(row => <tr key={row.id}>{[row.employee_name, row.leave_type, row.start_date, row.end_date, row.working_days, row.status].map((value, i) => <td key={i} style={{ padding: '10px' }}>{value}</td>)}<td>{row.can_correct_history && <button disabled={busy} onClick={() => open(row)}>Edit historical record</button>}</td></tr>)}
    </tbody></table>{!rows.length && <p>No historical records imported.</p>}</div>
    {editing && <form aria-label="Historical leave correction" onSubmit={event => { event.preventDefault(); run(async () => {
      const { id, employee_name, ...data } = editing;
      const response = await api.correctLeaveHistory(id, { ...data, resumption_date: data.resumption_date || null, working_days: Number(data.working_days) });
      if (!response.data?.id) throw new Error(); setEditing(null); setMessage('Historical record corrected.'); onSaved();
    }); }} style={{ border: '1px solid #aaa', padding: '16px' }}>
      <h4>Correct {editing.employee_name}'s historical leave</h4>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: '12px' }}>
        {['leave_type', 'status', 'day_basis'].map(field => <label key={field}>{field.replaceAll('_', ' ')}<select aria-label={`Historical ${field}`} style={style} disabled={busy} value={editing[field]} onChange={event => setEditing({ ...editing, [field]: event.target.value })}>
          {(field === 'leave_type' ? ['Annual', 'Sick', 'Paternity', 'Maternity', 'Compassionate', 'Unpaid'] : field === 'status' ? ['Approved', 'Pending', 'Recorded', 'Rejected', 'Cancelled'] : ['Recorded units', 'Calendar days']).map(value => <option key={value}>{value}</option>)}
        </select></label>)}
        {['start_date', 'end_date', 'resumption_date', 'working_days', 'reason'].map(field => <label key={field}>{field.replaceAll('_', ' ')}<input aria-label={`Historical ${field}`} style={style} disabled={busy} type={field.endsWith('date') ? 'date' : field === 'working_days' ? 'number' : 'text'} required={field !== 'resumption_date'} step={field === 'working_days' ? 'any' : undefined} min={field === 'working_days' ? '0.01' : undefined} minLength={field === 'reason' ? 5 : undefined} maxLength={field === 'reason' ? 1000 : undefined} value={editing[field]} onChange={event => setEditing({ ...editing, [field]: event.target.value })} /></label>)}
      </div>
      <button type="submit" disabled={busy}>Save correction</button> <button type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button>
    </form>}
  </section>;
}
