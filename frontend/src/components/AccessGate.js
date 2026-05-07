/**
 * AccessGate — wraps a page or section in an access check.
 * If the caller lacks the required level for the given module, renders a Forbidden state.
 *
 * <AccessGate module="M12" required="Read">
 *   <BudgetPage />
 * </AccessGate>
 */
import React from 'react';
import useModuleAccess from '../hooks/useModuleAccess';

export default function AccessGate({ module: moduleId, required = 'Read', children, fallback }) {
  const { loading, access, can } = useModuleAccess(moduleId);

  if (loading) {
    return <div data-testid={`access-loading-${moduleId}`} style={{ padding: '48px', textAlign: 'center', color: '#525252' }}>Checking access…</div>;
  }
  if (!can(required)) {
    if (fallback) return fallback;
    return (
      <div data-testid={`access-denied-${moduleId}`} style={{
        padding: '48px', textAlign: 'center', backgroundColor: '#fff',
        border: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Arial'
      }}>
        <div style={{ fontSize: '36px', marginBottom: '12px' }}>🔒</div>
        <h2 style={{ fontSize: '20px', fontWeight: 900, color: '#191919', margin: '0 0 8px' }}>Access Restricted</h2>
        <p style={{ fontSize: '13px', color: '#525252', margin: 0 }}>
          You don't have <strong>{required}</strong> access to module <strong>{moduleId}</strong>.
        </p>
        {access && (
          <p style={{ fontSize: '11px', color: '#9CA3AF', marginTop: '12px' }}>
            Your access: <code>{access.level}</code>{access.scope ? ` · scope: ${access.scope}` : ''}
          </p>
        )}
      </div>
    );
  }
  // Pass access info through context if children are a function
  if (typeof children === 'function') return children({ access, can });
  return children;
}
