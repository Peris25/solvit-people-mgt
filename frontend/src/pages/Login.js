import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const DEMO_USERS = [
  { label: 'HR Admin (Jessica)', email: 'jessica@solvit.co.ke', role: 'hr_admin', color: '#FF353F' },
  { label: 'Line Manager', email: 'manager@solvit.co.ke', role: 'line_manager', color: '#191919' },
  { label: 'Finance', email: 'finance@solvit.co.ke', role: 'finance', color: '#525252' },
  { label: 'Employee', email: 'employee@solvit.co.ke', role: 'employee', color: '#3B82F6' },
  { label: 'Solver', email: 'solver@solvit.co.ke', role: 'solver', color: '#22C55E' },
  { label: 'MD / Executive', email: 'md@solvit.co.ke', role: 'executive', color: '#8B5CF6' },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) { setError('Please enter email and password'); return; }
    setLoading(true); setError('');
    try {
      const user = await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map(d => d.msg).join(' ') : (detail || 'Login failed'));
    } finally {
      setLoading(false);
    }
  };

  const demoLogin = async (demoUser) => {
    setLoading(true); setError('');
    try {
      await login(demoUser.email, 'Solvit@2026');
      navigate('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map(d => d.msg).join(' ') : (detail || 'Demo login failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F5F5F5', display: 'flex', fontFamily: 'Arial, Helvetica, sans-serif' }}>
      {/* Left — brand panel */}
      <div style={{ flex: 1, background: '#191919', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '48px', minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
        <div style={{ backgroundImage: 'url(https://images.unsplash.com/photo-1762912297981-ee1a51f4f187?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85)', backgroundSize: 'cover', backgroundPosition: 'center', position: 'absolute', inset: 0, opacity: 0.25 }} />
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ width: '40px', height: '40px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '20px' }}>S</span>
            </div>
            <span style={{ color: '#fff', fontWeight: 900, fontSize: '20px', letterSpacing: '-0.05em' }}>SOLVIT</span>
          </div>
        </div>
        <div style={{ position: 'relative', zIndex: 1 }}>
          <h1 style={{ color: '#fff', fontSize: '42px', fontWeight: 900, lineHeight: 1.1, letterSpacing: '-0.05em', margin: 0, marginBottom: '16px' }}>
            People<br />Management<br />Platform
          </h1>
          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '14px', fontWeight: 400, margin: 0 }}>
            Solvit Limited — Kenya's Technology-Enabled Vehicle Inspection Company
          </p>
        </div>
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
            {[{ label: 'Employees', value: '10+' }, { label: 'Solvers', value: '3+' }, { label: 'Modules', value: '19' }].map(stat => (
              <div key={stat.label}>
                <div style={{ color: '#FF353F', fontSize: '24px', fontWeight: 900, letterSpacing: '-0.05em' }}>{stat.value}</div>
                <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right — login form */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '48px', maxWidth: '560px' }}>
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '28px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0, marginBottom: '4px' }}>Sign in</h2>
          <p style={{ color: '#525252', fontSize: '14px', margin: 0 }}>Access the Solvit People Platform</p>
        </div>

        <form onSubmit={handleLogin} style={{ marginBottom: '32px' }}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px' }}>Email Address</label>
            <input
              data-testid="login-email"
              type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="jessica@solvit.co.ke"
              style={{ width: '100%', padding: '10px 12px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: '#fff', fontSize: '14px', outline: 'none', boxSizing: 'border-box', fontFamily: 'Arial' }}
            />
          </div>
          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px' }}>Password</label>
            <input
              data-testid="login-password"
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              style={{ width: '100%', padding: '10px 12px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: '#fff', fontSize: '14px', outline: 'none', boxSizing: 'border-box', fontFamily: 'Arial' }}
            />
          </div>
          {error && <div data-testid="login-error" style={{ color: '#FF353F', fontSize: '13px', marginBottom: '16px', padding: '8px 12px', border: '1px solid #FF353F', backgroundColor: 'rgba(255,53,63,0.05)' }}>{error}</div>}
          <button
            data-testid="login-submit"
            type="submit" disabled={loading}
            style={{ width: '100%', padding: '12px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1, fontFamily: 'Arial', transition: 'opacity 0.2s' }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ flex: 1, height: '1px', backgroundColor: 'rgba(25,25,25,0.1)' }} />
            <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252' }}>Quick Demo Login</span>
            <div style={{ flex: 1, height: '1px', backgroundColor: 'rgba(25,25,25,0.1)' }} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
            {DEMO_USERS.map(u => (
              <button
                key={u.email}
                data-testid={`demo-login-${u.role}`}
                onClick={() => demoLogin(u)}
                disabled={loading}
                style={{
                  padding: '10px 12px', border: `1px solid ${u.color}`, backgroundColor: 'transparent',
                  cursor: 'pointer', textAlign: 'left', transition: 'background-color 0.2s', fontFamily: 'Arial',
                  opacity: loading ? 0.5 : 1
                }}
                onMouseEnter={e => e.currentTarget.style.backgroundColor = `${u.color}10`}
                onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <div style={{ fontSize: '11px', fontWeight: 700, color: u.color, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{u.label}</div>
                <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px' }}>{u.email}</div>
              </button>
            ))}
          </div>
          <p style={{ fontSize: '11px', color: '#525252', marginTop: '12px', textAlign: 'center' }}>All demo accounts use password: <strong>Solvit@2026</strong></p>
        </div>
      </div>
    </div>
  );
}
