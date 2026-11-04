import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import PublicSolverApplications from '../components/PublicSolverApplications';
import * as api from '../services/api';

export default function SolverApplicantInbox() {
  const { user } = useAuth();
  const key = `${user?.id}:${user?.role}`;
  const [access, setAccess] = useState(null);
  const eligible = ['hr_admin', 'hr_manager', 'general_manager', 'line_manager'].includes(user?.role);
  useEffect(() => {
    let cancelled = false;
    if (eligible) (async () => {
      try { const result = await api.getPublicSolverReviewCapabilities(); if (!cancelled) setAccess({ key, ...result?.data }); }
      catch { if (!cancelled) setAccess({ key, error: true }); }
    })();
    return () => { cancelled = true; };
  }, [key, eligible]);
  if (!eligible) return <p role="alert">HR or an authorized hiring lead is required to review applicant assessments.</p>;
  if (!access || access.key !== key) return <p role="status">Checking review access...</p>;
  if (!access.can_view) return <p role="alert">{access.error ? 'Unable to check review access. Please refresh.' : 'HR or an authorized hiring lead is required to review applicant assessments.'}</p>;
  return <div><h1>New Solver applications</h1><p>Assessments submitted by new job applicants through the standalone questionnaire.</p><PublicSolverApplications key={key} canReview={access.can_review} /></div>;
}
