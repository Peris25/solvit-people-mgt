/**
 * RoleDashboard — picks the appropriate dashboard view based on current user role.
 * - linked FTE accounts → Staff Home with their existing role dashboard as a view
 * - unlinked administrative accounts → existing operational dashboard
 * - line_manager → LineManagerDashboard (scoped to self + direct reports)
 * - employee → personal action dashboard
 * - solver → mobile bottom-nav dashboard
 */
import React, { lazy, useState } from 'react';
import { useAuth } from '../context/AuthContext';
const HRDashboard = lazy(() => import('./Dashboard'));
const EmployeeDashboard = lazy(() => import('./EmployeeDashboard'));
const SolverDashboard = lazy(() => import('./SolverDashboard'));
const LineManagerDashboard = lazy(() => import('./LineManagerDashboard'));

export default function RoleDashboard() {
  const { user } = useAuth();
  const [view, setView] = useState('home');
  if (!user) return null;
  const isManager = ['line_manager', 'it_admin'].includes(user.role);
  if (user.role === 'solver') return <SolverDashboard />;
  if (user.role === 'employee') return <EmployeeDashboard key={user.id} />;
  if (user.employee_id) return <>
    <nav aria-label="Dashboard views" style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
      <button onClick={() => setView('home')} aria-pressed={view === 'home'} style={{ minHeight: '44px', padding: '10px 16px' }}>Staff Home</button>
      <button onClick={() => setView('role')} aria-pressed={view === 'role'} style={{ minHeight: '44px', padding: '10px 16px' }}>{isManager ? 'My Team' : 'Role Dashboard'}</button>
    </nav>
    {view === 'home' ? <EmployeeDashboard key={user.id} /> : isManager ? <LineManagerDashboard /> : <HRDashboard />}
  </>;
  if (isManager) return <LineManagerDashboard />;
  // Default: HR Admin / Manager / Executive / Finance see operational dashboard
  return <HRDashboard />;
}
