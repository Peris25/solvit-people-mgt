/**
 * RoleDashboard — picks the appropriate dashboard view based on current user role.
 * - linked FTE accounts → Staff Home with their existing role dashboard as a view
 * - unlinked administrative accounts → existing operational dashboard
 * - line_manager → LineManagerDashboard (scoped to self + direct reports)
 * - employee → personal action dashboard
 * - solver → mobile bottom-nav dashboard
 */
import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import HRDashboard from './Dashboard';
import EmployeeDashboard from './EmployeeDashboard';
import SolverDashboard from './SolverDashboard';
import LineManagerDashboard from './LineManagerDashboard';

export default function RoleDashboard() {
  const { user } = useAuth();
  const [view, setView] = useState('home');
  if (!user) return null;
  if (user.role === 'solver') return <SolverDashboard />;
  if (user.role === 'employee') return <EmployeeDashboard key={user.id} />;
  if (user.employee_id) return <>
    <nav aria-label="Dashboard views" style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
      <button onClick={() => setView('home')} aria-pressed={view === 'home'} style={{ minHeight: '44px', padding: '10px 16px' }}>Staff Home</button>
      <button onClick={() => setView('role')} aria-pressed={view === 'role'} style={{ minHeight: '44px', padding: '10px 16px' }}>{user.role === 'line_manager' ? 'My Team' : 'Role Dashboard'}</button>
    </nav>
    {view === 'home' ? <EmployeeDashboard key={user.id} /> : user.role === 'line_manager' ? <LineManagerDashboard /> : <HRDashboard />}
  </>;
  if (user.role === 'line_manager') return <LineManagerDashboard />;
  // Default: HR Admin / Manager / Executive / Finance see operational dashboard
  return <HRDashboard />;
}
