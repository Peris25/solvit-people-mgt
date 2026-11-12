import React, { useState } from 'react';
import { getPerformanceHandoffs } from '../services/api';
import { errorText } from './PerformanceV3Panel';
import './PerformanceV3.css';

export default function PerformanceHandoffs() {
  const [scorecard, setScorecard] = useState(''); const [rows, setRows] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <section className="performance-v3"><details className="pv-card"><summary>Released performance reviews — Finance handoff</summary>
    <p>Read-only review of released final scores. The company scorecard must reach 80% before a bonus multiplier applies. No salary, payment or payroll record is changed.</p>
    {error && <p role="alert">{error}</p>}<form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { const response = await getPerformanceHandoffs(scorecard); setRows(response.data); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }}>
      <label>Verified company scorecard % (optional for viewing)<input type="number" min="0" max="100" step="any" value={scorecard} onChange={e => setScorecard(e.target.value)} /></label><button disabled={busy}>View released performance handoffs</button></form>
    {rows?.length === 0 && <p>No released V3 performance handoffs are available.</p>}
    {rows?.map(row => <article key={row.review_id}><h3>{row.employee_name} · {row.period}</h3><p>Final score: {row.final_score} · {row.multiplier == null ? 'Company scorecard not entered' : `Multiplier: ${(row.multiplier * 100).toFixed(2)}%`}{row.values_hold && ' · Values hold requires HR review'}</p><p>{row.status}</p></article>)}
  </details></section>;
}
