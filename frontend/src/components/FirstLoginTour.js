/**
 * FirstLoginTour — full-screen welcome modal + role-specific guided tour.
 * Fires automatically the first time a user logs in (controlled by backend).
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function FirstLoginTour() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({ phase: 'idle', steps: [], idx: 0, headline: '', body_text: '', enabled: true });

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!user) return;
      try {
        const r = await api.getMyTour();
        if (cancelled) return;
        if (r.data?.completed || !r.data?.enabled) return;
        setState({
          phase: 'welcome',
          steps: r.data.steps || [],
          idx: 0,
          headline: r.data.headline || 'Welcome to Solvit People',
          body_text: r.data.body_text || '',
          enabled: r.data.enabled,
        });
      } catch { /* not authed yet — ignore */ }
    };
    load();
    return () => { cancelled = true; };
  }, [user]);

  const finish = async (skipped) => {
    try { await api.completeTour(skipped); } catch { /* ignore */ }
    setState(s => ({ ...s, phase: 'idle' }));
  };

  const next = () => {
    setState(s => {
      const isLast = s.idx >= s.steps.length - 1;
      if (isLast) { finish(false); return { ...s, phase: 'idle' }; }
      return { ...s, idx: s.idx + 1 };
    });
  };
  const prev = () => setState(s => ({ ...s, idx: Math.max(0, s.idx - 1) }));
  const startTour = () => setState(s => ({ ...s, phase: 'tour', idx: 0 }));

  // Navigate as a side-effect when the active tour step changes — avoids
  // setState-in-render warning that surfaces when navigation is invoked
  // directly inside setState callbacks.
  useEffect(() => {
    if (state.phase !== 'tour') return;
    const target = state.steps[state.idx]?.target;
    if (target) navigate(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.idx]);

  if (state.phase === 'idle') return null;

  if (state.phase === 'welcome') {
    return (
      <div data-testid="tour-welcome" style={overlayStyle}>
        <div style={{ width: '520px', backgroundColor: '#fff', textAlign: 'center', padding: '40px 36px', borderTop: '6px solid #FF353F' }}>
          <div data-testid="tour-logo" style={{ width: '64px', height: '64px', backgroundColor: '#FF353F', margin: '0 auto 18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: '#fff', fontWeight: 900, fontSize: '28px', fontFamily: 'Barlow' }}>S</span>
          </div>
          <h2 style={{ margin: 0, fontFamily: 'Barlow', fontWeight: 900, fontSize: '24px', letterSpacing: '-0.03em', color: '#191919' }}>{state.headline}</h2>
          <p style={{ marginTop: '12px', fontSize: '14px', color: '#525252', lineHeight: 1.5 }}>{state.body_text}</p>
          <div style={{ marginTop: '28px', display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <button data-testid="tour-start-btn" onClick={startTour} style={btnRed}>Start Tour</button>
          </div>
          <button data-testid="tour-skip-btn" onClick={() => finish(true)} style={{ marginTop: '14px', background: 'none', border: 'none', color: '#525252', cursor: 'pointer', fontSize: '12px', textDecoration: 'underline', fontFamily: 'Nunito Sans' }}>Skip for now</button>
        </div>
      </div>
    );
  }

  if (state.phase === 'tour') {
    const step = state.steps[state.idx];
    if (!step) return null;
    return (
      <div data-testid="tour-step" style={{ position: 'fixed', bottom: '32px', right: '32px', width: '360px', backgroundColor: '#191919', color: '#fff', zIndex: 9000, borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: '#FF353F', boxShadow: '0 12px 36px rgba(0,0,0,0.4)' }}>
        <div style={{ padding: '18px 22px' }}>
          <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.2em', color: '#FF353F', fontFamily: 'Barlow', fontWeight: 700 }}>Step {state.idx + 1} / {state.steps.length}</div>
          <h4 style={{ margin: '6px 0 8px', fontFamily: 'Barlow', fontWeight: 900, fontSize: '16px', letterSpacing: '-0.02em' }}>{step.title}</h4>
          <p style={{ margin: 0, fontSize: '12px', color: 'rgba(255,255,255,0.75)', lineHeight: 1.5 }}>{step.body}</p>
        </div>
        <div style={{ padding: '12px 22px', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button data-testid="tour-skip-btn" onClick={() => finish(true)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '11px', textDecoration: 'underline', fontFamily: 'Nunito Sans' }}>Skip Tour</button>
          <div style={{ display: 'flex', gap: '8px' }}>
            {state.idx > 0 && <button data-testid="tour-prev-btn" onClick={prev} style={smBtnGhost}>Prev</button>}
            <button data-testid="tour-next-btn" onClick={next} style={smBtnRed}>{state.idx >= state.steps.length - 1 ? 'Done' : 'Next'}</button>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

const overlayStyle = { position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9000, fontFamily: 'Nunito Sans, sans-serif' };
const btnRed = { padding: '12px 28px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' };
const smBtnRed = { padding: '6px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'Barlow' };
const smBtnGhost = { padding: '6px 14px', backgroundColor: 'transparent', color: 'rgba(255,255,255,0.7)', border: '1px solid rgba(255,255,255,0.15)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'Barlow' };
