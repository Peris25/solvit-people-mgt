import React, { useState, useEffect } from 'react';
import StatusBadge from '../components/StatusBadge';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Projects() {
  const { user } = useAuth();
  const [projects, setProjects] = useState([]);
  const [eligible, setEligible] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('active');

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [pRes, eRes] = await Promise.all([
        api.get('/projects'),
        ['hr_admin', 'hr_manager'].includes(user?.role) ? api.get('/projects/eligible') : Promise.resolve({ data: [] })
      ]);
      setProjects(pRes.data);
      setEligible(eRes.data);
    } finally { setLoading(false); }
  };

  return (
    <div data-testid="projects-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>Project Ownership</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Reward high-performers with stretch projects (Score Exceeded)</p>
      </div>

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {[{ k: 'active', l: `Active Projects (${projects.length})` }, { k: 'eligible', l: `Eligible Employees (${eligible.length})` }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} style={{ padding: '10px 20px', backgroundColor: 'transparent', border: 'none', borderBottom: tab === t.k ? '2px solid #FF353F' : '2px solid transparent', marginBottom: '-2px', cursor: 'pointer', fontSize: '12px', fontWeight: tab === t.k ? 700 : 400, color: tab === t.k ? '#FF353F' : '#525252', fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{t.l}</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : tab === 'active' ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {projects.length === 0 ? (
            <div style={{ padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No projects assigned yet</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Employee', 'Project', 'Objective', 'Reward', 'Due', 'Status'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {projects.map((p, i) => (
                  <tr key={p.id} data-testid={`project-row-${p.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{p.employee_name}</td>
                    <td style={{ padding: '10px 14px' }}>{p.project_name}</td>
                    <td style={{ padding: '10px 14px', color: '#525252', fontSize: '11px' }}>{(p.project_objective || '').slice(0, 80)}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{p.reward_on_completion || '—'}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{p.expected_completion_date ? new Date(p.expected_completion_date).toLocaleDateString('en-GB') : '—'}</td>
                    <td style={{ padding: '10px 14px' }}><StatusBadge status={p.status} small /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          {eligible.length === 0 ? (
            <div style={{ padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No eligible employees yet. Employees become eligible when their performance score exceeds 1.49.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
                {['Employee', 'Role', 'Department', 'Last Score', 'Action'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)' }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {eligible.map((e, i) => (
                  <tr key={e.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700 }}>{e.full_name}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{e.role_title}</td>
                    <td style={{ padding: '10px 14px', color: '#525252' }}>{e.department}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700, color: '#22C55E' }}>{e.last_performance_score || '—'}</td>
                    <td style={{ padding: '10px 14px' }}><span style={{ color: '#9CA3AF', fontSize: '11px' }}>Assign via project form</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
