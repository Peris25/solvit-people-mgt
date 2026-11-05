import React from 'react';
import { useAuth } from '../context/AuthContext';

export const SOLVER_INTAKE_ROLES = ['hr_admin', 'it_admin'];

export default function SolverIntakeAccess({ children }) {
  const { user } = useAuth();
  if (!SOLVER_INTAKE_ROLES.includes(user?.role)) {
    return <div role="alert" style={{ padding: 24 }}>Solver applicant administration is restricted to HR Admin and IT Admin.</div>;
  }
  return children;
}
