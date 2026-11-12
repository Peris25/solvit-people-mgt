import React from 'react';
import './Workspace.css';

export default function WorkspaceSkeleton({ label = 'Loading...', profile = false }) {
  return <div className={`workspace-skeleton${profile ? ' workspace-skeleton-profile' : ''}`} role="status" aria-label={label}>
    <span className="workspace-sr-only">{label}</span>
    {profile && <div className="workspace-skeleton-hero" aria-hidden="true"><i /><i /></div>}
    <div className="workspace-skeleton-heading" aria-hidden="true"><i /><i /></div>
    {Array.from({ length: profile ? 4 : 5 }, (_, index) => <div className="workspace-skeleton-row" aria-hidden="true" key={index}><i /><i /><i /><i /></div>)}
  </div>;
}
