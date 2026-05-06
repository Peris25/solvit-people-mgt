import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Retention() {
  const { user } = useAuth();
  const [risks, setRisks] = useState([]);
  const [summary, setSummary] = useState(null);
  const [exitInsights, setExitInsights] = useState([]);
  const [tab, setTab] = useState('flight-risk');
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [risksRes, summaryRes, exitRes] = await Promise.all([
        api.getFlightRisks(),
        api.getRiskSummary(),
        api.getExitInsights()
      ]);
      setRisks(risksRes.data);
      setSummary(summaryRes.data);
      setExitInsights(exitRes.data);
    } finally { setLoading(false); }
  };

  const calcRisk = async (empId) => {
    await api.calculateRisk(empId);
    load();
  };

  const RISK_COLORS = { Low: '#22C55E', Elevated: '#F59E0B', High: '#F97316', Critical: '#EF4444', Unknown: '#9CA3AF' };

  return (
    <div data-testid="retention-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Retention & Flight Risk</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Proactive retention intelligence</p>
      </div>

      {summary && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
          {Object.entries(RISK_COLORS).map(([level, color]) => (
            <div key={level} style={{ backgroundColor: '#fff', border: `2px solid ${color}20`, padding: '16px 20px', flex: 1 }}>
              <div style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color }}>{summary[level] || 0}</div>
              <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginTop: '2px' }}>{level} Risk</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {['flight-risk', 'exit-insights'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t ? 700 : 400, color: tab === t ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {t === 'flight-risk' ? 'Flight Risk Tracker' : 'Exit Insights'}
          </button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'flight-risk' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Employee', 'Role', 'Dept', 'Tenure', 'Risk Score', 'Risk Level', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {risks.map((emp, i) => {
                const tenure = emp.start_date ? Math.round((Date.now() - new Date(emp.start_date)) / 31536000000 * 10) / 10 : 0;
                return (
                  <tr key={emp.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700, color: '#191919' }}>{emp.full_name}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{emp.role_title}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{emp.department}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{tenure}y</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{emp.flight_risk_score ?? '—'}</td>
                    <td style={{ padding: '10px 14px' }}>{emp.flight_risk_level ? <StatusBadge status={emp.flight_risk_level} small /> : <span style={{ color: '#9CA3AF' }}>Not calculated</span>}</td>
                    <td style={{ padding: '10px 14px' }}>
                      <button onClick={() => calcRisk(emp.id)} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Calc Risk</button>
                    </td>
                  </tr>
                );
              })}
              {risks.length === 0 && <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No active employees</td></tr>}
            </tbody>
          </table>
        </div>
      ) : (
        <div>
          <div style={{ backgroundColor: '#FFF3CD', border: '1px solid #F59E0B', padding: '12px 16px', marginBottom: '16px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#92400E', marginBottom: '4px' }}>Exit Interview Insights Tracker</div>
            <div style={{ fontSize: '12px', color: '#78350F' }}>Pre-loaded with Stephen Kiragu exit data (April 2026)</div>
          </div>
          {exitInsights.map(ei => (
            <div key={ei.id} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px', marginBottom: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div>
                  <div style={{ fontWeight: 900, fontSize: '16px', color: '#191919' }}>{ei.employee_name}</div>
                  <div style={{ fontSize: '12px', color: '#525252', marginTop: '2px' }}>{ei.role_title} · {ei.department} · {ei.tenure_years} years tenure</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', color: '#525252' }}>Exit Date</div>
                  <div style={{ fontWeight: 700, fontSize: '13px' }}>{ei.exit_date}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                {(ei.exit_codes || []).map(code => (
                  <span key={code} style={{ backgroundColor: '#FEE2E2', color: '#991B1B', fontSize: '11px', fontWeight: 700, padding: '3px 10px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    {code}: {ei.exit_code_descriptions?.[code] || code}
                  </span>
                ))}
              </div>
              {ei.insights && (
                <div style={{ backgroundColor: '#F9FAFB', border: '1px solid rgba(25,25,25,0.06)', padding: '12px', fontSize: '12px', color: '#374151' }}>
                  <strong>Key finding:</strong> {ei.insights.main_reason}
                </div>
              )}
            </div>
          ))}
          {exitInsights.length === 0 && <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No exit interviews recorded</div>}
        </div>
      )}
    </div>
  );
}
