/**
 * RoleDashboard — picks the appropriate dashboard view based on current user role.
 * - hr_admin / hr_manager / executive / finance → HR Admin Dashboard (Kanban control surface)
 * - line_manager → LineManagerDashboard (scoped to self + direct reports)
 * - employee → personal action dashboard
 * - solver → mobile bottom-nav dashboard
 */
import React from 'react';
import { useAuth } from '../context/AuthContext';
import HRDashboard from './Dashboard';
import EmployeeDashboard from './EmployeeDashboard';
import SolverDashboard from './SolverDashboard';
import LineManagerDashboard from './LineManagerDashboard';

export default function RoleDashboard() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === 'solver') return <SolverDashboard />;
  if (user.role === 'employee') return <EmployeeDashboard />;
  if (user.role === 'line_manager') return <LineManagerDashboard />;
  // Default: HR Admin / Manager / Executive / Finance see operational dashboard
  return <HRDashboard />;
}
