import React, { useState, useEffect, useRef } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const CATEGORIES = [
  '01 - People Strategy Foundation',
  '02 - Talent Acquisition',
  '03 - Onboarding',
  '04 - Performance Management',
  '05 - Learning and Development',
  '06 - Rewards and Recognition',
  '07 - Retention',
  '08 - Policies and Compliance',
  '09 - Templates',
  '10 - People Management System',
  '11 - Internal Communications',
  'Code of Conduct',
  'Leave',
  'Compensation',
  'IT Security',
  'Health & Safety',
  'Disciplinary',
  'Other',
];

export default function Policies() {
  const { user } = useAuth();
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [signature, setSignature] = useState('');
  const [form, setForm] = useState({ title: '', version: '1.0', category: '08 - Policies and Compliance', description: '', content: '', effective_date: new Date().toISOString().slice(0, 10), applies_to: ['all'] });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [draftId, setDraftId] = useState(null);
  const [fileInput, setFileInput] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [filterCategory, setFilterCategory] = useState('All');
  const fileRef = useRef();

  const canAcknowledge = selected && (selected.acknowledgement_available ?? (selected.status === 'Active' && Boolean(selected.content?.trim() || selected.has_attachment)));
  const canEdit = ['hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { const r = await api.getPolicies(); setPolicies(r.data); }
    catch { setError('Policies could not be loaded. Please retry.'); }
    finally { setLoading(false); }
  };

  const create = async (e) => {
    e.preventDefault();
    setError('');
    if (!fileInput && !form.content?.trim()) { setError('Attach a readable document or enter the full policy text before publishing.'); return; }
    if (fileInput && fileInput.size > 20 * 1024 * 1024) { setError('Files must be 20 MB or smaller.'); return; }
    setSaving(true);
    try {
      const payload = { ...form, status: 'Draft' };
      const response = draftId ? await api.updatePolicy(draftId, payload) : await api.createPolicy(payload);
      const id = draftId || response.data.id;
      setDraftId(id);
      if (fileInput) {
        setUploading(true);
        const fd = new FormData(); fd.append('file', fileInput);
        await api.uploadPolicyFile(id, fd);
      }
      await api.updatePolicy(id, { status: 'Active' });
      setShowForm(false); setDraftId(null);
      setForm({ title: '', version: '1.0', category: '08 - Policies and Compliance', description: '', content: '', effective_date: new Date().toISOString().slice(0, 10), applies_to: ['all'] });
      setFileInput(null);
      if (fileRef.current) fileRef.current.value = '';
      await load();
    } catch {
      setError('Publication failed. A saved draft is retained for retry. Check the document and scanner availability. If publication could not be confirmed, refresh before retrying.');
    } finally { setSaving(false); setUploading(false); }
  };

  const acknowledge = async (policy) => {
    if (!canAcknowledge) return;
    if (!signature.trim()) { alert('Please type your full name as digital signature'); return; }
    try {
      await api.acknowledgePolicy(policy.id, { signature });
      alert('Policy acknowledged successfully');
      setSelected(null);
      setSignature('');
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed to acknowledge'); }
  };

  const downloadFile = (policy) => {
    const url = api.policyDownloadUrl(policy.id);
    window.open(url, '_blank');
  };

  const grouped = CATEGORIES.reduce((acc, cat) => {
    const filtered = policies.filter(p => p.category === cat);
    if (filtered.length > 0) acc[cat] = filtered;
    return acc;
  }, {});

  const allCategories = ['All', ...Object.keys(grouped)];
  const displayPolicies = filterCategory === 'All' ? policies : (grouped[filterCategory] || []);

  return (
    <div data-testid="policies-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Policy Library</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>{policies.length} documents · acknowledge to confirm understanding</p>
        </div>
        {canEdit && <button data-testid="add-policy-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Publish Document</button>}
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {allCategories.map(cat => (
          <button key={cat} onClick={() => setFilterCategory(cat)} style={{ padding: '6px 12px', border: '1px solid rgba(25,25,25,0.15)', backgroundColor: filterCategory === cat ? '#FF353F' : '#fff', color: filterCategory === cat ? '#fff' : '#525252', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'Arial' }}>
            {cat === 'All' ? 'All' : cat.split(' - ')[1] || cat}
          </button>
        ))}
      </div>

      {error && <p role="alert">{error}</p>}
      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : displayPolicies.length === 0 ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No documents in this category yet. {canEdit && 'Click "+ Publish Document" to add one.'}</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 360px), 1fr))', gap: '12px' }}>
          {displayPolicies.map(p => (
            <div key={p.id} role="button" tabIndex={0} aria-label={`Read ${p.title}`} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(p); } }} data-testid={`policy-${p.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', cursor: 'pointer', transition: 'border-color 0.15s' }}
              onClick={() => setSelected(p)}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#FF353F'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(25,25,25,0.08)'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div style={{ fontWeight: 900, fontSize: '14px', color: '#191919', letterSpacing: '-0.02em' }}>{p.title}</div>
                <StatusBadge status={p.status} small />
              </div>
              <div style={{ fontSize: '11px', color: '#525252', marginBottom: '8px' }}>v{p.version} · {p.category}</div>
              <p style={{ fontSize: '12px', color: '#525252', lineHeight: 1.5, margin: '8px 0', minHeight: '36px' }}>{(p.description || '').slice(0, 120)}</p>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(25,25,25,0.06)', paddingTop: '8px', fontSize: '11px', color: '#525252' }}>
                <span>Effective: {p.effective_date ? new Date(p.effective_date).toLocaleDateString('en-GB') : '—'}</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {p.file_name && <span style={{ color: '#22C55E', fontWeight: 700 }}>📎 File attached</span>}
                  <span style={{ fontWeight: 700 }}>{p.acknowledgement_count || 0} ack'd</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '600px', maxWidth: 'calc(100vw - 24px)', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 900, fontSize: '18px' }}>{selected.title}</h3>
                <div style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>v{selected.version} · {selected.category} · Effective {selected.effective_date}</div>
              </div>
              <button onClick={() => { setSelected(null); setSignature(''); }} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ padding: '24px' }}>
              <p style={{ fontSize: '13px', lineHeight: 1.6, color: '#191919' }}>{selected.description || 'No description provided.'}</p>
              {selected.content && <div style={{ fontSize: '12px', color: '#525252', whiteSpace: 'pre-wrap', marginTop: '16px' }}>{selected.content}</div>}

              {selected.file_name && (
                <div style={{ marginTop: '16px', padding: '12px 16px', border: '1px solid rgba(34,197,94,0.3)', backgroundColor: 'rgba(34,197,94,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '12px', color: '#191919' }}>📎 {selected.file_name}</span>
                  <button onClick={() => downloadFile(selected)} style={{ padding: '6px 14px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'Arial' }}>Download</button>
                </div>
              )}

              <div style={{ marginTop: '24px', padding: '16px', border: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#FAFAFA' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>Digital Acknowledgement</div>
                <p style={{ fontSize: '12px', color: '#525252', margin: '0 0 8px 0' }}>By typing your full name below, you confirm that you have read and understood this document.</p>
                {!canAcknowledge && <p role="status">This policy is not available for acknowledgement. HR must publish readable content or an approved document first.</p>}
                <input disabled={!canAcknowledge} data-testid="ack-signature" placeholder="Type your full name" value={signature} onChange={e => setSignature(e.target.value)} style={{ width: '100%', padding: '10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'cursive', boxSizing: 'border-box' }} />
                <button disabled={!canAcknowledge || !signature.trim()} data-testid="acknowledge-btn" onClick={() => acknowledge(selected)} style={{ marginTop: '12px', padding: '10px 24px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>Acknowledge</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxWidth: 'calc(100vw - 24px)', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Publish Document</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            {error && <p role="alert">{error}</p>}
            <form aria-label="Publish policy" onSubmit={create} style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Title</label>
                <input required value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label htmlFor="policy-content">Full policy text (or attach a document)</label>
                <textarea id="policy-content" rows={6} value={form.content || ''} onChange={event => setForm(previous => ({ ...previous, content: event.target.value }))} style={{ width: '100%', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Version</label>
                <input required value={form.version} onChange={e => setForm(p => ({ ...p, version: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Category</label>
                <select value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Description</label>
                <textarea required rows={4} value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Effective Date</label>
                <input type="date" required value={form.effective_date} onChange={e => setForm(p => ({ ...p, effective_date: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Attach File (optional)</label>
                <input ref={fileRef} type="file" aria-label="Policy file" accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg" onChange={e => setFileInput(e.target.files[0] || null)} style={{ width: '100%', padding: '6px 0', fontSize: '12px', boxSizing: 'border-box' }} />
                <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '3px' }}>PDF, DOCX, XLSX, JPG or PNG - Maximum 20 MB - Malware scanning required</div>
              </div>
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button type="submit" disabled={saving || uploading} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving || uploading ? 'Publishing...' : 'Publish'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
