import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import * as api from '../services/api';

const NotificationContext = createContext(null);
export const useNotifications = () => useContext(NotificationContext);

export function NotificationProvider({ children }) {
  const { user } = useAuth();
  const key = user && !user.must_change_password && !(user.mfa_required && !user.mfa_verified) ? `${user.id}:${user.role}` : null;
  const activeKey = useRef(key); activeKey.current = key;
  const sequence = useRef(0);
  const [state, setState] = useState({ key: null, items: [], unreadCount: null, loading: false, error: '' });
  const refresh = useCallback(async () => {
    if (!key) return;
    const request = ++sequence.current;
    try {
      const response = await api.getNotificationCentre({ limit: 20 });
      if (!Array.isArray(response.data?.items)) throw new Error('Unavailable');
      if (activeKey.current === key && request === sequence.current) {
        setState({ key, items: response.data.items, unreadCount: response.data.unread_count, loading: false, error: '' });
      }
    } catch (_) {
      if (activeKey.current === key && request === sequence.current) setState({ key, items: [], unreadCount: null, loading: false, error: 'Notifications are unavailable. Please retry.' });
    }
  }, [key]);
  useEffect(() => {
    setState({ key, items: [], unreadCount: null, loading: !!key, error: '' });
    if (!key) return undefined;
    refresh();
    const timer = setInterval(refresh, 60000);
    return () => { sequence.current += 1; clearInterval(timer); };
  }, [key, refresh]);
  const markRead = useCallback(async id => {
    const response = await api.markNotificationRead(id);
    if (activeKey.current !== key) return;
    if (!response.data?.is_read) throw new Error('The notification could not be marked as read. Please retry.');
    await refresh();
  }, [key, refresh]);
  const current = state.key === key ? state : { items: [], unreadCount: null, loading: !!key, error: '' };
  const markAllRead = async () => {
    const ids = current.items.filter(item => !item.is_read).map(item => item.id);
    const results = await Promise.allSettled(ids.map(id => api.markNotificationRead(id)));
    if (activeKey.current !== key) return;
    await refresh();
    if (results.some(result => result.status === 'rejected' || !result.value.data?.is_read)) {
      setState(previous => ({ ...previous, error: 'Some notifications could not be marked as read. Please retry.' }));
    }
  };
  return <NotificationContext.Provider value={{ ...current, refresh, markRead, markAllRead }}>{children}</NotificationContext.Provider>;
}
