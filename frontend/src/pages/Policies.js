import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const CATEGORIES = ['Code of Conduct', 'Leave', 'Compensation', 'IT Security', 'Health & Safety', 'Disciplinary', 'Performance', 'Recruitment', 'Other'];

export default function Policies() {
  const { user } = useAuth();
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [signature, setSignature] = useState('');
  const [form, setForm] = useState({ title: '', version: '1.0', category: 'Other', description: '', effective_date: new Date().toISOString().slice(0, 10), applies_to: ['all'] });
  const [saving, setSaving] = useState(false);

  const canEdit = ['hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { const r = await api.getPolicies(); setPolicies(r.data); }
    finally { setLoading(false); }
  };

  const create = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createPolicy(form);
      setShowForm(false);
      setForm({ title: '', version: '1.0', category: 'Other', description: '', effective_date: new Date().toISOString().slice(0, 10), applies_to: ['all'] });
      load();
    } finally { setSaving(false); }
  };

  const acknowledge = async (policy) => {
    if (!signature.trim()) { alert('Please type your full name as digital signature'); return; }
    try {
      await api.acknowledgePolicy(policy.id, { signature });
      alert('Policy acknowledged successfully');
      setSelected(null);
      setSignature('');
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed to acknowledge'); }
  };

  return (
    <div data-testid="policies-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Policy Library</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>{policies.length} policies · acknowledge to confirm understanding</p>
        </div>
        {canEdit && <button data-testid="add-policy-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Publish Policy</button>}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : policies.length === 0 ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No policies published yet. {canEdit && 'Click "+ Publish Policy" to add one.'}</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '12px' }}>
          {policies.map(p => (
            <div key={p.id} data-testid={`policy-${p.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', cursor: 'pointer', transition: 'border-color 0.15s' }}
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
                <span style={{ fontWeight: 700 }}>{p.acknowledgement_count || 0} ack'd</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '600px', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 900, fontSize: '18px' }}>{selected.title}</h3>
                <div style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>v{selected.version} · {selected.category} · Effective {selected.effective_date}</div>
              </div>
              <button onClick={() => { setSelected(null); setSignature(''); }} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ padding: '24px' }}>
              <p style={{ fontSize: '13px', lineHeight: 1.6, color: '#191919' }}>{selected.description || 'Policy details to be added.'}</p>
              {selected.content && <div style={{ fontSize: '12px', color: '#525252', whiteSpace: 'pre-wrap', marginTop: '16px' }}>{selected.content}</div>}
              <div style={{ marginTop: '24px', padding: '16px', border: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#FAFAFA' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '8px' }}>Digital Acknowledgement</div>
                <p style={{ fontSize: '12px', color: '#525252', margin: '0 0 8px 0' }}>By typing your full name below, you confirm that you have read and understood this policy.</p>
                <input data-testid="ack-signature" placeholder="Type your full name" value={signature} onChange={e => setSignature(e.target.value)} style={{ width: '100%', padding: '10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'cursive', boxSizing: 'border-box' }} />
                <button data-testid="acknowledge-btn" onClick={() => acknowledge(selected)} style={{ marginTop: '12px', padding: '10px 24px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>Acknowledge Policy</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Publish Policy</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={create} style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Title</label>
                <input required value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
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
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Publishing...' : 'Publish'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
