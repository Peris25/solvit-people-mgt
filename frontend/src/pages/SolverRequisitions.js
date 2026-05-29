import React, { useEffect, useState } from 'react';
import * as api from '../services/api';

const STATUS_COLOR = { Open: '#16A34A', Closed: '#9CA3AF' };

export default function SolverRequisitions() {
  const [items, setItems] = useState([]);
  const [counties, setCounties] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([api.listSolverRequisitions(), api.solverIntakeCounties()]);
      setItems(r.data.requisitions || []);
      setCanEdit(!!r.data.can_edit);
      setCounties(c.data.counties || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const toggleStatus = async (req) => {
    await api.updateSolverRequisition(req.id, { status: req.status === 'Open' ? 'Closed' : 'Open' });
    await load();
  };

  const copyLink = (req) => {
    const url = `${window.location.origin}/apply/${req.id}`;
    navigator.clipboard.writeText(url);
    alert(`Link copied:\n${url}`);
  };

  if (loading) return <div style={{ padding: '24px' }}>Loading…</div>;

  return (
    <div data-testid="solver-requisitions-page" style={{ padding: '32px 28px', backgroundColor: '#F9FAFB', minHeight: '100vh' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', margin: 0 }}>Solver Requisitions</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>
            Open a requisition to activate a public application link. Each link has its own QR code for posters / WhatsApp / referrals.
          </p>
        </div>
        {canEdit && (
          <button data-testid="new-req-btn" onClick={() => setShowNew(true)}
            style={{ padding: '10px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}>
            + New Requisition
          </button>
        )}
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead style={{ backgroundColor: '#F9FAFB', borderBottom: '2px solid rgba(25,25,25,0.08)' }}>
            <tr style={{ textAlign: 'left', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.1em', color: '#525252' }}>
              <th style={{ padding: '10px 12px' }}>Code</th>
              <th style={{ padding: '10px 12px' }}>Title</th>
              <th style={{ padding: '10px 12px' }}>Working Areas</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Received</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Eligible</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Ineligible</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Inducted</th>
              <th style={{ padding: '10px 12px', textAlign: 'center' }}>Status</th>
              <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map(r => (
              <tr key={r.id} data-testid={`req-row-${r.code}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.04)' }}>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontWeight: 700 }}>{r.code}</td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ fontWeight: 700 }}>{r.title}</div>
                  {r.target_hires ? <div style={{ fontSize: '11px', color: '#9CA3AF' }}>Target: {r.target_hires}</div> : null}
                </td>
                <td style={{ padding: '10px 12px', maxWidth: '200px' }}>
                  <div style={{ fontSize: '11px', color: '#525252', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {(r.working_areas || []).join(', ') || 'All counties'}
                  </div>
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700 }}>{r.counters?.received ?? 0}</td>
                <td style={{ padding: '10px 12px', textAlign: 'right', color: '#16A34A', fontWeight: 700 }}>{r.counters?.eligible ?? 0}</td>
                <td style={{ padding: '10px 12px', textAlign: 'right', color: '#FF353F', fontWeight: 700 }}>{r.counters?.ineligible ?? 0}</td>
                <td style={{ padding: '10px 12px', textAlign: 'right' }}>{r.counters?.inducted ?? 0}</td>
                <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                  <span style={{ padding: '3px 8px', fontSize: '10px', fontWeight: 700, color: '#fff', backgroundColor: STATUS_COLOR[r.status] }}>
                    {r.status?.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                  {canEdit && (
                    <>
                      <button data-testid={`toggle-${r.code}`} onClick={() => toggleStatus(r)} style={{ marginRight: '6px', padding: '4px 8px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700 }}>
                        {r.status === 'Open' ? 'Close' : 'Open'}
                      </button>
                      <button data-testid={`copy-${r.code}`} onClick={() => copyLink(r)} disabled={r.status !== 'Open'} style={{ marginRight: '6px', padding: '4px 8px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: r.status === 'Open' ? 'pointer' : 'not-allowed', fontSize: '11px', fontWeight: 700, opacity: r.status === 'Open' ? 1 : 0.4 }}>
                        Copy Link
                      </button>
                      <a data-testid={`qr-${r.code}`} href={api.requisitionQrUrl(r.id)} target="_blank" rel="noreferrer" style={{ display: 'inline-block', padding: '4px 8px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textDecoration: 'none', color: '#191919' }}>
                        QR
                      </a>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: '#9CA3AF' }}>No requisitions yet. Click "New Requisition" to create one.</td></tr>}
          </tbody>
        </table>
      </div>

      {(showNew || editing) && (
        <RequisitionForm
          counties={counties}
          initial={editing}
          onClose={() => { setShowNew(false); setEditing(null); }}
          onSaved={async () => { setShowNew(false); setEditing(null); await load(); }}
        />
      )}
    </div>
  );
}

function RequisitionForm({ counties, initial, onClose, onSaved }) {
  const [title, setTitle] = useState(initial?.title || 'Solver — Vehicle Inspector');
  const [allCounties, setAllCounties] = useState(initial ? (initial.working_areas || []).includes('All counties') : true);
  const [selected, setSelected] = useState(initial?.working_areas || []);
  const [target, setTarget] = useState(initial?.target_hires || '');
  const [status, setStatus] = useState(initial?.status || 'Closed');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleCounty = (c) => {
    setSelected(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      const payload = {
        title,
        working_areas: allCounties ? ['All counties'] : selected,
        target_hires: target ? Number(target) : null,
        status,
      };
      if (initial) await api.updateSolverRequisition(initial.id, payload);
      else await api.createSolverRequisition(payload);
      await onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="req-form-modal" style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <form onSubmit={submit} style={{ backgroundColor: '#fff', width: '640px', maxHeight: '85vh', overflow: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0, fontWeight: 900, fontSize: '15px' }}>{initial ? 'Edit' : 'New'} Solver Requisition</h3>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '20px' }}>×</button>
        </div>
        <div style={{ padding: '16px 20px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>Title</label>
          <input data-testid="req-title" required value={title} onChange={e => setTitle(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', marginBottom: '14px' }} />

          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>Working Area Scope</label>
          <label style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
            <input type="checkbox" checked={allCounties} onChange={e => setAllCounties(e.target.checked)} data-testid="all-counties" />
            All counties
          </label>
          {!allCounties && (
            <div data-testid="county-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', maxHeight: '180px', overflow: 'auto', padding: '8px', border: '1px solid rgba(25,25,25,0.1)', marginBottom: '14px' }}>
              {counties.map(c => (
                <label key={c} style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <input type="checkbox" checked={selected.includes(c)} onChange={() => toggleCounty(c)} />
                  {c}
                </label>
              ))}
            </div>
          )}

          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>Target Hires (optional)</label>
          <input data-testid="req-target" type="number" min="0" value={target} onChange={e => setTarget(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', marginBottom: '14px' }} />

          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>Status</label>
          <select data-testid="req-status" value={status} onChange={e => setStatus(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }}>
            <option value="Closed">Closed</option>
            <option value="Open">Open (link goes live)</option>
          </select>
          {error && <p style={{ color: '#FF353F', fontSize: '12px', marginTop: '10px' }}>{error}</p>}
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid rgba(25,25,25,0.08)', textAlign: 'right' }}>
          <button type="button" onClick={onClose} style={{ marginRight: '8px', padding: '8px 16px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>Cancel</button>
          <button data-testid="req-save" type="submit" disabled={saving} style={{ padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </div>
  );
}
