import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';
const message = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e.message || 'Payroll files are unavailable. Please retry.';

export default function PayrollFiles() {
  const [rows, setRows] = useState([]);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const picker = useRef(null);
  const active = useRef(true);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const generation = ++sequence.current;
    const valid = () => active.current && generation === sequence.current;
    setLoading(true); setError('');
    try {
      const response = await api.getPayrollFiles();
      if (!Array.isArray(response?.data)) throw new Error('Payroll files could not be loaded.');
      if (valid()) setRows(response.data);
    } catch (e) { if (valid()) setError(message(e)); }
    finally { if (valid()) setLoading(false); }
  }, []);
  useEffect(() => { active.current = true; load(); return () => { active.current = false; }; }, [load]);
  const upload = async event => {
    event.preventDefault(); if (!file) return;
    setError(''); setNotice('');
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 5 * 1024 * 1024) { setError('Choose an Excel .xlsx workbook up to 5 MB.'); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append('file', file);
      const response = await api.uploadPayrollFile(form);
      if (!response?.data?.id) throw new Error('Upload could not be confirmed. Refresh the list before retrying.');
      if (!active.current) return;
      setFile(null); if (picker.current) picker.current.value = '';
      setNotice('Payroll file uploaded privately. No employee or payroll records were changed.');
      await load();
    } catch (e) { if (active.current) setError(message(e)); }
    finally { if (active.current) setBusy(false); }
  };
  const download = async row => {
    setBusy(true); setError('');
    try {
      const response = await api.downloadPayrollFile(row.id);
      if (!(response?.data instanceof Blob)) throw new Error('The file could not be downloaded.');
      if (!active.current) return;
      const url = URL.createObjectURL(response.data); const link = document.createElement('a');
      link.href = url; link.download = row.file_name; link.click(); URL.revokeObjectURL(url);
    } catch (e) { if (active.current) setError(message(e)); }
    finally { if (active.current) setBusy(false); }
  };
  return <section aria-label="Private HR payroll files" style={{ background: '#fff', padding: 24, border: '1px solid #e5e7eb', borderRadius: 16, margin: '20px 0' }}>
    <h2>Payroll files</h2>
    <p>Upload the Excel workbook HR wants to keep here. Files stay private to authorized HR administrators; uploading does not import rows, change salaries or bank details, or publish information to employees.</p>
    <form onSubmit={upload} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: 16, marginBottom: 20 }}>
      <label style={{ display: 'grid', gap: 8 }}>Excel workbook (.xlsx, up to 5 MB)
        <input ref={picker} type="file" aria-label="Payroll Excel workbook" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setNotice(''); }} />
      </label>
      <LeaveActionButton type="submit" variant="primary" disabled={busy || !file}>{busy ? 'Working…' : 'Upload payroll Excel'}</LeaveActionButton>
      <LeaveActionButton disabled={busy || loading} onClick={load}>Refresh files</LeaveActionButton>
    </form>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {loading ? <p role="status">Loading payroll files…</p> : !rows.length ? <p>No payroll files uploaded yet.</p> : <>
      <p>Latest payroll files (up to 100)</p>
      <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
        <thead><tr>{['Workbook', 'Uploaded', 'Uploaded by', 'Status', 'Action'].map(title => <th style={{ textAlign: 'left', padding: 12 }} key={title}>{title}</th>)}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.id} style={{ borderTop: '1px solid #e5e7eb' }}><td style={{ padding: 12 }}>{row.file_name}</td><td>{new Date(row.uploaded_at).toLocaleString('en-KE', { timeZone: 'Africa/Nairobi' })} EAT</td><td>{row.uploaded_by_name}</td><td>{row.status}</td><td><LeaveActionButton disabled={busy || !row.download_allowed} onClick={() => download(row)}>Download</LeaveActionButton></td></tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}
