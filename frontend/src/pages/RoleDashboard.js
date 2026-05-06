/**
 * RoleDashboard — picks the appropriate dashboard view based on current user role.
 * - hr_admin / hr_manager / executive / line_manager / finance → HR Admin Dashboard (Kanban control surface)
 * - employee → personal action dashboard
 * - solver → mobile bottom-nav dashboard
 */
import React from 'react';
import { useAuth } from '../context/AuthContext';
import HRDashboard from './Dashboard';
import EmployeeDashboard from './EmployeeDashboard';
import SolverDashboard from './SolverDashboard';

export default function RoleDashboard() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === 'solver') return <SolverDashboard />;
  if (user.role === 'employee') return <EmployeeDashboard />;
  // Default: HR Admin / Manager / Executive / Line Manager / Finance see operational dashboard
  return <HRDashboard />;
}
