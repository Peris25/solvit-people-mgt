import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Retention() {
  const { user } = useAuth();
  const [risks, setRisks] = useState([]);
  const [summary, setSummary] = useState(null);
  const [exitInsights, setExitInsights] = useState([]);
  const [stayInterviews, setStayInterviews] = useState([]);
  const [tab, setTab] = useState('flight-risk');
  const [loading, setLoading] = useState(true);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showConduct, setShowConduct] = useState(null);
  const [scheduleForm, setScheduleForm] = useState({ employee_id: '', employee_name: '', scheduled_date: '', trigger_reason: '' });
  const [conductForm, setConductForm] = useState({});
  const [attrition, setAttrition] = useState(null);

  useEffect(() => {
    load();
    if (['hr_admin', 'hr_manager', 'executive'].includes(user?.role)) {
      api.getVoluntaryAttrition().then(r => setAttrition(r.data)).catch(() => {});
    }
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [risksRes, summaryRes, exitRes, stayRes] = await Promise.all([
        api.getFlightRisks(),
        api.getRiskSummary(),
        api.getExitInsights(),
        api.getStayInterviews()
      ]);
      setRisks(risksRes.data);
      setSummary(summaryRes.data);
      setExitInsights(exitRes.data);
      setStayInterviews(stayRes.data);
    } finally { setLoading(false); }
  };

  const calcRisk = async (empId) => {
    await api.calculateRisk(empId);
    load();
  };

  const scheduleStay = async (e) => {
    e.preventDefault();
    await api.createStayInterview(scheduleForm);
    setShowSchedule(false);
    setScheduleForm({ employee_id: '', employee_name: '', scheduled_date: '', trigger_reason: '' });
    load();
  };

  const saveConduct = async (e) => {
    e.preventDefault();
    await api.updateStayInterview(showConduct.id, { ...conductForm, status: 'Completed', completed_at: new Date().toISOString() });
    setShowConduct(null);
    setConductForm({});
    load();
  };

  const RISK_COLORS = { Low: '#22C55E', Elevated: '#F59E0B', High: '#F97316', Critical: '#EF4444', Unknown: '#9CA3AF' };

  const KPIPill = ({ k, v, color = '#191919' }) => (
    <div style={{ padding: '8px 14px', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252' }}>{k}</div>
      <div style={{ fontSize: '20px', fontWeight: 900, color }}>{v}</div>
    </div>
  );

  return (
    <div data-testid="retention-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Retention & Flight Risk</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: 0, marginTop: '4px' }}>Proactive retention intelligence</p>
      </div>

      {/* Voluntary Attrition KPI banner (correction §4) */}
      {attrition && (
        <div data-testid="attrition-card" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#525252' }}>Voluntary Attrition · 12-mo rolling</div>
            <div style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.04em', color: attrition.status === 'Healthy' ? '#22C55E' : attrition.status === 'Concerning' ? '#F97316' : '#FF353F' }}>
              {attrition.pct}%
            </div>
            <div style={{ fontSize: '11px', color: '#525252' }}>Target ≤ {attrition.target_pct}% · <strong>{attrition.status}</strong></div>
          </div>
          <div style={{ display: 'flex', gap: '14px', flex: 1, justifyContent: 'flex-end' }}>
            <KPIPill k="Voluntary exits" v={attrition.voluntary_count_12mo} />
            <KPIPill k="Regrettable" v={attrition.regrettable} color="#FF353F" />
            <KPIPill k="Non-regrettable" v={attrition.non_regrettable} color="#525252" />
            <KPIPill k="Probation excl." v={attrition.probation_exits_excluded} color="#9CA3AF" />
          </div>
        </div>
      )}

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
        {[{ k: 'flight-risk', l: 'Flight Risk Tracker' }, { k: 'stay-interviews', l: `Stay Interviews (${stayInterviews.length})` }, { k: 'exit-insights', l: 'Exit Insights' }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {t.l}
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
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button onClick={() => calcRisk(emp.id)} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>Calc Risk</button>
                        {['Elevated', 'High', 'Critical'].includes(emp.flight_risk_level) && (
                          <button data-testid={`schedule-stay-${emp.id}`} onClick={() => { setScheduleForm({ employee_id: emp.id, employee_name: emp.full_name, scheduled_date: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 16), trigger_reason: `${emp.flight_risk_level} flight risk` }); setShowSchedule(true); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #8B5CF6', color: '#8B5CF6', backgroundColor: 'transparent', cursor: 'pointer', fontFamily: 'Arial', fontWeight: 700 }}>+ Stay Interview</button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {risks.length === 0 && <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No active employees</td></tr>}
            </tbody>
          </table>
        </div>
      ) : tab === 'stay-interviews' ? (
        <div>
          <div style={{ backgroundColor: '#F5F3FF', border: '1px solid #C4B5FD', padding: '14px 18px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: '12px', color: '#5B21B6' }}>Stay interviews are conducted with at-risk employees to surface concerns before they resign. Completed conversations feed into retention strategy.</div>
            <button data-testid="new-stay-interview-btn" onClick={() => setShowSchedule(true)} style={{ padding: '8px 16px', backgroundColor: '#8B5CF6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>+ Schedule</button>
          </div>
          {stayInterviews.length === 0 ? (
            <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No stay interviews scheduled</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '12px' }}>
              {stayInterviews.map(s => (
                <div key={s.id} data-testid={`stay-${s.id}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div>
                      <div style={{ fontWeight: 900, fontSize: '14px', color: '#191919' }}>{s.employee_name}</div>
                      <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px' }}>Scheduled: {s.scheduled_date ? new Date(s.scheduled_date).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}</div>
                    </div>
                    <StatusBadge status={s.status} small />
                  </div>
                  {s.trigger_reason && <p style={{ fontSize: '11px', color: '#525252', margin: '8px 0', fontStyle: 'italic' }}>Trigger: {s.trigger_reason}</p>}
                  {s.what_makes_stay && (
                    <div style={{ fontSize: '11px', marginTop: '8px' }}>
                      <strong>Stays because:</strong> <span style={{ color: '#525252' }}>{(s.what_makes_stay || '').slice(0, 100)}</span>
                    </div>
                  )}
                  {s.agreed_actions && (
                    <div style={{ fontSize: '11px', marginTop: '6px' }}>
                      <strong>Actions:</strong> <span style={{ color: '#525252' }}>{(s.agreed_actions || '').slice(0, 100)}</span>
                    </div>
                  )}
                  {s.status === 'Scheduled' && (
                    <button data-testid={`conduct-stay-${s.id}`} onClick={() => { setShowConduct(s); setConductForm({}); }} style={{ marginTop: '10px', padding: '6px 12px', backgroundColor: '#8B5CF6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Arial' }}>Conduct Interview</button>
                  )}
                </div>
              ))}
            </div>
          )}
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

      {/* Schedule Stay Interview modal */}
      {showSchedule && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '480px', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900 }}>Schedule Stay Interview</h3>
              <button onClick={() => setShowSchedule(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={scheduleStay} style={{ padding: '24px' }}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Employee Name</label>
                <input data-testid="stay-employee-name" required value={scheduleForm.employee_name} onChange={e => setScheduleForm(p => ({ ...p, employee_name: e.target.value, employee_id: p.employee_id || e.target.value.toLowerCase().replace(/ /g, '_') }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Scheduled Date & Time</label>
                <input data-testid="stay-scheduled-date" type="datetime-local" required value={scheduleForm.scheduled_date} onChange={e => setScheduleForm(p => ({ ...p, scheduled_date: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>Trigger Reason</label>
                <input value={scheduleForm.trigger_reason} onChange={e => setScheduleForm(p => ({ ...p, trigger_reason: e.target.value }))} placeholder="e.g. High flight risk, tenure milestone, alignment dip" style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button type="button" onClick={() => setShowSchedule(false)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button data-testid="schedule-stay-submit" type="submit" style={{ padding: '10px 24px', backgroundColor: '#8B5CF6', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>Schedule</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Conduct Stay Interview modal */}
      {showConduct && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#fff', width: '600px', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <div>
                <h3 style={{ margin: 0, fontWeight: 900 }}>Stay Interview · {showConduct.employee_name}</h3>
                <p style={{ fontSize: '11px', color: '#525252', margin: '4px 0 0' }}>Capture the conversation. Follow Form 22 prompts.</p>
              </div>
              <button onClick={() => setShowConduct(null)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={saveConduct} style={{ padding: '24px' }}>
              {[
                { k: 'what_makes_stay', l: 'What makes you stay at Solvit?', type: 'textarea' },
                { k: 'what_might_leave', l: 'What might cause you to leave?', type: 'textarea' },
                { k: 'energising', l: 'Most energising part of your role', type: 'textarea' },
                { k: 'frustrating', l: 'Most frustrating part of your role', type: 'textarea' },
                { k: 'career_path_clear', l: 'Is your career path clear?', type: 'select', options: ['Very clear', 'Somewhat', 'Not at all'] },
                { k: 'manager_support_rating', l: 'Manager support (1-5)', type: 'number', min: 1, max: 5 },
                { k: 'agreed_actions', l: 'Agreed actions', type: 'textarea', required: true },
                { k: 'follow_up_date', l: 'Follow-up date', type: 'date', required: true },
              ].map(f => (
                <div key={f.k} style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '4px' }}>{f.l}{f.required && <span style={{ color: '#FF353F' }}> *</span>}</label>
                  {f.type === 'textarea' ? (
                    <textarea required={f.required} rows={2} value={conductForm[f.k] || ''} onChange={e => setConductForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }} />
                  ) : f.type === 'select' ? (
                    <select value={conductForm[f.k] || ''} onChange={e => setConductForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px' }}>
                      <option value="">Select...</option>
                      {f.options.map(o => <option key={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type={f.type} required={f.required} min={f.min} max={f.max} value={conductForm[f.k] || ''} onChange={e => setConductForm(p => ({ ...p, [f.k]: f.type === 'number' ? parseInt(e.target.value) || '' : e.target.value }))} style={{ width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' }} />
                  )}
                </div>
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                <button type="button" onClick={() => setShowConduct(null)} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
                <button data-testid="conduct-stay-submit" type="submit" style={{ padding: '10px 24px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>Save & Complete</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
