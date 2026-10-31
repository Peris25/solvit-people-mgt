import LeaveHistory from '../components/LeaveHistory';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import StatusBadge from '../components/StatusBadge';
import EmployeePicker from '../components/EmployeePicker';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useSearchParams } from 'react-router-dom';
import { relatedRecordRows } from '../utils/relatedRecordFilter';
import { useNotifications } from '../context/NotificationContext';
import { Calendar as CalendarIcon, ClipboardList, Users as UsersIcon, RotateCcw, Plus } from 'lucide-react';

const LEAVE_TYPE_LABELS = {
  Annual: 'Annual leave',
  Sick: 'Sick leave',
  Maternity: 'Maternity leave',
  Paternity: 'Paternity leave',
  Compassionate: 'Compassionate leave',
  Unpaid: 'Unpaid leave',
};

const LEAVE_TYPE_COLOR = {
  Annual: '#FF353F', Sick: '#F97316', Maternity: '#8B5CF6',
  Paternity: '#3B82F6', Compassionate: '#525252', Unpaid: '#9CA3AF',
};

const fmtPeriod = (s, e) => {
  try {
    const a = new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    const b = new Date(e).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    return `${a} → ${b}`;
  } catch { return `${s} → ${e}`; }
};
const freshForm = () => ({ leave_type: 'Annual', start_date: '', end_date: '', handover_contact: '', handover_contact_id: '', notes: '', supporting_document_id: '', expected_delivery_date: '', birth_date: '', family_relationship: '', emergency_sick: false, early_maternity_advice: false, request_token: globalThis.crypto?.randomUUID?.() || `leave-${Date.now()}-${Math.random()}` });
const message = error => {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail?.message || error?.message || 'Leave information is unavailable. Please retry.';
};

