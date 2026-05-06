import React, { useState, useEffect } from 'react';
import * as api from '../services/api';

const fmtKES = (n) => n != null ? `KES ${Number(n).toLocaleString('en-KE', { maximumFractionDigits: 2 })}` : '—';

export default function Compliance() {
  const [tab, setTab] = useState('paye');
  const [statutory, setStatutory] = useState([]);
  const [deadlines, setDeadlines] = useState(null);
  const [paye, setPaye] = useState(null);
  const [gross, setGross] = useState(75000);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getStatutoryStatus().catch(() => ({ data: [] })),
      api.getComplianceDeadlines().catch(() => ({ data: null }))
    ]).then(([s, d]) => {
      setStatutory(s.data);
      setDeadlines(d.data);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    api.getPAYECalculator(gross).then(r => setPaye(r.data)).catch(() => {});
  }, [gross]);

  return (
    <div data-testid="compliance-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Statutory Compliance</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Kenya — PAYE · NSSF · SHA · Affordable Housing Levy</p>
      </div>

      {/* Deadlines banner */}
      {deadlines && (
        <div style={{ backgroundColor: '#FFF7ED', border: '1px solid #F97316', padding: '14px 18px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#9A3412' }}>Upcoming Deadlines</div>
            <div style={{ display: 'flex', gap: '20px', marginTop: '6px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '12px', color: '#7C2D12' }}><strong>NSSF/SHA:</strong> {deadlines.nssf_sha_deadline}</span>
              <span style={{ fontSize: '12px', color: '#7C2D12' }}><strong>PAYE:</strong> {deadlines.paye_deadline}</span>
            </div>
          </div>
          <div style={{ fontSize: '11px', color: '#7C2D12', fontStyle: 'italic' }}>{deadlines.note}</div>
        </div>
      )}

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {[{ k: 'paye', l: 'PAYE Calculator' }, { k: 'remit', l: `Remittance Log (${statutory.length})` }, { k: 'rates', l: 'Statutory Rates' }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'paye' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
          <h3 style={{ fontWeight: 900, fontSize: '16px', margin: '0 0 16px', color: '#191919' }}>PAYE / NSSF / SHA Calculator</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
            <label style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>Gross Salary (KES):</label>
            <input data-testid="gross-input" type="number" value={gross} onChange={e => setGross(parseFloat(e.target.value) || 0)} style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '14px', fontFamily: 'Arial', width: '160px', fontWeight: 700 }} />
          </div>
          {paye && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
              {[
                { label: 'Gross Salary', value: paye.gross_salary_kes, color: '#191919' },
                { label: 'PAYE (Income Tax)', value: paye.paye_kes, color: '#FF353F' },
                { label: 'NSSF (Employee)', value: paye.nssf_employee_kes, color: '#F97316' },
                { label: 'SHA (2.75%)', value: paye.sha_kes, color: '#F97316' },
                { label: 'Total Deductions', value: paye.total_deductions_kes, color: '#FF353F' },
                { label: 'Net Pay', value: paye.net_pay_kes, color: '#22C55E' },
              ].map(s => (
                <div key={s.label} style={{ padding: '14px 18px', border: `1px solid ${s.color}33`, backgroundColor: `${s.color}08` }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '4px' }}>{s.label}</div>
                  <div style={{ fontSize: '18px', fontWeight: 900, letterSpacing: '-0.03em', color: s.color }}>{fmtKES(s.value)}</div>
                </div>
              ))}
            </div>
          )}
          <p style={{ fontSize: '11px', color: '#525252', marginTop: '16px', fontStyle: 'italic' }}>Personal relief KES 2,400/month applied. Calculations per Kenya Income Tax Act Cap 470 (2023 rates), NSSF Act 2013 and Social Health Insurance Act 2023.</p>
        </div>
      ) : tab === 'remit' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {statutory.length === 0 ? <div style={{ padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No remittance records yet</div> : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Period', 'Type', 'Amount', 'Status', 'Recorded'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {statutory.map((s, i) => (
                  <tr key={s.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{s.period}</td>
                    <td style={{ padding: '10px 14px' }}>{s.statutory_type}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{fmtKES(s.amount_kes)}</td>
                    <td style={{ padding: '10px 14px' }}>{s.status}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{s.recorded_at ? new Date(s.recorded_at).toLocaleDateString('en-GB') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
          <h3 style={{ fontWeight: 900, fontSize: '16px', margin: '0 0 16px' }}>Kenya Statutory Rates (2026)</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <tbody>
              {[
                ['PAYE Band 1 (0 – 24,000)', '10%'],
                ['PAYE Band 2 (24,001 – 32,333)', '25%'],
                ['PAYE Band 3 (32,334 – 500,000)', '30%'],
                ['PAYE Band 4 (above 500,000)', '32.5%'],
                ['Personal Relief', 'KES 2,400 / month'],
                ['NSSF Tier 1 (≤ 6,000)', '6% employee + 6% employer'],
                ['NSSF Tier 2 (6,001 – 18,000)', '6% employee + 6% employer'],
                ['SHA (Social Health)', '2.75% of gross'],
                ['Affordable Housing Levy', '1.5% employee + 1.5% employer'],
              ].map(([k, v]) => (
                <tr key={k} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{k}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
