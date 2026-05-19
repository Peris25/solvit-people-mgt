import React, { useState } from 'react';

const STATE_COLOR = {
  Active: '#16A34A', Onboarding: '#1D4ED8', Probation: '#F97316',
  On_Leave: '#A855F7', PIP: '#FF353F', Suspended: '#9CA3AF',
  Exiting: '#525252', Notice_Period: '#525252',
};

function OrgNode(props) {
  const node = props.node;
  const [open, setOpen] = useState(true);
  const reports = node.direct_reports || [];
  const hasReports = reports.length > 0;
  const color = STATE_COLOR[node.lifecycle_state] || '#191919';

  return (
    <div
      data-testid={'org-node-' + node.id}
      style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', padding: '0 8px' }}
    >
      <div
        onClick={() => hasReports && setOpen(!open)}
        style={{
          minWidth: '220px', maxWidth: '240px',
          backgroundColor: '#fff',
          border: '1px solid rgba(25,25,25,0.12)',
          borderTop: '3px solid ' + color,
          padding: '12px 14px',
          cursor: hasReports ? 'pointer' : 'default',
          boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
          position: 'relative',
        }}
      >
        <div style={{ fontSize: '13px', fontWeight: 900, color: '#191919', letterSpacing: '-0.01em' }}>
          {node.name || '—'}
        </div>
        <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px' }}>
          {node.role_title || '—'}
        </div>
        <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '6px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {node.department || '—'}
        </div>
        {hasReports ? (
          <div style={{ position: 'absolute', top: '8px', right: '10px', fontSize: '10px', color: '#525252', fontWeight: 700 }}>
            {(open ? '−' : '+') + ' ' + reports.length}
          </div>
        ) : null}
      </div>

      {hasReports && open ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ width: '2px', height: '20px', backgroundColor: 'rgba(25,25,25,0.2)' }} />
          <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '20px' }}>
            {reports.length > 1 ? (
              <div style={{
                position: 'absolute', top: 0, left: '8%', right: '8%',
                height: '2px', backgroundColor: 'rgba(25,25,25,0.2)',
              }} />
            ) : null}
            {reports.map((child) =>
              React.createElement(
                'div',
                { key: child.id, style: { display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' } },
                React.createElement('div', { style: { position: 'absolute', top: '-20px', width: '2px', height: '20px', backgroundColor: 'rgba(25,25,25,0.2)' } }),
                React.createElement(OrgNode, { node: child })
              )
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default OrgNode;
