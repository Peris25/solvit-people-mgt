import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import EmployeePicker from '../components/EmployeePicker';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtKES = (n) => n != null ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';

export default function LnD() {
  const { user } = useAuth();
  const [tab, setTab] = useState('training');
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    employee_id: user?.employee_id || user?.id || '',
    training_name: '', provider: '', delivery_method: 'External',
    cost_kes: '', duration_days: 1, business_justification: '',
    proposed_start_date: '', proposed_end_date: ''
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.getTrainingRequests();
      setRequests(r.data);
    } finally { setLoading(false); }
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createTrainingRequest({
        ...form,
        cost_kes: parseFloat(form.cost_kes) || 0,
        duration_days: parseInt(form.duration_days) || 1
      });
      setShowForm(false);
      setForm({ ...form, training_name: '', provider: '', cost_kes: '', business_justification: '' });
      load();
    } finally { setSaving(false); }
  };

  const decide = async (id, decision) => {
    await api.trainingDecision(id, { decision });
    load();
  };

  return (
    <div data-testid="lnd-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Learning & Development</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Individual Development Plans · Training Requests · Skills Matrix</p>
        </div>
        <button data-testid="add-training-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Request Training</button>
      </div>

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {[{ k: 'training', l: 'Training Requests' }, { k: 'idp', l: 'IDP Plans' }, { k: 'skills', l: 'Skills Matrix' }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {tab === 'training' && (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ backgroundColor: '#F5F5F5' }}>
                  {['Training', 'Provider', 'Cost', 'Days', 'Status', 'Actions'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {requests.map((r, i) => (
                  <tr key={r.id} data-testid={`training-row-${r.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.training_name}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{r.provider}</td>
                    <td style={{ padding: '10px 14px', color: '#191919', fontWeight: 700 }}>{fmtKES(r.cost_kes)}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{r.duration_days}</td>
                    <td style={{ padding: '10px 14px' }}><StatusBadge status={r.status?.replace('Pending_', '').replace('_', ' ')} small /></td>
                    <td style={{ padding: '10px 14px' }}>
                      {['hr_admin', 'hr_manager', 'line_manager'].includes(user?.role) && r.status?.startsWith('Pending') && (
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button onClick={() => decide(r.id, 'Approve')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #22C55E', color: '#22C55E', background: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Approve</button>
                          <button onClick={() => decide(r.id, 'Reject')} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Reject</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {requests.length === 0 && <tr><td colSpan={6} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No training requests</td></tr>}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'idp' && (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#525252' }}>
          <p style={{ fontSize: '14px', fontWeight: 700, color: '#191919' }}>Individual Development Plans</p>
          <p style={{ fontSize: '12px' }}>Visit an employee profile to view or edit their IDP. Career aspirations, goals, and development priorities are captured per employee.</p>
        </div>
      )}

      {tab === 'skills' && <SkillsMatrixPanel user={user} />}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Request Training</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={submit} style={{ padding: '24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              {[
                { k: 'training_name', l: 'Training Name', type: 'text', span: true },
                { k: 'provider', l: 'Provider', type: 'text' },
                { k: 'delivery_method', l: 'Delivery', type: 'select', options: ['External', 'Internal', 'Online', 'Mixed'] },
                { k: 'cost_kes', l: 'Cost (KES)', type: 'number' },
                { k: 'duration_days', l: 'Duration (days)', type: 'number' },
                { k: 'proposed_start_date', l: 'Start Date', type: 'date' },
                { k: 'proposed_end_date', l: 'End Date', type: 'date' },
                { k: 'business_justification', l: 'Business Justification', type: 'textarea', span: true },
              ].map(f => (
                <div key={f.k} style={{ gridColumn: f.span ? '1 / -1' : 'auto' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.l}</label>
                  {f.type === 'select' ? (
                    <select value={form[f.k]} onChange={e => setForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box' }}>
                      {f.options.map(o => <option key={o}>{o}</option>)}
                    </select>
                  ) : f.type === 'textarea' ? (
                    <textarea value={form[f.k]} onChange={e => setForm(p => ({ ...p, [f.k]: e.target.value }))} required rows={3} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', resize: 'vertical' }} />
                  ) : (
                    <input type={f.type} required={['training_name', 'provider', 'business_justification'].includes(f.k)} value={form[f.k] || ''} onChange={e => setForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box' }} />
                  )}
                </div>
              ))}
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Arial' }}>Cancel</button>
                <button data-testid="submit-training-btn" type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>{saving ? 'Submitting...' : 'Submit Request'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Expert'];
const LEVEL_COLOR = { Beginner: '#9CA3AF', Intermediate: '#3B82F6', Advanced: '#22C55E', Expert: '#FF353F' };

function SkillsMatrixPanel({ user }) {
  const myEmpId = user?.employee_id || user?.id;
  const canEditAny = ['hr_admin', 'hr_manager', 'line_manager'].includes(user?.role);
  const [empId, setEmpId] = useState(myEmpId || '');
  const [empName, setEmpName] = useState('');
  const [skills, setSkills] = useState([]);
  const [newSkill, setNewSkill] = useState('');
  const [newLevel, setNewLevel] = useState('Intermediate');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await api.getSkillsMatrix(id);
      setSkills(r.data?.skills || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { if (empId) load(empId); }, [empId]);

  const canEdit = canEditAny || empId === myEmpId;

  const save = async (next) => {
    setSaving(true);
    try {
      await api.updateSkillsMatrix(empId, { skills: next });
      setSkills(next);
    } finally { setSaving(false); }
  };

  const addSkill = () => {
    if (!newSkill.trim()) return;
    const next = [...skills, { name: newSkill.trim(), level: newLevel }];
    setNewSkill('');
    save(next);
  };

  const updateLevel = (idx, level) => {
    const next = skills.map((s, i) => i === idx ? { ...s, level } : s);
    save(next);
  };

  const removeSkill = (idx) => save(skills.filter((_, i) => i !== idx));

  return (
    <div data-testid="skills-matrix-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', marginBottom: '20px' }}>
        <div style={{ minWidth: '280px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>Employee</label>
          <EmployeePicker
            testId="skills-emp-picker"
            value={empId}
            placeholder="Select employee..."
            onChange={(e) => { setEmpId(e.id); setEmpName(e.full_name); }}
          />
        </div>
        {empId === myEmpId && <div style={{ padding: '8px 14px', backgroundColor: '#F5F5F5', fontSize: '11px', color: '#525252', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' }}>My Skills</div>}
      </div>

      {loading ? <div style={{ padding: '24px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', marginBottom: '20px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Skill', 'Level', canEdit ? 'Action' : ''].filter(Boolean).map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontWeight: 700, fontFamily: 'Barlow' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {skills.map((s, i) => (
                <tr key={i} data-testid={`skill-row-${i}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{s.name}</td>
                  <td style={{ padding: '10px 14px' }}>
                    {canEdit ? (
                      <select value={s.level} onChange={e => updateLevel(i, e.target.value)} style={{ padding: '4px 8px', fontSize: '11px', border: '1px solid rgba(25,25,25,0.15)', fontFamily: 'Nunito Sans' }}>
                        {LEVELS.map(L => <option key={L} value={L}>{L}</option>)}
                      </select>
                    ) : (
                      <span style={{ display: 'inline-block', padding: '2px 8px', fontSize: '10px', fontWeight: 700, color: '#fff', backgroundColor: LEVEL_COLOR[s.level] || '#525252', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.level}</span>
                    )}
                  </td>
                  {canEdit && (
                    <td style={{ padding: '10px 14px' }}>
                      <button data-testid={`skill-remove-${i}`} onClick={() => removeSkill(i)} style={{ padding: '3px 8px', fontSize: '10px', border: '1px solid #FF353F', color: '#FF353F', background: 'transparent', cursor: 'pointer', fontFamily: 'Barlow', fontWeight: 700 }}>Remove</button>
                    </td>
                  )}
                </tr>
              ))}
              {skills.length === 0 && <tr><td colSpan={canEdit ? 3 : 2} style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF' }}>No skills recorded yet.</td></tr>}
            </tbody>
          </table>

          {canEdit && (
            <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', borderTop: '1px solid rgba(25,25,25,0.08)', paddingTop: '16px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>Add Skill</label>
                <input data-testid="new-skill-input" value={newSkill} onChange={e => setNewSkill(e.target.value)} placeholder="e.g. SQL, Negotiation, Inspection routing" style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' }}>Level</label>
                <select value={newLevel} onChange={e => setNewLevel(e.target.value)} style={{ padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans' }}>
                  {LEVELS.map(L => <option key={L}>{L}</option>)}
                </select>
              </div>
              <button data-testid="add-skill-btn" onClick={addSkill} disabled={saving || !newSkill.trim()} style={{ padding: '9px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{saving ? 'Saving…' : 'Add'}</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
