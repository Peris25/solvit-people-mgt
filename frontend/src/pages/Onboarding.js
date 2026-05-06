import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Onboarding() {
  const { user } = useAuth();
  const [onboarding, setOnboarding] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.getAllOnboarding();
      setOnboarding(res.data);
    } finally { setLoading(false); }
  };

  const updateTask = async (taskId, status) => {
    await api.updateOnboardingTask(taskId, { status });
    load();
  };

  return (
    <div data-testid="onboarding-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Onboarding Tracker</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>{onboarding.length} employees in onboarding/probation</p>
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : onboarding.length === 0 ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>
          No employees currently in onboarding
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {onboarding.map(emp => (
            <div key={emp.id} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 900, fontSize: '15px', color: '#191919', letterSpacing: '-0.02em' }}>{emp.name}</div>
                  <div style={{ fontSize: '12px', color: '#525252', marginTop: '2px' }}>{emp.role} · {emp.department}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '11px', color: '#525252' }}>Progress</div>
                    <div style={{ fontWeight: 900, fontSize: '18px', color: emp.progress_pct === 100 ? '#22C55E' : '#191919' }}>{emp.progress_pct}%</div>
                  </div>
                  <div style={{ width: '80px', height: '6px', backgroundColor: '#F5F5F5', overflow: 'hidden' }}>
                    <div style={{ width: `${emp.progress_pct}%`, height: '100%', backgroundColor: emp.progress_pct === 100 ? '#22C55E' : '#FF353F', transition: 'width 0.3s' }} />
                  </div>
                  <StatusBadge status={emp.lifecycle_state} small />
                  {emp.tasks_overdue > 0 && <span style={{ backgroundColor: '#FEE2E2', color: '#991B1B', fontSize: '10px', fontWeight: 700, padding: '2px 8px' }}>{emp.tasks_overdue} OVERDUE</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
