import React, { useState, useEffect } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Surveys() {
  const { user } = useAuth();
  const [windows, setWindows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', survey_type: 'alignment_fte', open_date: '', close_date: '' });
  const [saving, setSaving] = useState(false);
  const [activeWindow, setActiveWindow] = useState(null);
  const [results, setResults] = useState(null);

  useEffect(() => { load(); }, []);
  const load = async () => {
    setLoading(true);
    try { const r = await api.getSurveyWindows(); setWindows(r.data); } finally { setLoading(false); }
  };

  const saveWindow = async (e) => {
    e.preventDefault();
    setSaving(true);
    try { await api.createSurveyWindow(form); setShowCreate(false); load(); } finally { setSaving(false); }
  };

  const viewResults = async (w) => {
    setActiveWindow(w);
    const r = await api.getSurveyResults(w.id);
    setResults(r.data);
  };

  const pillars = ['Environment', 'Values', 'Rewards'];

  return (
    <div data-testid="surveys-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Alignment Surveys</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>FTE and Solver engagement surveys</p>
        </div>
        {['hr_admin', 'hr_manager'].includes(user?.role) && (
          <button data-testid="create-survey-btn" onClick={() => setShowCreate(true)} style={{ padding: '10px 20px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Create Survey</button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div>
          <h3 style={{ fontWeight: 900, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '12px' }}>Survey Windows</h3>
          {loading ? <div style={{ padding: '32px', textAlign: 'center' }}>Loading...</div> : windows.map(w => (
            <div key={w.id} data-testid={`survey-window-${w.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px', marginBottom: '10px' }}>
              <div style={{ fontWeight: 700, fontSize: '14px', color: '#191919', marginBottom: '4px' }}>{w.title}</div>
              <div style={{ fontSize: '11px', color: '#525252', marginBottom: '8px' }}>{w.survey_type?.replace('_', ' ').toUpperCase()} · {w.open_date} to {w.close_date}</div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span style={{ backgroundColor: w.status === 'Open' ? '#DCFCE7' : '#F3F4F6', color: w.status === 'Open' ? '#166534' : '#374151', fontSize: '10px', fontWeight: 700, padding: '2px 8px', textTransform: 'uppercase' }}>{w.status}</span>
                <span style={{ fontSize: '11px', color: '#525252' }}>{w.response_count} responses</span>
                <button onClick={() => viewResults(w)} style={{ marginLeft: 'auto', padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>View Results</button>
              </div>
            </div>
          ))}
          {windows.length === 0 && !loading && <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No surveys created yet</div>}
        </div>

        {results && activeWindow && (
          <div>
            <h3 style={{ fontWeight: 900, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '12px' }}>Results: {activeWindow.title}</h3>
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                <div style={{ fontSize: '48px', fontWeight: 900, letterSpacing: '-0.05em', color: results.overall >= 75 ? '#22C55E' : results.overall >= 50 ? '#F59E0B' : '#EF4444' }}>{results.overall}%</div>
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Overall Alignment</div>
                <div style={{ fontSize: '12px', color: '#525252', marginTop: '4px' }}>{results.response_count} responses</div>
              </div>
              {pillars.map((p, i) => {
                const score = [results.pillar_1, results.pillar_2, results.pillar_3][i];
                return (
                  <div key={p} style={{ marginBottom: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#191919' }}>{p}</span>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#191919' }}>{score}%</span>
                    </div>
                    <div style={{ height: '8px', backgroundColor: '#F5F5F5', overflow: 'hidden' }}>
                      <div style={{ width: `${score}%`, height: '100%', backgroundColor: score >= 75 ? '#22C55E' : score >= 50 ? '#F59E0B' : '#EF4444', transition: 'width 0.5s' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '440px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Create Survey Window</h3>
              <button onClick={() => setShowCreate(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={saveWindow} style={{ padding: '24px' }}>
              {[{ key: 'title', label: 'Survey Title', type: 'text' }, { key: 'open_date', label: 'Open Date', type: 'date' }, { key: 'close_date', label: 'Close Date', type: 'date' }].map(f => (
                <div key={f.key} style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{f.label}</label>
                  <input type={f.type} required value={form[f.key]} onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', boxSizing: 'border-box', outline: 'none' }} />
                </div>
              ))}
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Survey Type</label>
                <select value={form.survey_type} onChange={e => setForm(p => ({ ...p, survey_type: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Arial', outline: 'none' }}>
                  <option value="alignment_fte">FTE Alignment Survey</option>
                  <option value="alignment_solver">Solver Alignment Survey</option>
                  <option value="engagement_fte">FTE Engagement Survey</option>
                  <option value="satisfaction_solver">Solver Satisfaction Pulse</option>
                </select>
              </div>
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowCreate(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Arial' }}>Cancel</button>
                <button type="submit" disabled={saving} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Arial' }}>Create Survey</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
