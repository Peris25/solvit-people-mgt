import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const VALUES = ['Integrity', 'Hard Work & Ownership', 'Teamwork & Decency', 'Solution Orientation', 'Timeliness'];

export default function Recognition() {
  const { user } = useAuth();
  const [recs, setRecs] = useState([]);
  const [solverAwards, setSolverAwards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('peer');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ nominee_id: '', nominee_name: '', values_demonstrated: [], specific_behaviour: '', impact: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([api.getRecognitions(), api.getSolverAwards()]);
      setRecs(r.data);
      setSolverAwards(s.data);
    } finally { setLoading(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createPeerNomination(form);
      setShowForm(false);
      setForm({ nominee_id: '', nominee_name: '', values_demonstrated: [], specific_behaviour: '', impact: '' });
      load();
    } finally { setSaving(false); }
  };

  const toggleValue = (v) => setForm(p => ({ ...p, values_demonstrated: p.values_demonstrated.includes(v) ? p.values_demonstrated.filter(x => x !== v) : [...p.values_demonstrated, v] }));

  const peerRecs = recs.filter(r => r.recognition_type === 'Peer');
  const mgrRecs = recs.filter(r => r.recognition_type === 'Manager');

  return (
    <div data-testid="recognition-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Recognition</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Peer Nominations · Manager Recognition · Solver Awards · Long Service</p>
        </div>
        <button data-testid="nominate-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Nominate Peer</button>
      </div>

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {[{ k: 'peer', l: `Peer (${peerRecs.length})` }, { k: 'manager', l: `Manager (${mgrRecs.length})` }, { k: 'solver', l: `Solver Awards (${solverAwards.length})` }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
          {(tab === 'peer' ? peerRecs : tab === 'manager' ? mgrRecs : []).map(r => (
            <div key={r.id} data-testid={`recognition-${r.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div style={{ fontWeight: 900, fontSize: '14px', color: '#191919' }}>{r.nominee_name}</div>
                  <div style={{ fontSize: '11px', color: '#525252' }}>by {r.nominator_name}</div>
                </div>
                <StatusBadge status={r.status} small />
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '10px' }}>
                {(r.values_demonstrated || []).map(v => <span key={v} style={{ fontSize: '10px', backgroundColor: '#FFEDD5', color: '#9A3412', padding: '2px 8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{v}</span>)}
              </div>
              <p style={{ fontSize: '12px', color: '#191919', lineHeight: 1.5, margin: '8px 0' }}>{r.specific_behaviour}</p>
              <p style={{ fontSize: '11px', color: '#525252', lineHeight: 1.5, margin: 0 }}><strong>Impact:</strong> {r.impact}</p>
            </div>
          ))}
          {tab === 'solver' && solverAwards.map(a => (
            <div key={a.id} style={{ backgroundColor: '#fff', border: '2px solid #F97316', padding: '16px' }}>
              <div style={{ fontWeight: 900, fontSize: '14px' }}>{a.solver_name || a.nominee_name}</div>
              <div style={{ fontSize: '11px', color: '#F97316', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '4px 0' }}>{a.award_tier}</div>
              <div style={{ fontSize: '14px', fontWeight: 900, color: '#191919' }}>KES {Number(a.award_amount_kes || 0).toLocaleString('en-KE')}</div>
              <div style={{ marginTop: '8px' }}><StatusBadge status={a.status?.replace('Pending_', '')} small /></div>
            </div>
          ))}
          {((tab === 'peer' && peerRecs.length === 0) || (tab === 'manager' && mgrRecs.length === 0) || (tab === 'solver' && solverAwards.length === 0)) && (
            <div style={{ gridColumn: '1 / -1', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No recognition entries yet</div>
          )}
        </div>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Peer Nomination</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={submit} style={{ padding: '24px' }}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Nominee Name</label>
                <input required value={form.nominee_name} onChange={e => setForm(p => ({ ...p, nominee_name: e.target.value, nominee_id: e.target.value.toLowerCase().replace(/ /g, '_') }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '8px' }}>Values Demonstrated</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {VALUES.map(v => <label key={v} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer' }}><input type="checkbox" checked={form.values_demonstrated.includes(v)} onChange={() => toggleValue(v)} />{v}</label>)}
                </div>
              </div>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Specific Behaviour</label>
                <textarea required rows={3} value={form.specific_behaviour} onChange={e => setForm(p => ({ ...p, specific_behaviour: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Impact</label>
                <textarea required rows={2} value={form.impact} onChange={e => setForm(p => ({ ...p, impact: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Submitting...' : 'Nominate'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
