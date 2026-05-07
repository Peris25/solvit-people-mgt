/**
 * useModuleAccess — fetches the current user's access entry for a single module
 * (Section A of the Access Rule Matrix). Returns { loading, access, can }.
 *
 * Usage:
 *   const { access, can, loading } = useModuleAccess('M01');
 *   if (loading) return <Spinner/>;
 *   if (!can('Read')) return <Forbidden/>;
 */
import { useState, useEffect } from 'react';
import * as api from '../services/api';

const RANK = { Read: 1, Manage: 2, Full: 3 };

export default function useModuleAccess(moduleId) {
  const [state, setState] = useState({ loading: true, access: null });

  useEffect(() => {
    if (!moduleId) { setState({ loading: false, access: null }); return; }
    let cancelled = false;
    api.checkModuleAccess(moduleId)
      .then(r => { if (!cancelled) setState({ loading: false, access: r.data?.access || null }); })
      .catch(() => { if (!cancelled) setState({ loading: false, access: null }); });
    return () => { cancelled = true; };
  }, [moduleId]);

  const can = (level = 'Read') => {
    if (!state.access) return false;
    return (RANK[state.access.level] || 0) >= (RANK[level] || 0);
  };

  return { ...state, can };
}
