import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtKES = (n) => n != null ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';

export default function Compensation() {
  const { user } = useAuth();
  const [tab, setTab] = useState('bands');
  const [bands, setBands] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [bonus, setBonus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tier, setTier] = useState('Tier1');
  const [editBand, setEditBand] = useState(null);
  const [editForm, setEditForm] = useState({ min_kes: 0, mid_kes: 0, max_kes: 0, roles_csv: '', note: '' });
  const [saving, setSaving] = useState(false);

  const canEditBands = ['hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => {
    Promise.all([api.getPayBands(), api.getPayBandAlerts()])
      .then(([b, a]) => { setBands(b.data || []); setAlerts(a.data || []); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { if (tab === 'bonus') api.getBonusCalculator(tier).then(r => setBonus(r.data)); }, [tab, tier]);

  const openEdit = (band) => {
    setEditBand(band);
    setEditForm({
      min_kes: band.min_kes || 0,
      mid_kes: band.mid_kes || 0,
      max_kes: band.max_kes || 0,
      roles_csv: (band.roles || []).join(', '),
      note: band.note || '',
    });
  };

  const saveBand = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        min_kes: Number(editForm.min_kes),
        mid_kes: Number(editForm.mid_kes),
        max_kes: Number(editForm.max_kes),
        roles: editForm.roles_csv.split(',').map(s => s.trim()).filter(Boolean),
        note: editForm.note,
      };
      await api.updatePayBand(editBand.id, payload);
      const r = await api.getPayBands();
      setBands(r.data || []);
      setEditBand(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="compensation-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Compensation</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Pay Bands · Salary Reviews · Bonus Calculator · GP Gate</p>
        </div>
        {tab === 'bands' && (
          <button data-testid="export-pay-bands-csv" onClick={() => api.downloadCSV('pay-bands')} style={{ padding: '8px 14px', backgroundColor: 'transparent', color: '#191919', border: '1px solid #191919', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>↓ CSV</button>
        )}
      </div>

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {[{ k: 'bands', l: 'Pay Bands' }, { k: 'alerts', l: `Pay Alerts (${alerts.length})` }, { k: 'bonus', l: 'Bonus Calculator' }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'bands' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
              {['Band', 'Min', 'Mid', 'Max', 'Roles', canEditBands ? 'Edit' : ''].filter(Boolean).map(h => (
                <th key={h} style={{ padding: '12px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {bands.map((b, i) => (
                <tr key={b.id} data-testid={`band-${b.band}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '12px 14px', fontWeight: 900, fontSize: '14px', color: '#FF353F' }}>{b.band}</td>
                  <td style={{ padding: '12px 14px', fontWeight: 700 }}>{fmtKES(b.min_kes)}</td>
                  <td style={{ padding: '12px 14px', fontWeight: 700, color: '#22C55E' }}>{fmtKES(b.mid_kes)}</td>
                  <td style={{ padding: '12px 14px', fontWeight: 700 }}>{fmtKES(b.max_kes)}</td>
                  <td style={{ padding: '12px 14px', color: '#525252', fontSize: '11px' }}>{(b.roles || []).join(', ')}{b.note && <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '2px' }}>{b.note}</div>}</td>
                  {canEditBands && (
                    <td style={{ padding: '12px 14px' }}>
                      <button data-testid={`edit-band-${b.band}`} onClick={() => openEdit(b)} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Edit</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : tab === 'alerts' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {alerts.length === 0 ? <div style={{ padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No active pay band alerts</div> : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Employee', 'Role', 'Band', 'Salary', 'Min', 'Alert'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {alerts.map((a, i) => (
                  <tr key={a.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{a.employee_name}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{a.role}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 900, color: '#FF353F' }}>{a.band}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{fmtKES(a.current_salary)}</td>
                    <td style={{ padding: '10px 14px' }}>{fmtKES(a.band_minimum)}</td>
                    <td style={{ padding: '10px 14px' }}><span style={{ backgroundColor: a.alert_type === 'below_minimum' ? '#FEE2E2' : '#FEF3C7', color: a.alert_type === 'below_minimum' ? '#991B1B' : '#92400E', padding: '2px 8px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{a.alert_type?.replace('_', ' ')}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginRight: '12px' }}>Bonus Tier:</label>
            <select data-testid="bonus-tier" value={tier} onChange={e => setTier(e.target.value)} style={{ padding: '6px 12px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial' }}>
              <option value="Tier1">Tier 1 (8% Met / 15% Exceeded)</option>
              <option value="Tier2">Tier 2 (12% Met / 20% Exceeded)</option>
            </select>
          </div>
          {bonus ? (
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 700, fontSize: '13px' }}>Total Bonus Pool</span>
                <span style={{ fontWeight: 900, fontSize: '18px', color: '#22C55E' }}>{fmtKES(bonus.total_bonus_kes)}</span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                  {['Employee', 'Role', 'Salary', 'Score', 'Rating', 'Bonus'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {bonus.employees.map((e, i) => (
                    <tr key={e.employee_id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 700 }}>{e.name}</td>
                      <td style={{ padding: '10px 14px', color: '#525252' }}>{e.role}</td>
                      <td style={{ padding: '10px 14px' }}>{fmtKES(e.salary)}</td>
                      <td style={{ padding: '10px 14px' }}>{e.performance_score}</td>
                      <td style={{ padding: '10px 14px' }}><StatusBadge status={e.rating} small /></td>
                      <td style={{ padding: '10px 14px', fontWeight: 700, color: e.bonus_amount_kes > 0 ? '#22C55E' : '#9CA3AF' }}>{fmtKES(e.bonus_amount_kes)}</td>
                    </tr>
                  ))}
                  {bonus.employees.length === 0 && <tr><td colSpan={6} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No employees with performance scores yet</td></tr>}
                </tbody>
              </table>
            </div>
          ) : <div style={{ padding: '48px', textAlign: 'center' }}>Calculating...</div>}
        </div>
      )}

      {editBand && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div data-testid="edit-band-modal" style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Edit Pay Band {editBand.band}</h3>
              <button onClick={() => setEditBand(null)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={saveBand} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '14px' }}>
                {[{ k: 'min_kes', l: 'Min (KES)' }, { k: 'mid_kes', l: 'Mid (KES)' }, { k: 'max_kes', l: 'Max (KES)' }].map(f => (
                  <div key={f.k}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.l}</label>
                    <input
                      data-testid={`band-edit-${f.k}`}
                      type="number" required min={0}
                      value={editForm[f.k]}
                      onChange={e => setEditForm(p => ({ ...p, [f.k]: e.target.value }))}
                      style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                ))}
              </div>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Roles (comma-separated)</label>
                <input
                  value={editForm.roles_csv}
                  onChange={e => setEditForm(p => ({ ...p, roles_csv: e.target.value }))}
                  placeholder="Senior Account Manager, Operations Manager"
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Note (optional)</label>
                <input
                  value={editForm.note}
                  onChange={e => setEditForm(p => ({ ...p, note: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" onClick={() => setEditBand(null)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button data-testid="band-edit-save" type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Saving...' : 'Save Band'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
