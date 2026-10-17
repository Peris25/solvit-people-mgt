import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import EmployeePicker from '../components/EmployeePicker';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';

export default function Onboarding() {
  const { user } = useAuth();
  const hr = ['hr_admin', 'hr_manager'].includes(user?.role);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [employee, setEmployee] = useState('');
  const [kind, setKind] = useState('onboarding');
  const [lastDay, setLastDay] = useState('');
  const [reference, setReference] = useState('');
  const [confirm, setConfirm] = useState('');
  const [documents, setDocuments] = useState({});
  const [documentIds, setDocumentIds] = useState({});
  const load = useCallback(async () => {
    setLoading(true);
    try { setGroups((await api.getLifecycleChecklists()).data); }
    catch { setError('Unable to load checklists. Please retry.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const perform = async action => {
    setBusy(true); setError('');
    try { await action(); setConfirm(''); await load(); }
    catch (e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'The update could not be saved. Please retry.'); }
    finally { setBusy(false); }
  };
  const button = { padding: '10px 16px', minHeight: 44, cursor: 'pointer' };
  return <div data-testid="onboarding-page" style={{ fontFamily: 'Arial, sans-serif' }}>
    <h1 style={{ fontWeight: 900 }}>Onboarding & Offboarding</h1>
    <p>Track your assigned responsibilities. Private HR documents remain in the Document Centre.</p>
    <nav style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 20 }}>
      <Link to="/my-profile">My Profile</Link><Link to="/documents">Documents</Link><Link to="/notifications">Notifications</Link>
      <Link to="/policies">Policy Library</Link>
    </nav>
    {error && <div role="alert">{error} <button onClick={load}>Retry</button></div>}
    {hr && <form onSubmit={e => { e.preventDefault(); perform(() => api.initiateLifecycle({ employee_id: employee, kind,
      ...(kind === 'offboarding' ? { last_working_day: lastDay, authorization_reference: reference } : {}) })); }}
      style={{ background: '#fff', padding: 20, marginBottom: 20, display: 'grid', gap: 12 }}>
      <h2>Initiate a workflow</h2>
      <EmployeePicker value={employee} onChange={value => setEmployee(value.id)} disabled={busy} />
      <label>Workflow <select value={kind} onChange={e => setKind(e.target.value)}><option value="onboarding">Onboarding</option><option value="offboarding">Offboarding</option></select></label>
      {kind === 'offboarding' && <><label>Confirmed last working day <input type="date" required value={lastDay} onChange={e => setLastDay(e.target.value)} /></label>
        <label>HR authorization reference <input required maxLength={200} value={reference} onChange={e => setReference(e.target.value)} /></label>
        <p>Confirm contract notice, handover and exit authorization before initiating. This does not deactivate the account.</p></>}
      <button style={button} disabled={busy || !employee}>Initiate workflow</button>
      <p>Account creation uses the existing Access Control provisioning process and mandatory first-login password change.</p>
    </form>}
    {loading ? <p role="status">Loading checklists...</p> : groups.length === 0 ? <p>No onboarding or offboarding responsibilities available.</p> :
      groups.map(group => <section key={group.kind + group.employee_id} style={{ background: '#fff', padding: 20, marginBottom: 20 }}>
        <h2>{group.name} / {group.kind}</h2><p>{group.progress_pct}% complete {group.completed_at && '/ Archived'}</p>
        {group.last_working_day && <p>Last working day: {group.last_working_day}</p>}
        <progress value={group.progress_pct} max="100" aria-label="Checklist progress" />
        <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>{group.tasks.map(task => <div key={task.id} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', borderBottom: '1px solid #eee', paddingBottom: 12 }}>
          <div><strong>{task.title}</strong><div>{task.assigned_role?.replaceAll('_', ' ')} / {task.due_date || 'Due date awaiting HR confirmation'} / {task.status}</div>
            {task.document_id && <Link to="/documents">View authorized documents</Link>}</div>
          {hr && task.task_key === 'DOCS' && task.status !== 'Completed' && <div>
            <button disabled={busy} onClick={() => perform(async () => { const response = await api.getEmployeeDocuments(group.employee_id); setDocuments(previous => ({ ...previous, [group.employee_id]: response.data })); })}>Load employee documents</button>
            <label>Verified document <select value={documentIds[task.id] || ''} onChange={e => setDocumentIds(previous => ({ ...previous, [task.id]: e.target.value }))}>
              <option value="">Select a verified document</option>{(documents[group.employee_id] || []).filter(doc => !doc.deleted_at).map(doc => <option key={doc.id} value={doc.id}>{doc.title || doc.file_name || doc.category}</option>)}
            </select></label>
          </div>}
          {task.can_complete && task.status !== 'Completed' && !group.completed_at && <button style={button} disabled={busy}
            onClick={() => perform(() => api.updateLifecycleTask(group.kind, task.id, { status: 'Completed', ...(documentIds[task.id] ? { document_id: documentIds[task.id] } : {}) }))}>Mark complete</button>}
        </div>)}</div>
        {hr && group.kind === 'offboarding' && !group.completed_at && <div style={{ marginTop: 20 }}>
          {confirm === group.employee_id ? <><p>Archival requires completed clearance and the 17:00 EAT cutoff. Scheduled deactivation revokes access at that cutoff even if clearance remains open.</p>
            <button style={button} disabled={busy} onClick={() => perform(() => api.completeOffboarding(group.employee_id))}>Confirm deactivation</button>
            <button style={button} disabled={busy} onClick={() => perform(() => api.authorizeExitDeactivation(group.employee_id))}>Authorize scheduled deactivation</button>
            <button style={button} onClick={() => setConfirm('')}>Cancel</button></> : <button style={button} disabled={busy} onClick={() => setConfirm(group.employee_id)}>Review exit completion</button>}
        </div>}
      </section>)}
  </div>;
}
