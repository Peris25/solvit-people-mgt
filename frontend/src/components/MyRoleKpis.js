import React, { useEffect, useState } from 'react';
import { getMyRoleKpis } from '../services/api';

export default function MyRoleKpis() {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ loading: true, data: null, error: '' });
    (async () => {
      try {
        const response = await getMyRoleKpis();
        if (active) setState({ loading: false, data: response.data, error: '' });
      } catch {
        if (active) setState({ loading: false, data: null, error: 'Unable to load your role KPIs.' });
      }
    })();
    return () => { active = false; };
  }, [attempt]);
  return <section className="bg-white rounded-2xl border border-slate-200 p-6 mb-6" aria-label="My role KPIs">
    <h2 className="text-lg font-semibold text-slate-900">My role KPIs</h2>
    <p className="text-sm text-slate-600 mt-1">Your approved expectations are available from account setup. Review them with your line manager during Week 3 of onboarding.</p>
    {state.loading ? <p role="status" className="mt-4">Loading your KPIs…</p> : state.error ?
      <div role="alert" className="mt-4">{state.error} <button type="button" onClick={() => setAttempt(n => n + 1)} className="border rounded-lg px-4 py-2 ml-2">Retry</button></div> :
      !state.data ? <p className="mt-4 text-sm text-slate-600">HR has not assigned approved role KPIs yet. Please contact HR to confirm them.</p> :
      <><h3 className="font-medium mt-4">{state.data.name}</h3><div className="overflow-x-auto mt-3"><table className="w-full text-sm text-left">
        <thead><tr className="border-b"><th className="p-3">Objective</th><th className="p-3">Measurement</th><th className="p-3">Target</th><th className="p-3">Weight</th></tr></thead>
        <tbody>{state.data.goals.map(goal => <tr key={goal.id} className="border-b last:border-0"><td className="p-3">{goal.objective}</td><td className="p-3">{goal.metric}</td><td className="p-3">{goal.target}</td><td className="p-3">{goal.weight}%{goal.group ? ` (${goal.group})` : ''}</td></tr>)}</tbody>
      </table></div></>}
  </section>;
}
