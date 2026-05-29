import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import ApplicantDetailModal from '../components/ApplicantDetailModal';

const CHANNELS = ['Facebook', 'Instagram', 'WhatsApp', 'Referral from a Solver', 'Job board', 'Other'];

export default function EligibleSolvers() {
  const [rows, setRows] = useState([]);
  const [reqs, setReqs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ county: '', channel: '', requisition_id: '', current_stage: '' });
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = async (f = filters) => {
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
      const r = await api.listEligibleSolvers(params);
      setRows(r.data.rows || []);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    api.listSolverRequisitions().then(r => setReqs(r.data.requisitions || [])).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetail = async (cid) => {
    setSelectedId(cid);
    setDetail(null);
    setDetailLoading(true);
    try {
      const r = await api.getEligibleSolver(cid);
      setDetail(r.data);
    } finally { setDetailLoading(false); }
  };

  const apply = () => load(filters);

  return (
    <div data-testid="eligible-page" style={{ padding: '32px 28px', backgroundColor: '#F9FAFB', minHeight: '100vh' }}>
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', margin: 0 }}>Eligible Solvers</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>
            Applicants who cleared Stage 1 eligibility and entered the Solver pipeline. Click a row for full submission details.
          </p>
        </div>
        <a data-testid="export-csv" href={api.exportEligibleCsv(filters)} style={{ padding: '8px 16px', backgroundColor: '#191919', color: '#fff', textDecoration: 'none', fontSize: '12px', fontWeight: 700 }}>
          Export CSV
        </a>
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '14px 18px', marginBottom: '16px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <FilterField label="Requisition" value={filters.requisition_id} onChange={v => setFilters({ ...filters, requisition_id: v })}>
          <option value="">Any</option>
          {reqs.map(r => <option key={r.id} value={r.id}>{r.code} — {r.title}</option>)}
        </FilterField>
        <FilterField label="County" value={filters.county} onChange={v => setFilters({ ...filters, county: v })} isText />
        <FilterField label="Channel" value={filters.channel} onChange={v => setFilters({ ...filters, channel: v })}>
          <option value="">Any</option>
          {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
        </FilterField>
        <FilterField label="Stage contains" value={filters.current_stage} onChange={v => setFilters({ ...filters, current_stage: v })} isText />
        <button data-testid="apply-filters" onClick={apply} style={{ padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700 }}>Apply</button>
        <span style={{ marginLeft: 'auto', fontSize: '12px', color: '#525252' }}>{rows.length} records</span>
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead style={{ backgroundColor: '#F9FAFB', borderBottom: '2px solid rgba(25,25,25,0.08)' }}>
            <tr style={{ textAlign: 'left', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.1em', color: '#525252' }}>
              <th style={{ padding: '10px 12px' }}>Submitted</th>
              <th style={{ padding: '10px 12px' }}>Requisition</th>
              <th style={{ padding: '10px 12px' }}>Name</th>
              <th style={{ padding: '10px 12px' }}>Contact</th>
              <th style={{ padding: '10px 12px' }}>Location</th>
              <th style={{ padding: '10px 12px' }}>Channel</th>
              <th style={{ padding: '10px 12px' }}>Current Stage</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: '#9CA3AF' }}>Loading…</td></tr>}
            {!loading && rows.map(r => (
              <tr
                key={r.id}
                data-testid={`eligible-row-${r.id}`}
                onClick={() => openDetail(r.id)}
                style={{ borderBottom: '1px solid rgba(25,25,25,0.04)', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = '#F9FAFB'}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = '#fff'}
              >
                <td style={{ padding: '10px 12px' }}>{r.created_at ? new Date(r.created_at).toLocaleString('en-KE') : '—'}</td>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace' }}>{r.requisition_code}</td>
                <td style={{ padding: '10px 12px', fontWeight: 700 }}>{r.full_name}</td>
                <td style={{ padding: '10px 12px' }}><div>{r.email}</div><div style={{ fontSize: '11px', color: '#525252' }}>{r.phone_number}</div></td>
                <td style={{ padding: '10px 12px' }}><div>{r.county}</div><div style={{ fontSize: '11px', color: '#525252' }}>{r.town_area}</div></td>
                <td style={{ padding: '10px 12px' }}>{r.source}</td>
                <td style={{ padding: '10px 12px', fontSize: '11px' }}>{r.current_stage}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && <tr><td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#9CA3AF' }}>No eligible solvers match these filters.</td></tr>}
          </tbody>
        </table>
      </div>

      <ApplicantDetailModal
        open={!!selectedId}
        loading={detailLoading}
        data={detail}
        mode="eligible"
        onClose={() => { setSelectedId(null); setDetail(null); }}
      />
    </div>
  );
}

function FilterField({ label, value, onChange, children, isText }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>{label}</label>
      {isText ? (
        <input value={value} onChange={e => onChange(e.target.value)} placeholder="—"
          style={{ padding: '6px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', minWidth: '160px' }} />
      ) : (
        <select value={value} onChange={e => onChange(e.target.value)} style={{ padding: '6px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', minWidth: '180px' }}>
          {children}
        </select>
      )}
    </div>
  );
}
