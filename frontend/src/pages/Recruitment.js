import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const STAGES = ['Stage 1: Competency Test', 'Stage 2: Values Assessment', 'Stage 3: Growth Mindset', 'Stage 4: Physical Interview', 'Offer Made', 'Offer Accepted', 'Rejected', 'Withdrawn'];

export default function Recruitment() {
  const { user } = useAuth();
  const [pipeline, setPipeline] = useState({});
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ full_name: '', email: '', position_applied: '', department: 'Operations', role_level: 'L2', candidate_type: 'FTE', source: 'Direct' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.getRecruitmentPipeline();
      setPipeline(res.data);
    } finally { setLoading(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createCandidate(form);
      setShowForm(false);
      load();
    } finally { setSaving(false); }
  };

  const moveStage = async (candidateId, newStage) => {
    await api.updateCandidate(candidateId, { stage: newStage });
    load();
  };

  const totalCandidates = Object.values(pipeline).reduce((s, v) => s + (v?.count || 0), 0);

  return (
    <div data-testid="recruitment-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Recruitment Pipeline</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>{totalCandidates} active candidates</p>
        </div>
        {['hr_admin', 'hr_manager'].includes(user?.role) && (
          <button data-testid="add-candidate-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Add Candidate</button>
        )}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          {STAGES.slice(0, 4).map(stage => {
            const stageData = pipeline[stage] || { candidates: [], count: 0 };
            return (
              <div key={stage} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
                <div style={{ padding: '10px 14px', borderBottom: '2px solid #191919', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#191919' }}>{stage.split(': ')[1] || stage}</span>
                  <span style={{ backgroundColor: '#191919', color: '#fff', width: '20px', height: '20px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', fontWeight: 900 }}>{stageData.count}</span>
                </div>
                <div style={{ padding: '10px', maxHeight: '500px', overflowY: 'auto' }}>
                  {stageData.candidates.map(c => (
                    <div key={c.id} style={{ padding: '10px', border: '1px solid rgba(25,25,25,0.06)', marginBottom: '8px', backgroundColor: '#FAFAFA' }}>
                      <div style={{ fontWeight: 700, fontSize: '12px', color: '#191919' }}>{c.full_name}</div>
                      <div style={{ fontSize: '11px', color: '#525252', margin: '2px 0' }}>{c.position_applied}</div>
                      <div style={{ fontSize: '10px', color: '#9CA3AF' }}>{c.department} · {c.role_level}</div>
                      <div style={{ display: 'flex', gap: '4px', marginTop: '8px' }}>
                        {STAGES.indexOf(stage) < STAGES.length - 3 && (
                          <button onClick={() => moveStage(c.id, STAGES[STAGES.indexOf(stage) + 1])} style={{ padding: '3px 8px', fontSize: '10px', border: '1px solid #22C55E', backgroundColor: 'transparent', color: '#22C55E', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>→ Next</button>
                        )}
                        <button onClick={() => moveStage(c.id, 'Rejected')} style={{ padding: '3px 8px', fontSize: '10px', border: '1px solid #FF353F', backgroundColor: 'transparent', color: '#FF353F', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>✗ Reject</button>
                      </div>
                    </div>
                  ))}
                  {stageData.count === 0 && <div style={{ textAlign: 'center', padding: '20px', color: '#9CA3AF', fontSize: '11px' }}>No candidates</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '480px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Add Candidate</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={save} style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {[{ key: 'full_name', label: 'Full Name', type: 'text' }, { key: 'email', label: 'Email', type: 'email' }, { key: 'position_applied', label: 'Position Applied', type: 'text' }].map(f => (
                <div key={f.key} style={{ gridColumn: f.key === 'position_applied' ? '1 / -1' : 'auto' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                  <input type={f.type} required value={form[f.key] || ''} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                </div>
              ))}
              {[{ key: 'department', label: 'Department', options: ['Operations', 'Commercial', 'Finance', 'Technology', 'HR_People'] }, { key: 'role_level', label: 'Level', options: ['L1', 'L2', 'L3', 'L4', 'L5'] }, { key: 'candidate_type', label: 'Type', options: ['FTE', 'Solver'] }].map(f => (
                <div key={f.key}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                  <select value={form[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                    {f.options.map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
              ))}
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Arial' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>
                  {saving ? 'Adding...' : 'Add Candidate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
