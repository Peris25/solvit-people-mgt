/**
 * Budget Governance (M12) — full implementation per FRD §10 spec.
 * Sections: GP Actual (Finance only) → Envelope/Headroom → Tier Switch (Form 28)
 *           → Department breakdown → HR Headroom Allocations
 */
import React, { useState, useEffect } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

const fmtKES = (n) => (n == null ? '—' : `KES ${Number(n).toLocaleString('en-KE')}`);
const COLORS = ['#FF353F', '#3B82F6', '#22C55E', '#F97316', '#8B5CF6'];

const LINKED_MODULES = [
  { v: 'M05', l: 'M05 Performance' },
  { v: 'M06', l: 'M06 Compensation' },
  { v: 'M08', l: 'M08 Recognition' },
  { v: 'M10', l: 'M10 L&D' },
  { v: 'M11', l: 'M11 Retention' },
  { v: 'M14', l: 'M14 Solver Performance' },
  { v: 'General HR', l: 'General HR' },
];

const Stat = ({ label, value, sub, color = '#fff', testId }) => (
  <div data-testid={testId} style={{ flex: 1, minWidth: '180px' }}>
    <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'rgba(255,255,255,0.5)' }}>{label}</div>
    <div style={{ fontSize: '22px', fontWeight: 900, color, letterSpacing: '-0.04em', marginTop: '4px' }}>{value}</div>
    {sub && <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.5)', marginTop: '2px' }}>{sub}</div>}
  </div>
);

