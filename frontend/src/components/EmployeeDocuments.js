import React, { useState, useEffect, useCallback, useRef } from 'react';
import * as api from '../services/api';

// ----- Documents Tab -----
export default function EmployeeDocuments({ employeeId, user }) {
  const identity = `${user?.id}:${user?.role}:${employeeId || 'self'}`;
  const active = useRef(identity); active.current = identity;
  const generation = useRef(0);
  const [loadedFor, setLoadedFor] = useState(null);
  const [docs, setDocs] = useState([]);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState(null);
  const [category, setCategory] = useState('');
  const [categoryLabel, setCategoryLabel] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [error, setError] = useState('');
  const [visibility, setVisibility] = useState('hr_only');
  const [confidential, setConfidential] = useState(true);
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [downloading, setDownloading] = useState(null);
  const canWrite = ['hr_admin', 'hr_manager'].includes(user?.role);

  const load = useCallback(async () => {
    const sequence = ++generation.current;
    const valid = () => active.current === identity && sequence === generation.current;
    setLoading(true); setError(''); setDocs([]);
    try {
      const [d, c] = await Promise.all([employeeId ? api.getEmployeeDocuments(employeeId) : api.getMyDocuments(), api.getDocumentCategories()]);
      if (!Array.isArray(d.data)) throw new Error('Unavailable');
      if (!valid()) return;
      setDocs(d.data);
      setCats(c.data?.categories || []);
      if (c.data?.categories?.length) setCategory(previous => previous || c.data.categories[0]);
    } catch { if (valid()) setError('Documents are unavailable. Please retry.'); }
    finally { if (valid()) { setLoading(false); setLoadedFor(identity); } }
  }, [employeeId, identity]);
  useEffect(() => { active.current = identity; setShowUpload(false); setEditing(null); setConfirmDelete(null); setFile(null); setUploading(false); load(); return () => { active.current = null; }; }, [load, identity]);

  const submitUpload = async (ev) => {
    ev.preventDefault();
    if (!file || !category) return;
    if (file.size > 20 * 1024 * 1024) { setError('File exceeds the 20 MB limit'); return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('category', category);
    fd.append('visibility', visibility);
    fd.append('confidential', String(confidential));
    if (category === 'Other' && categoryLabel) fd.append('category_label', categoryLabel);
    setUploading(true);
    try {
      const target = employeeId || user?.employee_id;
      if (!target) throw new Error('Select an employee before uploading');
      const response = await api.uploadEmployeeDocument(target, fd);
      if (!response.data?.id) throw new Error('Upload was not confirmed');
      if (active.current !== identity) return;
      setShowUpload(false);
      setFile(null); setCategoryLabel('');
      load();
    } catch (err) {
      if (active.current === identity) setError(typeof err?.response?.data?.detail === 'string' ? err.response.data.detail : err?.response?.data?.detail?.message || err.message || 'Upload could not be confirmed. Refresh before retrying.');
    } finally { if (active.current === identity) setUploading(false); }
  };

  const doDelete = async () => {
    const id = confirmDelete?.id;
    if (!id) return;
    try {
      const response = await api.deleteEmployeeDocument(id);
      if (!response.data?.deleted) throw new Error('Removal not confirmed');
      if (active.current === identity) { setConfirmDelete(null); load(); }
    } catch { if (active.current === identity) setError('Document removal could not be confirmed. Refresh before retrying.'); }
  };

  const download = async doc => {
    setDownloading(doc.id); setError('');
    try {
      const response = await api.downloadEmployeeDocument(doc.id);
      if (!response.data || !(response.data instanceof Blob)) throw new Error('Unavailable');
      if (active.current !== identity) return;
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href = url; link.download = doc.file_name || 'Document'; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { if (active.current === identity) setError('Document download failed or is no longer authorized. Please retry.'); }
    finally { if (active.current === identity) setDownloading(null); }
  };

  const saveMetadata = async event => {
    event.preventDefault(); setUploading(true); setError('');
    try {
      const response = await api.updateEmployeeDocument(editing.id, editForm);
      if (!response.data?.id) throw new Error('Unconfirmed');
      if (active.current === identity) { setEditing(null); load(); }
    } catch (failure) { if (active.current === identity) setError(typeof failure?.response?.data?.detail === 'string' ? failure.response.data.detail : 'Document change could not be confirmed. Refresh before retrying.'); }
    finally { if (active.current === identity) setUploading(false); }
  };

  return (
    <div data-testid="documents-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ padding: '16px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em', fontSize: '16px' }}>Personal Documents</h3>
          <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#525252' }}>PDF, JPG, PNG, DOCX, XLSX up to 20 MB · Categories editable in Masters Settings</p>
        </div>
        {canWrite && (employeeId || user?.employee_id) && loadedFor === identity && (
          <button data-testid="upload-doc-btn" onClick={() => setShowUpload(true)} style={{ padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' }}>+ Upload</button>
        )}
      </div>

      <p style={{ padding: '0 18px', fontSize: '12px' }}>Only explicitly shared documents appear here. Legacy unclassified, medical, disciplinary and salary documents remain HR only. Ask HR if a document is missing.</p>
      {error && <p role="alert">{error} <button onClick={load}>Retry</button></p>}
      {loading || loadedFor !== identity ? <div style={{ padding: '32px', textAlign: 'center', color: '#525252' }}>Loading…</div> : !error && (
        <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
            {['Category', 'Document', 'Uploaded', 'Status', 'Actions'].map(h =>
              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontWeight: 700, fontFamily: 'Barlow' }}>{h}</th>
            )}
          </tr></thead>
          <tbody>
            {docs.map((d, i) => (
              <tr key={d.id} data-testid={`doc-row-${d.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700 }}>{d.category}{d.category === 'Other' && d.category_label ? ` · ${d.category_label}` : ''}</td>
                <td style={{ padding: '10px 14px', color: '#525252', overflowWrap: 'anywhere' }}>{d.title || d.file_name}{d.title && d.title !== d.file_name && <div>{d.file_name}</div>}</td>
                <td style={{ padding: '10px 14px', color: '#525252' }}>{d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('en-GB') : '—'}</td>
                <td style={{ padding: '10px 14px', color: '#525252' }}>{d.status || 'Available'}</td>
                <td style={{ padding: '10px 14px' }}>
                  <button data-testid={`view-doc-${d.id}`} disabled={d.download_allowed === false || downloading === d.id} onClick={() => download(d)} style={{ padding: '8px 12px', cursor: 'pointer' }}>{downloading === d.id ? 'Downloading…' : 'Download'}</button>
                  {canWrite && <button disabled={d.download_allowed === false} onClick={() => { setEditing(d); setError(''); setEditForm({ title: d.title || d.file_name, category: d.category, visibility: d.visibility || 'hr_only', confidential: d.confidential !== false, issued_date: d.issued_date || null, effective_date: d.effective_date || null, expiry_date: d.expiry_date || null }); }} style={{ padding: '8px 12px', cursor: 'pointer' }}>Manage</button>}
                  {canWrite && <button data-testid={`delete-doc-${d.id}`} onClick={() => setConfirmDelete(d)} style={{ marginLeft: '6px', padding: '4px 10px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Delete</button>}
                </td>
              </tr>
            ))}
            {docs.length === 0 && <tr><td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No authorized documents are available. Ask HR to share an approved document.</td></tr>}
          </tbody>
        </table>
        </div>
      )}

      {showUpload && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <form onSubmit={submitUpload} style={{ backgroundColor: '#fff', width: 'min(480px, 95vw)', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '16px 22px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
              <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900 }}>Upload Document</h3>
            </div>
            <div style={{ padding: '20px 22px', display: 'grid', gap: '14px' }}>
              {error && <p role="alert">{error}</p>}
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>Category</label>
                <select data-testid="upload-category" required value={category} onChange={e => setCategory(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                  {cats.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              {category === 'Other' && (
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>Free-text label</label>
                  <input data-testid="upload-category-label" value={categoryLabel} onChange={e => setCategoryLabel(e.target.value)} placeholder="Describe the document type" style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
              )}
              <label>Visibility<select aria-label="Document visibility" value={visibility} onChange={event => setVisibility(event.target.value)} style={{ width: '100%', padding: '10px' }}>
                <option value="hr_only">HR only</option><option value="hr_employee">HR + employee</option><option value="hr_employee_manager">HR + employee + line manager</option>
              </select></label>
              <label><input type="checkbox" checked={confidential} onChange={event => setConfidential(event.target.checked)} /> Confidential — HR only regardless of visibility</label>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>File (PDF, JPG, PNG, DOCX, XLSX · max 20 MB)</label>
                <input data-testid="upload-file-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx" required onChange={e => setFile(e.target.files[0])} style={{ width: '100%', padding: '8px 0', fontSize: '13px' }} />
                {file && <div style={{ marginTop: '4px', fontSize: '11px', color: '#525252' }}>{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</div>}
              </div>
            </div>
            <div style={{ padding: '14px 22px', borderTop: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button type="button" onClick={() => { setShowUpload(false); setFile(null); }} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
              <button data-testid="upload-submit-btn" type="submit" disabled={uploading || !file} style={{ padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{uploading ? 'Uploading…' : 'Upload'}</button>
            </div>
          </form>
        </div>
      )}

      {editing && loadedFor === identity && <div role="dialog" aria-label="Manage document" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
        <form onSubmit={saveMetadata} style={{ background: '#fff', padding: '24px', width: 'min(480px, 95vw)', maxHeight: '90vh', overflowY: 'auto' }}>
          <h2>Manage document</h2><p>Assigned employee cannot be changed. Sharing requires HR classification; restricted documents remain HR only.</p>
          {error && <p role="alert">{error}</p>}
          <label>Document title<input aria-label="Document title" required maxLength={200} value={editForm.title} onChange={event => setEditForm(previous => ({ ...previous, title: event.target.value }))} style={{ display: 'block', width: '100%', padding: '8px' }} /></label>
          <label>Category<select aria-label="Document category" value={editForm.category} onChange={event => setEditForm(previous => ({ ...previous, category: event.target.value }))} style={{ display: 'block', width: '100%', padding: '8px' }}>
            {[...new Set([...cats, editing.category])].filter(Boolean).map(value => <option key={value}>{value}</option>)}
          </select></label>
          <label>Visibility<select aria-label="Document visibility" value={editForm.visibility} onChange={event => setEditForm(previous => ({ ...previous, visibility: event.target.value }))} style={{ display: 'block', width: '100%', padding: '8px' }}>
            <option value="hr_only">HR only</option><option value="hr_employee">HR + employee</option><option value="hr_employee_manager">HR + employee + line manager</option>
          </select></label>
          <label><input type="checkbox" checked={editForm.confidential} onChange={event => setEditForm(previous => ({ ...previous, confidential: event.target.checked }))} /> Confidential — HR only</label>
          {['issued_date', 'effective_date', 'expiry_date'].map(field => <label key={field} style={{ display: 'block' }}>{field.replaceAll('_', ' ')}<input type="date" aria-label={field} value={editForm[field] || ''} onChange={event => setEditForm(previous => ({ ...previous, [field]: event.target.value || null }))} /></label>)}
          <div><button type="button" onClick={() => setEditing(null)} style={{ padding: '10px' }}>Cancel</button><button disabled={uploading} style={{ padding: '10px', background: '#FF353F', color: '#fff', border: 0 }}>Save document changes</button></div>
        </form>
      </div>}

      {confirmDelete && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div data-testid="confirm-delete-modal" style={{ backgroundColor: '#fff', width: '420px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '16px 22px', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>
              <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900 }}>Delete Document?</h3>
            </div>
            <div style={{ padding: '20px 22px', fontSize: '13px', color: '#525252' }}>
              Remove <strong style={{ color: '#191919' }}>{confirmDelete.file_name}</strong> ({confirmDelete.category}) from active documents. This is audited; the original file is retained for HR retention review.
            </div>
            <div style={{ padding: '14px 22px', borderTop: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button onClick={() => setConfirmDelete(null)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
              <button data-testid="confirm-delete-btn" onClick={doDelete} style={{ padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
