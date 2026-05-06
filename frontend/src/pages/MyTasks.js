import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';

export default function MyTasks() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getMyFormTasks()
      .then(r => setTasks(r.data || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div data-testid="my-tasks-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>My Tasks</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Forms awaiting your sign-off · sequential workflow routing</p>
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tasks.length === 0 ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>
          🎉 No tasks awaiting your input. You're all caught up.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '12px' }}>
          {tasks.map(t => (
            <div key={t.id} data-testid={`mytask-${t.id}`} style={{ backgroundColor: '#fff', border: '2px solid #FF353F', padding: '18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div style={{ fontSize: '10px', fontWeight: 700, color: '#FF353F', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{t.form_id}</div>
                <span style={{ fontSize: '9px', backgroundColor: '#FEE2E2', color: '#991B1B', padding: '2px 8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Step {(t.current_step_index || 0) + 1} / {(t.completing_users_sequence || []).length}</span>
              </div>
              <div style={{ fontSize: '14px', fontWeight: 900, color: '#191919', marginBottom: '6px', letterSpacing: '-0.02em' }}>{t.form_title}</div>
              {t.subject_employee_name && <div style={{ fontSize: '12px', color: '#525252', marginBottom: '4px' }}>Subject: <strong>{t.subject_employee_name}</strong></div>}
              <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                {(t.completing_users_sequence || []).map((r, idx) => (
                  <React.Fragment key={idx}>
                    {idx > 0 && <span style={{ fontSize: '11px', color: '#9CA3AF' }}>→</span>}
                    <span style={{ fontSize: '9px', backgroundColor: idx === t.current_step_index ? '#FF353F' : (idx < (t.current_step_index || 0) ? '#22C55E' : '#F5F5F5'), color: idx <= (t.current_step_index || 0) ? '#fff' : '#525252', padding: '2px 8px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                      {idx < (t.current_step_index || 0) ? '✓ ' : ''}{r.replace('_', ' ')}
                    </span>
                  </React.Fragment>
                ))}
              </div>
              <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '8px' }}>Started {t.created_at ? new Date(t.created_at).toLocaleDateString('en-GB') : '—'}</div>
              <button onClick={() => navigate(`/forms?submission=${t.id}`)} style={{ marginTop: '12px', padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>Open & Sign</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
