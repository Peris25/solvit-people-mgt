import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const CATEGORIES = ['Misconduct', 'Gross Misconduct', 'Performance Issue', 'Attendance Issue', 'Policy Violation'];

export default function Disciplinary() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: '', employee_name: '', allegation_category: 'Misconduct', allegation_details: '', incident_date: new Date().toISOString().slice(0, 10), case_type: 'Disciplinary' });
  const [saving, setSaving] = useState(false);

  const canCreate = ['hr_admin', 'hr_manager'].includes(user?.role);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try { const r = await api.getDisCases(); setCases(r.data); }
    finally { setLoading(false); }
  };

  const create = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.createDisCase(form);
      setShowForm(false);
      setForm({ employee_id: '', employee_name: '', allegation_category: 'Misconduct', allegation_details: '', incident_date: new Date().toISOString().slice(0, 10), case_type: 'Disciplinary' });
      load();
    } finally { setSaving(false); }
  };

  return (
    <div data-testid="disciplinary-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Disciplinary & Grievance</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>{cases.length} active cases · confidential</p>
        </div>
        {canCreate && <button data-testid="new-case-btn" onClick={() => setShowForm(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Open Case</button>}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {cases.length === 0 ? <div style={{ padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No cases on record</div> : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Case Ref', 'Employee', 'Type', 'Category', 'Incident Date', 'Status'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {cases.map((c, i) => (
                  <tr key={c.id} data-testid={`case-${c.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '11px', fontWeight: 700, color: '#FF353F' }}>{c.case_ref}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{c.employee_name}</td>
                    <td style={{ padding: '10px 14px' }}><span style={{ fontSize: '10px', backgroundColor: c.case_type === 'Grievance' ? '#DBEAFE' : '#FFEDD5', color: c.case_type === 'Grievance' ? '#1D4ED8' : '#9A3412', padding: '2px 8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{c.case_type}</span></td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{c.allegation_category}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{c.incident_date ? new Date(c.incident_date).toLocaleDateString('en-GB') : '—'}</td>
                    <td style={{ padding: '10px 14px' }}><StatusBadge status={c.status?.replace('_', ' ')} small /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {showForm && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Open Case</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={create} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Employee Name</label>
                  <input required value={form.employee_name} onChange={e => setForm(p => ({ ...p, employee_name: e.target.value, employee_id: e.target.value.toLowerCase().replace(/ /g, '_') }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Type</label>
                  <select value={form.case_type} onChange={e => setForm(p => ({ ...p, case_type: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                    <option>Disciplinary</option>
                    <option>Grievance</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Category</label>
                  <select value={form.allegation_category} onChange={e => setForm(p => ({ ...p, allegation_category: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                    {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Incident Date</label>
                  <input type="date" required value={form.incident_date} onChange={e => setForm(p => ({ ...p, incident_date: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                </div>
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Allegation Details</label>
                <textarea required rows={4} value={form.allegation_details} onChange={e => setForm(p => ({ ...p, allegation_details: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{saving ? 'Opening...' : 'Open Case'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
