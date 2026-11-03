import React from 'react';
import { useAuth } from '../context/AuthContext';
import PublicSolverApplications from '../components/PublicSolverApplications';

export default function SolverApplicantInbox() {
  const { user } = useAuth();
  if (!['hr_admin', 'hr_manager', 'general_manager'].includes(user?.role)) return <p role="alert">HR access is required to review applicant assessments.</p>;
  return <div><h1>New Solver applications</h1><p>Assessments submitted by new job applicants through the standalone questionnaire.</p><PublicSolverApplications key={`${user.id}:${user.role}`} /></div>;
}