export default function Leave() {
  const { user } = useAuth();
  const notificationState = useNotifications();
  const accountKey = `${user?.id}:${user?.role}`;
  const activeAccount = useRef(accountKey); activeAccount.current = accountKey;
  const loadSequence = useRef(0);
  const [loadedFor, setLoadedFor] = useState(null);
  const [historyAvailable, setHistoryAvailable] = useState(false);
  const [error, setError] = useState('');
  const [quote, setQuote] = useState(null);
  const [quoteError, setQuoteError] = useState('');
  const [document, setDocument] = useState(null);
  const [editing, setEditing] = useState(null);
  const [review, setReview] = useState(null);
  const [checks, setChecks] = useState({ handover_reviewed: false, policy_review_confirmed: false, document_verified: false, reason: '' });
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedRequest = searchParams.get('request');
  const requestedView = searchParams.get('view');
  // Canonical employee.id resolved from /api/employees/me. user.id refers to
  // the users-collection id which can differ from employees.id (e.g. Finance,
  // HR Admin), so always prefer the resolved id when available.
  const [myEmpId, setMyEmpId] = useState(user?.employee_id || '');
  const isLM = user?.role === 'line_manager';
  const isHR = ['hr_admin', 'hr_manager'].includes(user?.role);
  const canDecide = isLM || isHR || ['finance', 'executive', 'board'].includes(user?.role);

  const [tab, setTab] = useState('my');
  useEffect(() => {
    if (linkedRequest) setTab(requestedView === 'team' && canDecide ? 'team' : 'my');
  }, [linkedRequest, requestedView, canDecide]);
  const [requests, setRequests] = useState([]);
  const [balances, setBalances] = useState(null);
  const [rollover, setRollover] = useState(null);
  const [types, setTypes] = useState({});
  const [calendar, setCalendar] = useState(null);
  const [calYear, setCalYear] = useState(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  // Auto-resolved line manager (read-only on the Apply form per UAT Fix).
  const [myLM, setMyLM] = useState({ id: '', name: '' });
  const [form, setForm] = useState(freshForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const generation = ++loadSequence.current;
    const valid = () => activeAccount.current === accountKey && generation === loadSequence.current;
    setLoading(true); setError(''); setHistoryAvailable(false); setRequests([]); setBalances(null); setRollover(null);
    try {
      const [r, t, me] = await Promise.allSettled([api.getLeaveRequests(), api.getLeaveTypes(), api.getMyEmployee()]);
      if (!valid()) return;
      if (r.status !== 'fulfilled' || !Array.isArray(r.value.data) || t.status !== 'fulfilled' || !t.value.data) throw new Error('Leave information could not be loaded. Please retry.');
      setRequests(r.value.data); setTypes(t.value.data); setHistoryAvailable(true);
      const employee = me.status === 'fulfilled' ? me.value.data : null;
      const id = employee?.id || user?.employee_id || '';
      setMyEmpId(id); setMyLM({ id: employee?.line_manager_id || '', name: employee?.line_manager_name || '' });
      if (id) {
        const [b, ro] = await Promise.allSettled([api.getLeaveBalances(id), api.getLeaveRollover(id)]);
        if (!valid()) return;
        setBalances(b.status === 'fulfilled' ? b.value.data : null);
        setRollover(ro.status === 'fulfilled' ? ro.value.data : null);
      }
    } catch (err) { if (valid()) setError(message(err)); }
    finally { if (valid()) { setLoading(false); setLoadedFor(accountKey); } }
  }, [accountKey, user?.employee_id]);
  useEffect(() => { setShowForm(false); setReview(null); setCalendar(null); setForm(freshForm()); load(); }, [load]);
  const loadCalendar = useCallback(async () => {
    setCalendar(null);
    try { const c = await api.getLeaveCalendar(calYear, calMonth); if (activeAccount.current === accountKey) setCalendar(c.data); }
    catch { if (activeAccount.current === accountKey) setCalendar(null); }
  }, [calYear, calMonth, accountKey]);
  useEffect(() => { if (tab === 'calendar') loadCalendar(); }, [tab, loadCalendar]);
  const previewBody = JSON.stringify(form);
  useEffect(() => {
    let cancelled = false;
    setQuote(null); setQuoteError('');
    if (!showForm || !myEmpId || !JSON.parse(previewBody).start_date || !JSON.parse(previewBody).end_date) return undefined;
    const timer = setTimeout(() => {
      api.previewLeave({ ...JSON.parse(previewBody), employee_id: myEmpId }, { request_id: editing?.id })
        .then(response => { if (!response.data) throw new Error('Leave calculation unavailable'); if (!cancelled) setQuote(response.data); })
        .catch(err => { if (!cancelled) setQuoteError(message(err)); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [showForm, previewBody, myEmpId, editing?.id]);
  const openForm = row => {
    setEditing(row || null); setDocument(null); setError('');
    setForm(row ? { ...freshForm(), ...row } : freshForm()); setShowForm(true);
  };
  const submit = async event => {
    event.preventDefault(); setError('');
    if (!myEmpId || !myLM.id) { setError('HR must confirm your employee record and line manager.'); return; }
    setSaving(true);
    try {
      let documentId = form.supporting_document_id;
      if (document) {
        const data = new FormData(); data.append('file', document);
        data.append('document_type', form.leave_type === 'Maternity' ? 'maternity_confirmation' : form.leave_type === 'Paternity' ? 'birth_notification' : 'medical_certificate');
        const uploaded = await api.uploadLeaveEvidence(data);
        if (!uploaded.data?.id) throw new Error('Supporting document could not be saved');
        documentId = uploaded.data.id; setForm(previous => ({ ...previous, supporting_document_id: documentId }));
      }
      const payload = { ...form, employee_id: myEmpId, line_manager_id: myLM.id || undefined, supporting_document_id: documentId || undefined };
      const fields = ['notes', 'handover_contact_id', 'supporting_document_id', 'expected_delivery_date', 'birth_date', 'family_relationship', 'emergency_sick', 'early_maternity_advice'];
      const response = editing ? await api.supplementLeave(editing.id, Object.fromEntries(fields.filter(field => payload[field] !== undefined).map(field => [field, payload[field]]))) : await api.createLeaveRequest(payload);
      if (!response.data?.id) throw new Error('The leave request could not be confirmed. Refresh history before retrying.');
      setShowForm(false); setForm(freshForm()); load(); notificationState?.refresh();
    } catch (err) { setError(message(err)); } finally { setSaving(false); }
  };
  const decide = async decision => {
    setSaving(true); setError('');
    try {
      const response = await api.leaveDecision(review.id, { ...checks, decision, stage: review.approval_stage || (isHR ? 'hr' : undefined) });
      if (!response.data?.id) throw new Error('The decision could not be confirmed. Refresh before retrying.');
      setReview(null); load(); notificationState?.refresh();
    } catch (err) { setError(message(err)); } finally { setSaving(false); }
  };
  const withdraw = async row => {
    setSaving(true); setError('');
    try {
      const response = await api.cancelLeave(row.id, 'Employee withdrew a future pending request');
      if (!response.data?.id) throw new Error('Withdrawal could not be confirmed. Refresh before retrying.');
      load(); notificationState?.refresh();
    } catch (err) { setError(message(err)); } finally { setSaving(false); }
  };
  const openReview = row => { setReview(row); setError(''); setChecks({ handover_reviewed: false, policy_review_confirmed: false, document_verified: false, reason: '' }); };
  const downloadEvidence = async id => {
    try {
      const response = await api.downloadLeaveEvidence(id);
      if (!response.data || !(response.data instanceof Blob)) throw new Error('Document unavailable');
      const url = URL.createObjectURL(response.data); const link = window.document.createElement('a'); link.href = url; link.download = 'leave-evidence'; link.click(); URL.revokeObjectURL(url);
    } catch (_) { setError('The supporting document could not be downloaded.'); }
  };
  const calcDays = () => quote?.working_days ?? 'Awaiting server calculation';

  // Filtered request lists
  const ownAliases = [myEmpId, user?.employee_id, ...(user?.employee_reference_ids || [])].filter(Boolean).map(String);
  const selectedRequests = relatedRecordRows(requests, linkedRequest);
  const myRequests = selectedRequests.filter(r => ownAliases.includes(String(r.employee_id)));
  const teamRequests = selectedRequests.filter(r => !ownAliases.includes(String(r.employee_id)));

  const annualBal = balances?.Annual;
  const accruedDisplay = balances && Object.prototype.hasOwnProperty.call(balances, 'annual_available_to_request') ? balances.annual_available_to_request ?? 'Needs HR review' : annualBal?.remaining ?? 'Unavailable';
  const hasTeam = (canDecide || requests.some(row => row.employee_id !== myEmpId)) && loadedFor === accountKey;

  const TabButton = ({ id, label, Icon }) => (
    <button
      data-testid={`leave-tab-${id}`}
      onClick={() => setTab(id)}
      style={{
        padding: '10px 18px', backgroundColor: 'transparent', border: 'none',
        borderBottom: tab === id ? '2px solid #FF353F' : '2px solid transparent',
        marginBottom: '-2px', cursor: 'pointer', fontSize: '12px',
        fontWeight: tab === id ? 700 : 500, color: tab === id ? '#FF353F' : '#525252',
        fontFamily: 'Barlow, sans-serif', textTransform: 'uppercase', letterSpacing: '0.1em',
        display: 'inline-flex', alignItems: 'center', gap: '8px'
      }}>
      <Icon size={14} />{label}
    </button>
  );

  return (
    <div data-testid="leave-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0, fontFamily: 'Barlow' }}>Leave Management</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Handbook v2 · Contract terms take precedence · Manager and HR approval</p>
        </div>
        <button data-testid="apply-leave-btn" onClick={() => openForm()} disabled={!myEmpId || loadedFor !== accountKey} style={{ padding: '10px 18px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          <Plus size={14} /> Apply for Leave
        </button>
      </div>

      {/* Rollover banner */}
      {rollover && loadedFor === accountKey && rollover.carried_forward > 0 && (
        <div data-testid="rollover-banner" style={{ padding: '12px 16px', backgroundColor: rollover.deadline_passed ? '#FEE2E2' : '#FEF3C7', borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: rollover.deadline_passed ? '#FF353F' : '#F59E0B', marginBottom: '20px', fontSize: '12px', color: '#191919' }}>
          <strong style={{ color: '#FF353F' }}>Rollover Leave:</strong> {rollover.remaining} of {rollover.carried_forward} carried-forward days remaining. {rollover.banner}
        </div>
      )}

      {/* Balances */}
      {balances && loadedFor === accountKey && (
        <div data-testid="leave-balances" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px', marginBottom: '24px' }}>
          {/* Accrued balance card */}
          {annualBal && (
            <div data-testid="balance-accrued" style={{ backgroundColor: '#191919', color: '#fff', padding: '14px 18px' }}>
              <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'rgba(255,255,255,0.6)', marginBottom: '6px' }}>Available to request</div>
              <div style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', fontFamily: 'Barlow' }}>{accruedDisplay}</div>
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>Recorded balance: {annualBal.remaining ?? 'Needs HR review'}. Pending commitments are shown separately.</div>
            </div>
          )}
          {Object.entries(balances).filter(([, value]) => value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'remaining')).map(([type, b]) => (
            <div key={type} data-testid={`balance-${type}`} style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px' }}>{type}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '26px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', fontFamily: 'Barlow' }}>{b.remaining ?? 'Unavailable'}</span>
                <span style={{ fontSize: '11px', color: '#525252' }}>{b.entitlement != null ? `of ${b.entitlement}` : b.balance_label || 'As recorded'}</span>
              </div>
              {typeof b.used === 'number' && typeof b.entitlement === 'number' && <div style={{ height: '4px', backgroundColor: '#F5F5F5', marginTop: '8px' }}>
                <div style={{ width: `${Math.min(100, (b.used / Math.max(1, b.entitlement)) * 100)}%`, height: '100%', backgroundColor: LEAVE_TYPE_COLOR[type] || '#FF353F' }} />
              </div>}
            </div>
          ))}
        </div>
      )}
      {!balances && !loading && loadedFor === accountKey && <p>Leave balances are unavailable. HR must check the recorded balance.</p>}

      {/* Tabs */}
      {linkedRequest && <div style={{ padding: '12px', marginBottom: '12px', background: '#fff' }}>
        {!loading && selectedRequests.length === 0 ? 'The requested leave record is unavailable or not authorized.' : 'Viewing a linked leave request.'}
        <button onClick={() => setSearchParams({})} style={{ marginLeft: '12px', minHeight: '44px' }}>Show all requests</button>
      </div>}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        <TabButton id="my" label="My Applications" Icon={ClipboardList} />
        {hasTeam && <TabButton id="team" label="Team Leave" Icon={UsersIcon} />}
        {isHR && <TabButton id="history" label="Historical records" Icon={ClipboardList} />}
        <TabButton id="calendar" label="Calendar" Icon={CalendarIcon} />
        <TabButton id="rollover" label="Rollover" Icon={RotateCcw} />
      </div>

      {error && <div role="alert" style={{ padding: '16px', background: '#FEE2E2', marginBottom: '16px' }}>{error}</div>}
      {!historyAvailable && !loading && loadedFor === accountKey ? <p>Leave history is unavailable. <button style={btnGhost} onClick={load}>Retry</button></p> : loading || loadedFor !== accountKey ? <div style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
        <>
          {tab === 'my' && <RequestsTable rows={myRequests} withdraw={withdraw} edit={openForm} review={openReview} saving={saving} testId="my-applications" />}
          {tab === 'team' && hasTeam && <RequestsTable rows={teamRequests} withdraw={withdraw} review={openReview} saving={saving} testId="team-leave" />}
          {tab === 'history' && isHR && <LeaveHistory key={accountKey} rows={requests.filter(row => row.historical_import)} onSaved={load} />}
          {tab === 'calendar' && <LeaveCalendar calendar={calendar} year={calYear} month={calMonth} setYear={setCalYear} setMonth={setCalMonth} />}
          {tab === 'rollover' && <RolloverPanel rollover={rollover} />}
        </>
      )}

      {showForm && loadedFor === accountKey && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ backgroundColor: '#fff', width: '560px', maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.15)' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0, fontWeight: 900, fontFamily: 'Barlow' }}>Apply for Leave</h3>
              <button onClick={() => setShowForm(false)} style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={submit} style={{ padding: '24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: '14px' }}>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Leave Type</label>
                  <select required aria-label="Leave type" disabled={!!editing} value={form.leave_type} onChange={e => setForm(p => ({ ...p, leave_type: e.target.value }))} style={inp}>
                    {Object.keys(types).map(t => <option key={t} value={t}>{LEAVE_TYPE_LABELS[t] || `${t} leave`}</option>)}
                  </select>
                  {types[form.leave_type]?.description && (
                    <div style={{ fontSize: '10px', color: '#525252', marginTop: '4px', fontStyle: 'italic' }}>{types[form.leave_type].description}</div>
                  )}
                </div>
                <div>
                  <label style={lbl}>Start Date</label>
                  <input type="date" required disabled={!!editing} aria-label="Leave start date" value={form.start_date} onChange={e => setForm(p => ({ ...p, start_date: e.target.value }))} style={inp} />
                </div>
                <div>
                  <label style={lbl}>End Date</label>
                  <input type="date" required disabled={!!editing} aria-label="Leave end date" value={form.end_date} onChange={e => setForm(p => ({ ...p, end_date: e.target.value }))} style={inp} />
                </div>
                <div style={{ gridColumn: '1 / -1', backgroundColor: '#F5F5F5', padding: '8px 12px', fontSize: '12px' }}>
                  Working Days: <strong>{calcDays()}</strong>
                  {quoteError && <p role="alert">{quoteError}</p>}
                  {quote && <p>{quote.notice_days_required ? `${quote.notice_days_required} days advance notice. ` : ''}{quote.warning}</p>}
                  {annualBal && form.leave_type === 'Annual' && (
                    <span style={{ marginLeft: '12px', color: calcDays() > accruedDisplay ? '#FF353F' : '#525252' }}>
                      · Accrued available: {accruedDisplay} days
                    </span>
                  )}
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Line Manager (auto-assigned — approval routes here)</label>
                  {myLM.id ? (
                    <div data-testid="leave-lm-readonly" style={{ ...inp, backgroundColor: '#F5F5F5', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'not-allowed', color: '#191919', fontWeight: 600 }}>
                      <span>{myLM.name || 'Line Manager assigned'}</span>
                      <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow', fontWeight: 700 }}>Read-only</span>
                    </div>
                  ) : (
                    <div data-testid="leave-lm-missing" style={{ ...inp, backgroundColor: '#FEF2F2', color: '#991B1B', border: '1px solid #FF353F' }}>
                      No Line Manager on file. Contact HR — leave cannot be submitted without an approver.
                    </div>
                  )}
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Handover Contact</label>
                  <EmployeePicker
                    testId="leave-handover-picker"
                    value={form.handover_contact_id}
                    excludeId={myEmpId}
                    placeholder="Select colleague covering for you..."
                    onChange={(emp) => setForm(p => ({ ...p, handover_contact: emp.full_name, handover_contact_id: emp.id }))}
                  />
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Handover Notes</label>
                  <textarea rows={3} aria-label="Written handover notes" maxLength={8000} value={form.notes || ''} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} style={{ ...inp, resize: 'vertical' }} />
                </div>
                {form.leave_type === 'Sick' && <label style={{ gridColumn: '1 / -1' }}><input type="checkbox" checked={form.emergency_sick} onChange={e => setForm(p => ({ ...p, emergency_sick: e.target.checked }))} /> Emergency sick leave (no advance handover for an immediate absence)</label>}
                {form.leave_type === 'Maternity' && <>
                  <label>Expected delivery date<input aria-label="Expected delivery date" type="date" required style={inp} value={form.expected_delivery_date || ''} onChange={e => setForm(p => ({ ...p, expected_delivery_date: e.target.value }))} /></label>
                  <label><input type="checkbox" checked={form.early_maternity_advice} onChange={e => setForm(p => ({ ...p, early_maternity_advice: e.target.checked }))} /> Medical advice supports an earlier start (HR verification required)</label>
                </>}
                {form.leave_type === 'Paternity' && <label>Date of birth<input type="date" aria-label="Child birth date" required style={inp} value={form.birth_date || ''} onChange={e => setForm(p => ({ ...p, birth_date: e.target.value }))} /></label>}
                {form.leave_type === 'Compassionate' && <label>Immediate-family relationship<select required aria-label="Family relationship" style={inp} value={form.family_relationship || ''} onChange={e => setForm(p => ({ ...p, family_relationship: e.target.value }))}><option value="">Select</option>{['spouse', 'child', 'parent', 'sibling'].map(value => <option key={value}>{value}</option>)}</select></label>}
                {['Sick', 'Maternity', 'Paternity'].includes(form.leave_type) && <div style={{ gridColumn: '1 / -1' }}>
                  <label style={lbl}>Supporting document (PDF, PNG or JPEG, up to 5 MB)</label>
                  <input aria-label="Leave supporting document" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={e => setDocument(e.target.files?.[0] || null)} />
                  <p>Restricted to you and HR. {quote?.supporting_document_required ? 'Required for this request.' : 'Sick certificates are required after 3 consecutive days or for half-pay absences.'}</p>
                  {form.supporting_document_id && <span>Supporting document already recorded.</span>}
                </div>}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
                <button type="button" onClick={() => setShowForm(false)} style={btnGhost}>Cancel</button>
                <button data-testid="leave-submit-btn" type="submit" disabled={saving} style={btnRed}>{saving ? 'Saving...' : editing ? 'Save supporting information' : 'Submit Request'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
      {review && loadedFor === accountKey && <div role="dialog" aria-label="Review leave request" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 100 }}>
        <div style={{ background: '#fff', width: '600px', maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto', padding: '24px' }}>
          <h2>Review leave request</h2><p>{review.employee_name} · {review.leave_type} · {fmtPeriod(review.start_date, review.end_date)} · {review.working_days} working days</p>
          <p>Status: {review.status}. Manager recommendation does not finalize leave; HR must approve next.</p>
          {review.notes && <p style={{ whiteSpace: 'pre-wrap' }}>Handover: {review.notes}</p>}
          {review.supporting_document_id && <button style={btnGhost} onClick={() => downloadEvidence(review.supporting_document_id)}>Download restricted supporting document</button>}
          <label style={{ display: 'block', margin: '12px 0' }}><input type="checkbox" checked={checks.handover_reviewed} onChange={e => setChecks(p => ({ ...p, handover_reviewed: e.target.checked }))} /> Written handover reviewed and signed off (planned leave)</label>
          {review.approval_stage === 'hr' && <>
            <label style={{ display: 'block', margin: '12px 0' }}><input type="checkbox" checked={checks.policy_review_confirmed} onChange={e => setChecks(p => ({ ...p, policy_review_confirmed: e.target.checked }))} /> Contract eligibility, recorded balance and gazetted holiday calendar verified</label>
            <label style={{ display: 'block', margin: '12px 0' }}><input type="checkbox" checked={checks.document_verified} onChange={e => setChecks(p => ({ ...p, document_verified: e.target.checked }))} /> Supporting document verified where required</label>
          </>}
          <label>Decision reason<textarea aria-label="Leave decision reason" maxLength={4000} style={inp} value={checks.reason} onChange={e => setChecks(p => ({ ...p, reason: e.target.value }))} /></label>
          <h3>Approval history</h3>{(review.approval_history || []).map((entry, index) => <p key={index}>{entry.stage} · {entry.decision || 'Recorded'} · {entry.actor_role} · {entry.at}</p>)}
          {error && <p role="alert">{error}</p>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '16px' }}>
            <button style={btnGhost} onClick={() => setReview(null)}>Close</button>
            {review.approval_stage && <button disabled={saving} style={btnRed} onClick={() => decide('Approve')}>{review.approval_stage === 'hr' ? 'HR final approval' : 'Recommend to HR'}</button>}
            {review.can_reject && <button disabled={saving} style={btnGhost} onClick={() => decide('Reject')}>Reject</button>}
            {review.approval_stage && <button disabled={saving} style={btnGhost} onClick={() => decide('Discussion')}>Request discussion</button>}
          </div>
        </div>
      </div>}
    </div>
  );
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', fontFamily: 'Nunito Sans, sans-serif' };
const btnRed = { padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' };
const btnGhost = { padding: '10px 20px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontFamily: 'Nunito Sans, sans-serif' };

function RequestsTable({ rows, withdraw, review, edit, saving, testId }) {
  return (
    <div data-testid={testId} style={{ overflowX: 'auto', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr style={{ backgroundColor: '#F5F5F5' }}>
            {['Employee', 'Type', 'Period', 'Days', 'Handover', 'Status', 'Action'].map(h => (
              <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Barlow' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} data-testid={`leave-${r.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
              <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '11px' }}>{r.employee_name || 'Employee name unavailable'}</td>
              <td style={{ padding: '10px 14px', fontWeight: 700 }}>{LEAVE_TYPE_LABELS[r.leave_type] || r.leave_type}</td>
              <td style={{ padding: '10px 14px', color: '#525252' }}>{fmtPeriod(r.start_date, r.end_date)}</td>
              <td style={{ padding: '10px 14px', fontWeight: 700 }}>{r.working_days}</td>
              <td style={{ padding: '10px 14px', color: '#525252' }}>{r.handover_contact || '—'}</td>
              <td style={{ padding: '10px 14px' }}><StatusBadge status={(r.status || '').replace('Pending_', '').replace('_', ' ')} small /></td>
              <td style={{ padding: '10px 14px' }}>
                {(r.approval_stage || r.can_reject) && <button disabled={saving} onClick={() => review(r)} style={btnGhost}>Review</button>}
                {r.can_cancel && <button disabled={saving} onClick={() => withdraw(r)} style={btnGhost}>Withdraw</button>}
                {edit && !r.historical_import && ['Pending_Manager', 'Pending_HR', 'Discussion_Requested', 'Pending'].includes(r.status) && <button disabled={saving} onClick={() => edit(r)} style={btnGhost}>Supporting information</button>}

              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No requests</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function LeaveCalendar({ calendar, year, month, setYear, setMonth }) {
  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDayWeek = new Date(year, month - 1, 1).getDay(); // 0=Sun
  // Map: day -> events
  const dayMap = {};
  (calendar?.events || []).forEach(ev => {
    const start = new Date(ev.start_date);
    const end = new Date(ev.end_date);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      if (d.getFullYear() === year && d.getMonth() + 1 === month) {
        const day = d.getDate();
        if (!dayMap[day]) dayMap[day] = [];
        dayMap[day].push(ev);
      }
    }
  });

  const monthName = new Date(year, month - 1, 1).toLocaleString('en-GB', { month: 'long' });

  const prev = () => { if (month === 1) { setYear(year - 1); setMonth(12); } else setMonth(month - 1); };
  const next = () => { if (month === 12) { setYear(year + 1); setMonth(1); } else setMonth(month + 1); };

  return (
    <div data-testid="leave-calendar" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <button data-testid="cal-prev" onClick={prev} style={navBtn}>‹ Prev</button>
        <h3 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>{monthName} {year}</h3>
        <button data-testid="cal-next" onClick={next} style={navBtn}>Next ›</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '4px', fontSize: '11px' }}>
        {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d => (
          <div key={d} style={{ padding: '6px', textAlign: 'center', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{d}</div>
        ))}
        {Array.from({ length: firstDayWeek }).map((_, i) => <div key={`empty-${i}`} />)}
        {Array.from({ length: daysInMonth }).map((_, i) => {
          const day = i + 1;
          const events = dayMap[day] || [];
          return (
            <div key={day} data-testid={`cal-day-${day}`} style={{ minHeight: '70px', border: '1px solid rgba(25,25,25,0.06)', padding: '4px', backgroundColor: events.length ? '#FFF5F5' : '#fff' }}>
              <div style={{ fontWeight: 700, fontSize: '11px', color: '#191919' }}>{day}</div>
              {events.slice(0, 2).map(ev => (
                <div key={ev.id} title={`${ev.employee_name} · ${ev.leave_type}`} style={{ marginTop: '2px', padding: '1px 4px', fontSize: '9px', backgroundColor: LEAVE_TYPE_COLOR[ev.leave_type] || '#FF353F', color: '#fff', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                  {ev.employee_name?.split(' ')[0] || '·'}
                </div>
              ))}
              {events.length > 2 && <div style={{ fontSize: '9px', color: '#525252', marginTop: '2px' }}>+{events.length - 2} more</div>}
            </div>
          );
        })}
      </div>
      {(!calendar || (calendar.events || []).length === 0) && (
        <div style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF', fontSize: '12px', marginTop: '12px' }}>No approved leave in this month.</div>
      )}
    </div>
  );
}

const navBtn = { padding: '6px 12px', border: '1px solid rgba(25,25,25,0.15)', backgroundColor: '#fff', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };

function RolloverPanel({ rollover }) {
  if (!rollover) return <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No rollover data</div>;
  const cf = rollover.carried_forward || 0;
  return (
    <div data-testid="rollover-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '24px' }}>
      <h3 style={{ margin: '0 0 16px', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>Rollover Leave · {rollover.year || new Date().getFullYear()}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '20px' }}>
        <div style={statBox}>
          <div style={statLabel}>Carried Forward</div>
          <div style={statValue}>{cf}</div>
        </div>
        <div style={statBox}>
          <div style={statLabel}>Used</div>
          <div style={statValue}>{rollover.used || 0}</div>
        </div>
        <div style={statBox}>
          <div style={statLabel}>Remaining</div>
          <div style={{ ...statValue, color: rollover.deadline_passed ? '#FF353F' : '#191919' }}>{rollover.remaining || 0}</div>
        </div>
      </div>
      {rollover.banner && (
        <div style={{ padding: '12px 16px', backgroundColor: rollover.deadline_passed ? '#FEE2E2' : '#FEF3C7', borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: rollover.deadline_passed ? '#FF353F' : '#F59E0B', fontSize: '12px', color: '#191919' }}>
          {rollover.banner} {rollover.deadline_passed && <strong style={{ color: '#FF353F' }}>· Deadline passed — remaining days forfeited.</strong>}
        </div>
      )}
      {cf === 0 && <div style={{ padding: '20px', textAlign: 'center', color: '#525252', fontSize: '12px' }}>No carry-forward days from previous year.</div>}
    </div>
  );
}

const statBox = { padding: '16px', backgroundColor: '#F5F5F5', borderLeftWidth: '3px', borderLeftStyle: 'solid', borderLeftColor: '#FF353F' };
const statLabel = { fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', fontFamily: 'Barlow' };
const statValue = { fontSize: '32px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.04em', color: '#191919', marginTop: '4px' };
