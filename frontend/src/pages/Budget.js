import React, { useState, useEffect } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtKES = (n) => n != null ? `KES ${Number(n).toLocaleString('en-KE')}` : '—';
const COLORS = ['#FF353F', '#3B82F6', '#22C55E', '#F97316', '#8B5CF6', '#06B6D4', '#EC4899'];

export default function Budget() {
  const [envelope, setEnvelope] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getPeopleEnvelope(), api.getBudgetSummary()])
      .then(([e, s]) => { setEnvelope(e.data); setSummary(s.data); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: '48px', textAlign: 'center' }}>Loading budget data...</div>;

  const utilisation = envelope?.utilization_pct || 0;
  const utilColor = utilisation > 95 ? '#FF353F' : utilisation > 80 ? '#F97316' : '#22C55E';

  return (
    <div data-testid="budget-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Budget Governance</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>People Cost Envelope (50% of GP) · Headcount Budget</p>
      </div>

      {/* Envelope card */}
      <div style={{ backgroundColor: '#191919', color: '#fff', padding: '32px', marginBottom: '20px' }}>
        <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: 'rgba(255,255,255,0.5)', marginBottom: '8px' }}>People Cost Envelope · {envelope?.period || 'Current Period'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px', marginTop: '24px' }}>
          {[
            { label: 'GP Actual', value: fmtKES(envelope?.actual_gp_kes), color: '#fff' },
            { label: 'Envelope (50%)', value: fmtKES(envelope?.people_cost_envelope_kes), color: '#FF353F' },
            { label: 'Total Cost', value: fmtKES(envelope?.total_people_cost_kes || summary?.total_monthly_salary_kes), color: '#fff' },
            { label: 'Headroom', value: fmtKES(envelope?.headroom_kes), color: '#22C55E' },
          ].map(s => (
            <div key={s.label}>
              <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'rgba(255,255,255,0.5)' }}>{s.label}</div>
              <div style={{ fontSize: '22px', fontWeight: 900, color: s.color, letterSpacing: '-0.04em', marginTop: '4px' }}>{s.value}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'rgba(255,255,255,0.5)' }}>Utilization</span>
            <span style={{ fontSize: '14px', fontWeight: 900, color: utilColor }}>{utilisation}%</span>
          </div>
          <div style={{ height: '8px', backgroundColor: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(utilisation, 100)}%`, height: '100%', backgroundColor: utilColor, transition: 'width 0.5s' }} />
          </div>
        </div>
      </div>

      {/* Summary KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '24px' }}>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>Headcount</div>
          <div style={{ fontSize: '36px', fontWeight: 900, letterSpacing: '-0.05em', marginTop: '8px' }}>{summary?.headcount || 0}</div>
        </div>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>Total Monthly Salary</div>
          <div style={{ fontSize: '24px', fontWeight: 900, letterSpacing: '-0.04em', marginTop: '8px' }}>{fmtKES(summary?.total_monthly_salary_kes)}</div>
        </div>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: '#525252' }}>Avg Salary</div>
          <div style={{ fontSize: '24px', fontWeight: 900, letterSpacing: '-0.04em', marginTop: '8px' }}>{fmtKES(summary?.average_salary_kes)}</div>
        </div>
      </div>

      {/* Department breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', fontWeight: 700, fontSize: '13px', backgroundColor: '#F5F5F5' }}>By Department</div>
          <div style={{ padding: '16px' }}>
            {Object.entries(summary?.by_department || {}).sort((a, b) => b[1] - a[1]).map(([dept, cost], i) => {
              const pct = summary.total_monthly_salary_kes > 0 ? (cost / summary.total_monthly_salary_kes * 100) : 0;
              return (
                <div key={dept} style={{ marginBottom: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 700 }}>{dept}</span>
                    <span style={{ color: '#525252' }}>{fmtKES(cost)} · {pct.toFixed(1)}%</span>
                  </div>
                  <div style={{ height: '4px', backgroundColor: '#F5F5F5' }}>
                    <div style={{ width: `${pct}%`, height: '100%', backgroundColor: COLORS[i % COLORS.length] }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(25,25,25,0.08)', fontWeight: 700, fontSize: '13px', backgroundColor: '#F5F5F5' }}>By Pay Band</div>
          <div style={{ padding: '16px' }}>
            {Object.entries(summary?.by_level || {}).sort().map(([lvl, cost], i) => {
              const pct = summary.total_monthly_salary_kes > 0 ? (cost / summary.total_monthly_salary_kes * 100) : 0;
              return (
                <div key={lvl} style={{ marginBottom: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 700 }}>Band {lvl}</span>
                    <span style={{ color: '#525252' }}>{fmtKES(cost)} · {pct.toFixed(1)}%</span>
                  </div>
                  <div style={{ height: '4px', backgroundColor: '#F5F5F5' }}>
                    <div style={{ width: `${pct}%`, height: '100%', backgroundColor: COLORS[i % COLORS.length] }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