export default function Budget() {
  const { user } = useAuth();
  const isFinance = user?.role === 'finance';
  const isHRAdmin = user?.role === 'hr_admin';

  const [envelope, setEnvelope] = useState(null);
  const [summary, setSummary] = useState(null);
  const [allocSummary, setAllocSummary] = useState(null);
  const [allocations, setAllocations] = useState([]);
  const [loading, setLoading] = useState(true);

  // GP modal state
  const [showGP, setShowGP] = useState(false);
  const [gpForm, setGpForm] = useState({ actual_gp_kes: '', period: new Date().getFullYear().toString() });
  // Form 28 modal state
  const [showForm28, setShowForm28] = useState(false);
  const [form28, setForm28] = useState({ active_tier: 'Tier_1', signature: '' });
  // Allocation modal
  const [showAlloc, setShowAlloc] = useState(false);
  const [allocForm, setAllocForm] = useState({ initiative_name: '', amount_kes: '', linked_module: 'General HR', notes: '' });
  // Spend modal
  const [spendingFor, setSpendingFor] = useState(null);
  const [spendAmount, setSpendAmount] = useState('');

  const load = async () => {
    setLoading(true);
    const [e, s, as, al] = await Promise.allSettled([
      api.getPeopleEnvelope(), api.getBudgetSummary(),
      api.getAllocationSummary(), api.getAllocations(),
    ]);
    if (e.status === 'fulfilled') setEnvelope(e.value.data);
    if (s.status === 'fulfilled') setSummary(s.value.data);
    if (as.status === 'fulfilled') setAllocSummary(as.value.data);
    if (al.status === 'fulfilled') setAllocations(al.value.data || []);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submitGP = async (e) => {
    e.preventDefault();
    await api.submitGPRecord({ actual_gp_kes: Number(gpForm.actual_gp_kes), period: gpForm.period });
    setShowGP(false);
    setGpForm({ actual_gp_kes: '', period: new Date().getFullYear().toString() });
    load();
  };
  const submitForm28 = async (e) => {
    e.preventDefault();
    await api.submitForm28({ active_tier: form28.active_tier });
    setShowForm28(false);
    load();
  };
  const submitAllocation = async (e) => {
    e.preventDefault();
    await api.createAllocation({
      initiative_name: allocForm.initiative_name,
      amount_kes: Number(allocForm.amount_kes),
      linked_module: allocForm.linked_module,
      notes: allocForm.notes,
    });
    setShowAlloc(false);
    setAllocForm({ initiative_name: '', amount_kes: '', linked_module: 'General HR', notes: '' });
    load();
  };
  const approveAlloc = async (a) => { await api.updateAllocation(a.id, { status: 'Approved' }); load(); };
  const markSpent = async () => {
    await api.updateAllocation(spendingFor.id, { status: 'Spent', spent_amount_kes: Number(spendAmount) });
    setSpendingFor(null); setSpendAmount(''); load();
  };
  const removeAlloc = async (a) => {
    if (window.confirm(`Delete allocation "${a.initiative_name}"?`)) {
      await api.deleteAllocation(a.id); load();
    }
  };

  if (loading) return <div style={{ padding: '48px', textAlign: 'center' }}>Loading budget data...</div>;

  const financeReceived = envelope?.finance_input_received;
  const headroomColor = envelope?.headroom_kes == null ? '#9CA3AF' : (envelope.headroom_kes >= 0 ? '#22C55E' : '#FF353F');
  const tierActive = envelope?.form28_confirmed && envelope?.active_tier;

  return (
    <div data-testid="budget-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0 }}>Budget Governance</h1>
          <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>People Cost Envelope (50% of GP) · {envelope?.period}</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {isFinance && (
            <>
              <button data-testid="btn-submit-gp" onClick={() => setShowGP(true)} style={{ padding: '10px 18px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{financeReceived ? 'Update GP Actual' : 'Submit GP Actual'}</button>
              {financeReceived && (
                <button data-testid="btn-form28" onClick={() => setShowForm28(true)} style={{ padding: '10px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Submit Tier Confirmation (Form 28)</button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Envelope card */}
      <div data-testid="envelope-card" style={{ backgroundColor: '#191919', color: '#fff', padding: '28px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: 'rgba(255,255,255,0.5)' }}>People Cost Envelope · {envelope?.period}</span>
          <span data-testid="tier-status" style={{ fontSize: '11px', fontWeight: 700, padding: '6px 12px', backgroundColor: tierActive ? '#FF353F' : 'rgba(255,255,255,0.1)', color: '#fff', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
            {envelope?.tier_status}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
          <Stat testId="stat-gp-actual" label="GP Actual" value={financeReceived ? fmtKES(envelope.actual_gp_kes) : 'Awaiting Finance Input'} color={financeReceived ? '#fff' : 'rgba(255,255,255,0.4)'} />
          <Stat testId="stat-envelope" label="Envelope (50% of GP)" value={financeReceived ? fmtKES(envelope.people_cost_envelope_kes) : 'Awaiting Finance Input'} color={financeReceived ? '#FF353F' : 'rgba(255,255,255,0.4)'} />
          <Stat testId="stat-total-cost" label={`Total Annual People Cost (${envelope?.active_fte_headcount ?? 0} FTE)`} value={fmtKES(envelope?.total_annual_people_cost_kes)} />
          <Stat testId="stat-headroom" label="Headroom" value={financeReceived ? fmtKES(envelope.headroom_kes) : 'Awaiting Finance Input'} sub={financeReceived ? envelope.headroom_status : null} color={headroomColor} />
        </div>
      </div>

      {!financeReceived && (
        <div data-testid="awaiting-banner" style={{ backgroundColor: '#FFF7ED', border: '1px solid #F97316', padding: '12px 16px', marginBottom: '16px', fontSize: '12px', color: '#7C2D12' }}>
          <strong>Awaiting Finance Input.</strong> All envelope, headroom, and bonus / salary increase approvals remain locked until the Finance Manager submits GP Actual and signs Form 28.
        </div>
      )}

      {/* Tier thresholds reference */}
      <div data-testid="tier-thresholds" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px', marginBottom: '16px' }}>
        <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: '#525252', marginBottom: '8px' }}>Tier Thresholds (Reference)</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
          <div><strong>Tier 1</strong> · Annual Revenue ≥ KES 77,500,000 <em>and</em> PBT ≥ KES 9,500,000</div>
          <div><strong>Tier 2</strong> · Annual Revenue ≥ KES 178,300,000 <em>and</em> PBT ≥ KES 23,600,000</div>
        </div>
      </div>

      {/* Department breakdown */}
      <div data-testid="dept-breakdown" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', marginBottom: '16px' }}>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5', fontSize: '12px', fontWeight: 700 }}>Department Breakdown</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead><tr style={{ backgroundColor: '#FAFAFA' }}>
            {['Department', 'Headcount', 'Annual Salary Cost', '% of Envelope'].map(h => (
              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {(summary?.by_department || []).map((d, i) => (
              <tr key={d.department} data-testid={`dept-${d.department.replace(/[^a-z0-9]/gi, '_')}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.04)' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700, color: COLORS[i % COLORS.length] }}>{d.department}</td>
                <td style={{ padding: '10px 14px' }}>{d.headcount}</td>
                <td style={{ padding: '10px 14px', fontWeight: 700 }}>{fmtKES(d.annual_cost_kes)}</td>
                <td style={{ padding: '10px 14px', color: '#525252' }}>{d.pct_of_envelope == null ? '—' : `${d.pct_of_envelope}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* §10 HR Headroom Allocation Panel — visible once GP confirmed */}
      {financeReceived && (
        <div data-testid="headroom-allocation" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', marginBottom: '16px' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 700 }}>Headroom Allocation</span>
            {isHRAdmin && (
              <button data-testid="btn-add-allocation" onClick={() => setShowAlloc(true)} style={{ padding: '6px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>+ New Allocation</button>
            )}
          </div>
          <div style={{ padding: '16px 18px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
            <div data-testid="alloc-stat-total"><div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Confirmed Headroom</div><div style={{ fontSize: '20px', fontWeight: 900, color: '#191919' }}>{fmtKES(allocSummary?.headroom_kes)}</div></div>
            <div data-testid="alloc-stat-allocated"><div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Allocated</div><div style={{ fontSize: '20px', fontWeight: 900, color: '#F97316' }}>{fmtKES(allocSummary?.allocated_kes)}</div></div>
            <div data-testid="alloc-stat-remaining"><div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Remaining Unallocated</div><div style={{ fontSize: '20px', fontWeight: 900, color: '#22C55E' }}>{fmtKES(allocSummary?.remaining_kes)}</div></div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead><tr style={{ backgroundColor: '#FAFAFA' }}>
              {['Initiative', 'Module', 'Amount', 'Status', 'Spent', 'Variance', 'Action'].map(h => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderTop: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {allocations.length === 0 ? (
                <tr><td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF' }}>No allocations yet</td></tr>
              ) : allocations.map(a => (
                <tr key={a.id} data-testid={`alloc-${a.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.04)' }}>
                  <td style={{ padding: '8px 12px', fontWeight: 700 }}>{a.initiative_name}<div style={{ fontSize: '10px', color: '#9CA3AF' }}>{a.notes}</div></td>
                  <td style={{ padding: '8px 12px', color: '#525252' }}>{a.linked_module}</td>
                  <td style={{ padding: '8px 12px', fontWeight: 700 }}>{fmtKES(a.amount_kes)}</td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{ fontSize: '10px', padding: '2px 8px', backgroundColor: a.status === 'Spent' ? '#DBEAFE' : a.status === 'Approved' ? '#DCFCE7' : a.status === 'Pending_Finance' ? '#FEF3C7' : '#F5F5F5', color: a.status === 'Spent' ? '#1E40AF' : a.status === 'Approved' ? '#166534' : a.status === 'Pending_Finance' ? '#92400E' : '#525252', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.08em' }}>{a.status?.replace('_', ' ')}</span>
                  </td>
                  <td style={{ padding: '8px 12px', color: '#525252' }}>{a.spent_amount_kes != null ? fmtKES(a.spent_amount_kes) : '—'}</td>
                  <td style={{ padding: '8px 12px', color: a.variance_kes >= 0 ? '#22C55E' : '#FF353F' }}>{a.variance_kes != null ? fmtKES(a.variance_kes) : '—'}</td>
                  <td style={{ padding: '8px 12px' }}>
                    {isFinance && a.status === 'Pending_Finance' && (
                      <button data-testid={`approve-${a.id}`} onClick={() => approveAlloc(a)} style={{ padding: '4px 10px', fontSize: '10px', backgroundColor: '#22C55E', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 700 }}>Approve</button>
                    )}
                    {isHRAdmin && a.status === 'Approved' && (
                      <button data-testid={`spend-${a.id}`} onClick={() => { setSpendingFor(a); setSpendAmount(a.amount_kes); }} style={{ padding: '4px 10px', fontSize: '10px', border: '1px solid #3B82F6', color: '#3B82F6', background: 'transparent', cursor: 'pointer', fontWeight: 700 }}>Mark Spent</button>
                    )}
                    {isHRAdmin && a.status !== 'Spent' && (
                      <button onClick={() => removeAlloc(a)} style={{ padding: '4px 8px', fontSize: '10px', border: 'none', color: '#9CA3AF', background: 'transparent', cursor: 'pointer', marginLeft: '4px' }}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* GP Actual modal */}
      {showGP && (
        <Modal onClose={() => setShowGP(false)} title="Submit GP Actual">
          <form onSubmit={submitGP}>
            <div style={{ marginBottom: '14px' }}>
              <Label>Period (Year)</Label>
              <input required value={gpForm.period} onChange={e => setGpForm(p => ({ ...p, period: e.target.value }))} style={inputStyle} />
            </div>
            <div style={{ marginBottom: '20px' }}>
              <Label>GP Actual (KES)</Label>
              <input data-testid="gp-actual-input" required type="number" min={1} value={gpForm.actual_gp_kes} onChange={e => setGpForm(p => ({ ...p, actual_gp_kes: e.target.value }))} style={inputStyle} />
              <div style={{ fontSize: '10px', color: '#525252', marginTop: '4px' }}>Envelope auto-computes as 50% of this value.</div>
            </div>
            <ModalActions onCancel={() => setShowGP(false)} submitLabel="Submit GP Actual" testId="gp-submit" />
          </form>
        </Modal>
      )}

      {/* Form 28 modal */}
      {showForm28 && (
        <Modal onClose={() => setShowForm28(false)} title="Form 28 — Tier Confirmation">
          <form onSubmit={submitForm28}>
            <div style={{ marginBottom: '14px' }}>
              <Label>Active Tier</Label>
              <select data-testid="form28-tier" value={form28.active_tier} onChange={e => setForm28(p => ({ ...p, active_tier: e.target.value }))} style={inputStyle}>
                <option value="Tier_1">Tier 1 (Revenue ≥ 77.5M, PBT ≥ 9.5M)</option>
                <option value="Tier_2">Tier 2 (Revenue ≥ 178.3M, PBT ≥ 23.6M)</option>
              </select>
            </div>
            <div style={{ marginBottom: '20px' }}>
              <Label>Finance Manager Signature (type your full name)</Label>
              <input data-testid="form28-signature" required value={form28.signature} onChange={e => setForm28(p => ({ ...p, signature: e.target.value }))} placeholder="Sarah Njoroge" style={inputStyle} />
              <div style={{ fontSize: '10px', color: '#525252', marginTop: '4px' }}>By signing you confirm GP Actual and unlock bonus / salary increase approvals.</div>
            </div>
            <ModalActions onCancel={() => setShowForm28(false)} submitLabel="Confirm & Sign Form 28" testId="form28-submit" />
          </form>
        </Modal>
      )}

      {/* Allocation modal */}
      {showAlloc && (
        <Modal onClose={() => setShowAlloc(false)} title="New Headroom Allocation">
          <form onSubmit={submitAllocation}>
            <div style={{ marginBottom: '14px' }}><Label>Initiative Name</Label><input data-testid="alloc-name" required value={allocForm.initiative_name} onChange={e => setAllocForm(p => ({ ...p, initiative_name: e.target.value }))} placeholder="e.g. Q3 Recognition Events" style={inputStyle} /></div>
            <div style={{ marginBottom: '14px' }}><Label>Amount (KES)</Label><input data-testid="alloc-amount" required type="number" min={1} value={allocForm.amount_kes} onChange={e => setAllocForm(p => ({ ...p, amount_kes: e.target.value }))} style={inputStyle} /><div style={{ fontSize: '10px', color: '#525252', marginTop: '4px' }}>Allocations ≥ KES 50,000 require Finance approval.</div></div>
            <div style={{ marginBottom: '14px' }}><Label>Linked Module</Label>
              <select value={allocForm.linked_module} onChange={e => setAllocForm(p => ({ ...p, linked_module: e.target.value }))} style={inputStyle}>
                {LINKED_MODULES.map(m => <option key={m.v} value={m.v}>{m.l}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: '20px' }}><Label>Notes</Label><textarea rows={3} value={allocForm.notes} onChange={e => setAllocForm(p => ({ ...p, notes: e.target.value }))} style={{ ...inputStyle, resize: 'vertical' }} /></div>
            <ModalActions onCancel={() => setShowAlloc(false)} submitLabel="Save Allocation" testId="alloc-submit" />
          </form>
        </Modal>
      )}

      {/* Mark Spent modal */}
      {spendingFor && (
        <Modal onClose={() => setSpendingFor(null)} title={`Mark "${spendingFor.initiative_name}" as Spent`}>
          <div style={{ marginBottom: '14px' }}><Label>Allocated Amount</Label><div style={{ fontSize: '14px', fontWeight: 700 }}>{fmtKES(spendingFor.amount_kes)}</div></div>
          <div style={{ marginBottom: '20px' }}><Label>Actual Spent (KES)</Label><input data-testid="spend-actual" type="number" min={0} value={spendAmount} onChange={e => setSpendAmount(e.target.value)} style={inputStyle} /><div style={{ fontSize: '10px', color: '#525252', marginTop: '4px' }}>Variance returns to the unallocated headroom pool.</div></div>
          <ModalActions onCancel={() => setSpendingFor(null)} submitLabel="Mark Spent" testId="spend-submit" onSubmit={markSpent} />
        </Modal>
      )}
    </div>
  );
}

const inputStyle = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', fontFamily: 'Arial' };
const Label = ({ children }) => <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px' }}>{children}</label>;

const Modal = ({ onClose, title, children }) => (
  <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
    <div style={{ backgroundColor: '#fff', width: '520px', border: '1px solid rgba(25,25,25,0.15)' }}>
      <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0, fontWeight: 900 }}>{title}</h3>
        <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
      </div>
      <div style={{ padding: '24px' }}>{children}</div>
    </div>
  </div>
);

const ModalActions = ({ onCancel, onSubmit, submitLabel, testId }) => (
  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
    <button type="button" onClick={onCancel} style={{ padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
    <button data-testid={testId} type={onSubmit ? 'button' : 'submit'} onClick={onSubmit} style={{ padding: '10px 24px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>{submitLabel}</button>
  </div>
);
