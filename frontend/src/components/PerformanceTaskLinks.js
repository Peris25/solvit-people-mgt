import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPerformanceV3Tasks } from '../services/api';
import './PerformanceV3.css';

export default function PerformanceTaskLinks() {
  const [data, setData] = useState(null); const [error, setError] = useState(false); const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    (async () => { try { const response = await getPerformanceV3Tasks(); if (active) { setData(response.data); setError(false); } } catch { if (active) setError(true); } })();
    return () => { active = false; };
  }, [attempt]);
  return <section className="performance-v3"><div className="pv-card"><h2>360° peer reviews and Alignment</h2>
    {error ? <p role="alert">Performance tasks could not load. <button onClick={() => setAttempt(n => n + 1)}>Retry performance tasks</button></p> : !data ? <p>Loading performance tasks…</p> : <>
      {!data.peers.some(t => t.status === 'Assigned') && !data.alignment.some(t => !t.submitted) && <p>No pending peer or Alignment tasks.</p>}
      {data.peers.filter(t => t.status === 'Assigned').map(t => <p key={t.id}><Link to={`/performance?peer=${encodeURIComponent(t.id)}`}>Review {t.employee_name}</Link> · Due {t.due_on}</p>)}
      {data.alignment.filter(t => !t.submitted).map(t => <p key={t.id}><Link to={`/performance?alignment=${encodeURIComponent(t.id)}`}>{t.title} Alignment Survey</Link> · Due {t.due_on}</p>)}
    </>}
  </div></section>;
}
