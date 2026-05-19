import React, { useEffect, useMemo, useState } from 'react';
import OrgNode from '../components/OrgNode';
import * as api from '../services/api';

export default function Organogram() {
  const [roots, setRoots] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    api.getOrganogram()
      .then((r) => { setRoots(r.data.roots || []); setTotal(r.data.total || 0); })
      .catch((e) => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!filter.trim()) return roots;
    const q = filter.toLowerCase();
    const match = (n) =>
      (n.name || '').toLowerCase().includes(q) ||
      (n.role_title || '').toLowerCase().includes(q) ||
      (n.department || '').toLowerCase().includes(q) ||
      (n.work_email || '').toLowerCase().includes(q);
    const prune = (n) => {
      const childMatches = (n.direct_reports || []).map(prune).filter(Boolean);
      if (match(n) || childMatches.length > 0) {
        return { ...n, direct_reports: childMatches };
      }
      return null;
    };
    return roots.map(prune).filter(Boolean);
  }, [roots, filter]);

  return (
    <div data-testid="organogram-page" style={{ padding: '32px 28px', backgroundColor: '#F9FAFB', minHeight: '100vh' }}>
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'baseline', gap: '20px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0 }}>Organogram</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>
            Live reporting structure — auto-builds from each employee's line manager assignment.
          </p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <input
            data-testid="org-search"
            placeholder="Search name, role, department…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '13px', minWidth: '280px' }}
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
        <div style={{ overflowX: 'auto', padding: '20px', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <div style={{ display: 'inline-flex', alignItems: 'flex-start', gap: '24px', minWidth: 'max-content' }}>
            {filtered.map((r) => <OrgNode key={r.id} node={r} />)}
          </div>
        </div>
      ) : null}
    </div>
  );
}
