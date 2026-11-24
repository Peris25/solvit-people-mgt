import React, { useEffect, useMemo, useState } from 'react';
import EmployeeOrgChart from '../components/EmployeeOrgChart';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { STAFF_DIRECTORY_ROLES } from '../utils/staffDirectory';

export default function Organogram() {
  const { user } = useAuth();
  const allowed = STAFF_DIRECTORY_ROLES.includes(user?.role);
  const [roots, setRoots] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [issues, setIssues] = useState(0);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError(''); setRoots([]); setTotal(0); setIssues(0);
    api.getOrganogram()
      .then((r) => {
        if (!r.data || !Array.isArray(r.data.roots)) throw new Error(r.error || 'The reporting structure could not be loaded. Please try again.');
        if (r.data.total > 0 && r.data.roots.length === 0) throw new Error('The reporting structure needs an integrity review.');
        if (active) { setRoots(r.data.roots); setTotal(r.data.total || 0); setIssues(r.data.issues || 0); }
      })
      .catch((e) => { const detail = e.response?.data?.detail; if (active) setError(typeof detail === 'string' ? detail : detail?.message || e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed, user?.id, user?.role]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return roots;
    const q = filter.toLowerCase();
    const match = (n) =>
      (n.name || '').toLowerCase().includes(q) ||
      (n.role_title || '').toLowerCase().includes(q) ||
      (n.department || '').toLowerCase().includes(q) ||
      (n.department_label || '').toLowerCase().includes(q) ||
      (n.work_email || '').toLowerCase().includes(q);
    const prune = (n) => {
      if(match(n))return n;
      const childMatches = (n.direct_reports || []).map(prune).filter(Boolean);
      if (childMatches.length > 0) {
        return { ...n, direct_report_count:(n.direct_reports||[]).length,direct_reports: childMatches };
      }
      return null;
    };
    return roots.map(prune).filter(Boolean);
  }, [roots, filter]);

  if (!allowed) return <div role="alert" style={{ padding: 28 }}>Staff organogram access is not available for this account.</div>;
  return (
    <div data-testid="organogram-page" className="workspace-page org-page">
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'baseline', gap: '20px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0 }}>Organogram</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>
            See who reports to whom across Solvit.
          </p>
        </div>
        <div className="org-page-search" style={{ marginLeft: 'auto' }}>
          <input
            data-testid="org-search"
            placeholder="Search name, role, department…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Search reporting relationships"
            style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px' }}
          />
          <span style={{ fontSize: '12px', color: '#525252' }}>
            <strong style={{ color: '#191919' }}>{total}</strong> people
          </span>
        </div>
      </div>

      {loading ? <div style={{ padding: '32px' }}>Loading organogram…</div> : null}
      {error ? (
        <div style={{ padding: '16px', backgroundColor: '#FEE2E2', color: '#991B1B', fontSize: '13px' }}>
          Couldn't load organogram: {error}
        </div>
      ) : null}
      {!loading && !error && total === 0 ? (
        <div data-testid="org-empty" style={{ padding: '48px', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 900 }}>No employees yet</h3>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0 }}>
            Add employees in the Employees module — each one with a line manager will appear here automatically.
          </p>
        </div>
      ) : null}
      {!loading && !error && filtered.length > 0 ? (
        <EmployeeOrgChart key={`${user?.id}:${user?.role}:${filter.trim()}`} roots={filtered} sourceRoots={roots} onWholeCompany={()=>setFilter('')}/>
      ) : null}
      {!loading && !error && issues > 0 && <p role="status" style={{ color: '#92400E', fontSize: '12px' }}>Some identifiers or reporting links need review. Unresolved branches are shown separately; saved assignments have not been changed.</p>}
      {!loading && !error && total > 0 && filtered.length === 0 && <p role="status" style={{ color: '#525252', fontSize: '13px' }}>No people match your search.</p>}
    </div>
  );
}
