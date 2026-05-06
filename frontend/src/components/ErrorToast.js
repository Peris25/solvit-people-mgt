import React, { useEffect, useState } from 'react';

export default function ErrorToast() {
  const [errors, setErrors] = useState([]);

  useEffect(() => {
    const handler = (e) => {
      const id = Date.now() + Math.random();
      const detail = e.detail || {};
      setErrors(prev => [...prev, { id, ...detail }]);
      // Auto-dismiss after 6s
      setTimeout(() => {
        setErrors(prev => prev.filter(x => x.id !== id));
      }, 6000);
    };
    window.addEventListener('solvit:server-error', handler);
    return () => window.removeEventListener('solvit:server-error', handler);
  }, []);

  if (errors.length === 0) return null;

  return (
    <div data-testid="error-toast-stack" style={{
      position: 'fixed',
      bottom: '20px',
      right: '20px',
      zIndex: 9999,
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      maxWidth: '420px'
    }}>
      {errors.map(err => (
        <div key={err.id} data-testid={`error-toast-${err.id}`} style={{
          backgroundColor: '#FEE2E2',
          border: '1px solid #FCA5A5',
          color: '#991B1B',
          padding: '12px 16px',
          fontFamily: 'Arial, Helvetica, sans-serif',
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          animation: 'slideInRight 0.3s ease'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#7F1D1D', marginBottom: '4px' }}>
                Server Error · {err.status || 500}
              </div>
              <div style={{ fontSize: '12px', lineHeight: 1.4, color: '#991B1B' }}>{err.message || 'An unexpected error occurred'}</div>
              {err.url && <div style={{ fontSize: '10px', color: '#B91C1C', marginTop: '4px', fontFamily: 'monospace', opacity: 0.7 }}>{err.url.length > 60 ? '...' + err.url.slice(-60) : err.url}</div>}
            </div>
            <button onClick={() => setErrors(prev => prev.filter(x => x.id !== err.id))} style={{ background: 'none', border: 'none', color: '#991B1B', cursor: 'pointer', fontSize: '18px', lineHeight: 1, padding: 0 }}>×</button>
          </div>
        </div>
      ))}
    </div>
  );
}
