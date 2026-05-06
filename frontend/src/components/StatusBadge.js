import React from 'react';

const STATUS_CONFIG = {
  // Employee lifecycle
  'Onboarding': { bg: '#DBEAFE', color: '#1D4ED8', label: 'Onboarding' },
  'Probation': { bg: '#FEF3C7', color: '#92400E', label: 'Probation' },
  'Active': { bg: '#DCFCE7', color: '#166534', label: 'Active' },
  'On_Leave': { bg: '#E0F2FE', color: '#0369A1', label: 'On Leave' },
  'PIP': { bg: '#FEE2E2', color: '#991B1B', label: 'PIP' },
  'Realignment': { bg: '#FFF7ED', color: '#9A3412', label: 'Realignment' },
  'Exiting': { bg: '#FFEDD5', color: '#9A3412', label: 'Exiting' },
  'Exited': { bg: '#F3F4F6', color: '#374151', label: 'Exited' },
  'Candidate': { bg: '#EDE9FE', color: '#5B21B6', label: 'Candidate' },
  // Solver states
  'Registering': { bg: '#DBEAFE', color: '#1D4ED8', label: 'Registering' },
  'Suspended': { bg: '#FEE2E2', color: '#991B1B', label: 'Suspended' },
  'Inactive': { bg: '#F3F4F6', color: '#374151', label: 'Inactive' },
  'Deactivated': { bg: '#111827', color: '#F3F4F6', label: 'Deactivated' },
  // Flight risk
  'Low': { bg: '#DCFCE7', color: '#166534', label: 'Low Risk' },
  'Elevated': { bg: '#FEF3C7', color: '#92400E', label: 'Elevated Risk' },
  'High': { bg: '#FFEDD5', color: '#9A3412', label: 'High Risk' },
  'Critical': { bg: '#FEE2E2', color: '#991B1B', label: 'Critical Risk' },
  // Task/form status
  'Pending': { bg: '#FEF3C7', color: '#92400E', label: 'Pending' },
  'In_Progress': { bg: '#DBEAFE', color: '#1D4ED8', label: 'In Progress' },
  'Completed': { bg: '#DCFCE7', color: '#166534', label: 'Completed' },
  'Overdue': { bg: '#FEE2E2', color: '#991B1B', label: 'Overdue' },
  'Rejected': { bg: '#FEE2E2', color: '#991B1B', label: 'Rejected' },
  'Approved': { bg: '#DCFCE7', color: '#166534', label: 'Approved' },
  'Submitted': { bg: '#DBEAFE', color: '#1D4ED8', label: 'Submitted' },
  'Draft': { bg: '#F3F4F6', color: '#374151', label: 'Draft' },
  // Performance ratings
  'Exceeded': { bg: '#DCFCE7', color: '#166534', label: 'Exceeded' },
  'Met': { bg: '#DBEAFE', color: '#1D4ED8', label: 'Met' },
  'Below': { bg: '#FEF3C7', color: '#92400E', label: 'Below' },
  'Forfeited': { bg: '#FEE2E2', color: '#991B1B', label: 'Forfeited' },
  // General
  'Open': { bg: '#DCFCE7', color: '#166534', label: 'Open' },
  'Closed': { bg: '#F3F4F6', color: '#374151', label: 'Closed' },
  'Active_state': { bg: '#DCFCE7', color: '#166534', label: 'Active' },
};

export default function StatusBadge({ status, small = false, className = '' }) {
  const config = STATUS_CONFIG[status] || { bg: '#F3F4F6', color: '#374151', label: status || 'Unknown' };
  return (
    <span
      data-testid={`status-badge-${status}`}
      style={{
        display: 'inline-flex', alignItems: 'center',
        backgroundColor: config.bg, color: config.color,
        fontSize: small ? '9px' : '11px',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        padding: small ? '2px 6px' : '3px 8px',
        fontFamily: 'Arial, Helvetica, sans-serif',
      }}
    >
      {config.label}
    </span>
  );
}
