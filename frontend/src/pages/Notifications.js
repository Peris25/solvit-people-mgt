import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useNotifications } from '../context/NotificationContext';
import * as api from '../services/api';

const PAGE_SIZE = 20;
const buttonStyle = { minHeight: '44px', padding: '10px 16px', border: '1px solid #D9D9D9', background: '#fff', cursor: 'pointer', color: '#191919' };
export const safeNotificationLink = value => typeof value === 'string' && /^\/(leave|lnd|employees\/[^/?#]+|forms|policies|my-tasks)(?:[?#].*)?$/.test(value) ? value : null;
const eatDay = value => {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleDateString('en-CA', { timeZone: 'Africa/Nairobi' }) : '';
};

export default function Notifications() {
  const { user } = useAuth();
  const { markRead, refresh } = useNotifications();
  const key = `${user?.id}:${user?.role}`;
  const [category, setCategory] = useState('');
  const [readStatus, setReadStatus] = useState('all');
  const [kind, setKind] = useState('');
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState({ key: null, loading: true, data: null, error: '' });
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(null);
  useEffect(() => {
    let cancelled = false;
    setState({ key, loading: true, data: null, error: '' });
    api.getNotificationCentre({ category: category || undefined, kind: kind || undefined, read_status: readStatus, offset, limit: PAGE_SIZE })
      .then(response => {
        if (cancelled) return;
        if (!Array.isArray(response.data?.items)) throw new Error('Unavailable');
        setState({ key, loading: false, data: response.data, error: '' });
      })
      .catch(() => { if (!cancelled) setState({ key, loading: false, data: null, error: 'Notifications could not be loaded. Please retry.' }); });
    return () => { cancelled = true; };
  }, [key, category, kind, readStatus, offset, version]);
  useEffect(() => {
    const timer = setInterval(() => setVersion(value => value + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => { setOffset(0); setActionError(''); setBusy(null); }, [key]);
  const reload = () => { setVersion(value => value + 1); refresh(); };
  const read = async item => {
    setBusy(item.id); setActionError('');
    try { await markRead(item.id); setVersion(value => value + 1); }
    catch (_) { setActionError('The notification could not be marked as read. Please retry.'); }
    finally { setBusy(null); }
  };
  const decide = async (item, decision) => {
    setBusy(item.id); setActionError('');
    try {
      const response = await api.leaveDecision(item.action.record_id, { decision });
      if (!response.data) throw new Error('Unavailable');
      await markRead(item.id); setVersion(value => value + 1);
    } catch (_) {
      setActionError('The action could not be confirmed. Refresh and check the request before retrying.');
      reload();
    } finally { setBusy(null); }
  };
  const data = state.key === key ? state.data : null;
  const loading = state.key !== key || state.loading;
  const items = data?.items || [];
  const today = eatDay(new Date().toISOString());
  return <div data-testid="notification-centre" style={{ fontFamily: 'Nunito Sans, Arial, sans-serif' }}>
    <header style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '12px', marginBottom: '20px' }}>
      <div><h1 style={{ margin: 0, color: '#191919', fontSize: '28px' }}>Notifications</h1><p>{data ? `${data.unread_count} unread` : 'Your updates and actions in one place.'}</p></div>
      <button onClick={reload} style={buttonStyle}>Refresh</button>
    </header>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
      <label>Category <select aria-label="Notification category" value={category} onChange={event => { setCategory(event.target.value); setOffset(0); }} style={buttonStyle}>
        <option value="">All categories</option>
        {[...new Set([...(data?.categories || []), ...(category ? [category] : [])])].map(item => <option key={item}>{item}</option>)}
      </select></label>
      <label>Type <select aria-label="Notification type" value={kind} onChange={event => { setKind(event.target.value); setOffset(0); }} style={buttonStyle}>
        <option value="">All types</option><option>Action required</option><option>Updates</option><option>Approvals</option>
      </select></label>
      <label>Status <select aria-label="Notification status" value={readStatus} onChange={event => { setReadStatus(event.target.value); setOffset(0); }} style={buttonStyle}>
        <option value="all">All</option><option value="unread">Unread</option><option value="read">Read</option>
      </select></label>
    </div>
    {actionError && <div role="alert" style={{ padding: '16px', background: '#FEE2E2', marginBottom: '12px' }}>{actionError}</div>}
    {loading ? <div role="status" aria-label="Loading notifications" style={{ padding: '24px', background: '#fff' }}>Loading notifications…<div style={{ height: '64px', background: '#F5F5F5', marginTop: '16px' }} /></div>
      : state.error ? <div role="alert" style={{ padding: '24px', background: '#FEE2E2' }}>{state.error}<button onClick={reload} style={{ ...buttonStyle, marginLeft: '12px' }}>Retry</button></div>
      : items.length === 0 ? <div style={{ padding: '32px', background: '#fff' }}><h2 style={{ fontSize: '18px' }}>No notifications {category || kind || readStatus !== 'all' ? 'match these filters' : 'yet'}</h2><p>Your relevant updates and actions will appear here.</p><Link to="/dashboard">Back to Staff Home</Link></div>
      : ['Today', 'Earlier'].map(group => {
        const rows = items.filter(item => (eatDay(item.created_at) === today ? 'Today' : 'Earlier') === group);
        return rows.length ? <section key={group} aria-label={group}><h2 style={{ fontSize: '16px' }}>{group}</h2>
          {rows.map(item => <article key={item.id} data-testid={`notification-${item.id}`} style={{ padding: '20px', marginBottom: '12px', background: item.is_read ? '#fff' : '#FEF2F2', borderLeft: `4px solid ${item.is_read ? '#D9D9D9' : '#FF353F'}`, overflowWrap: 'anywhere' }}>
            <div style={{ fontSize: '12px', color: '#525252' }}>{item.category} · {item.kind} · {item.sender || 'Solvit People'}</div>
            <h3 style={{ margin: '8px 0', fontSize: '16px' }}>{item.title}</h3><p>{item.message}</p>
            <small>{eatDay(item.created_at) ? new Date(item.created_at).toLocaleString('en-KE', { timeZone: 'Africa/Nairobi' }) + ' EAT' : 'Time not recorded'} · {item.is_read ? 'Read' : 'Unread'}</small>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px', marginTop: '12px' }}>
              {!item.is_read && <button onClick={() => read(item)} disabled={busy != null} style={buttonStyle}>{busy === item.id ? 'Saving…' : 'Mark as read'}</button>}
              {safeNotificationLink(item.link) && <Link to={item.link} onClick={() => { if (!item.is_read) read(item); }} style={{ ...buttonStyle, display: 'inline-flex', alignItems: 'center' }}>Open related record</Link>}
              {item.action?.kind === 'leave' && <>
                <button disabled={busy != null} onClick={() => decide(item, 'Approve')} style={{ ...buttonStyle, color: '#166534' }}>Approve</button>
                <button disabled={busy != null} onClick={() => decide(item, 'Reject')} style={{ ...buttonStyle, color: '#B91C1C' }}>Reject</button>
              </>}
            </div>
          </article>)}
        </section> : null;
      })}
    {data && data.filtered_total > PAGE_SIZE && <nav aria-label="Notification pages" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
      <button style={buttonStyle} disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</button>
      <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, data.filtered_total)} of {data.filtered_total}</span>
      <button style={buttonStyle} disabled={loading || offset + PAGE_SIZE >= data.filtered_total} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</button>
    </nav>}
  </div>;
}
