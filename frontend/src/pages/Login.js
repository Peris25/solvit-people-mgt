import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

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
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map(d => d.msg).join(' ') : (detail || 'Login failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F5F5F5', display: 'flex', fontFamily: 'Arial, Helvetica, sans-serif' }}>
      {/* Left — brand panel */}
      <div style={{ flex: 1, background: '#191919', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '48px', minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
        <div style={{ backgroundImage: 'url(https://solvit.co.ke/wp-content/uploads/2024/03/Client-Meet.webp)', backgroundSize: 'cover', backgroundPosition: 'center', position: 'absolute', inset: 0, opacity: 0.35 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(25,25,25,0.85) 0%, rgba(25,25,25,0.55) 100%)' }} />
        <div style={{ position: 'relative', zIndex: 1 }}>
          <img src="https://www.solvit.limited/dist/images/logo.png" alt="Solvit" style={{ height: '44px', width: 'auto', display: 'block', filter: 'brightness(0) invert(1)' }} />
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
              <div key={stat.label}>
                <div style={{ color: '#FF353F', fontSize: '24px', fontWeight: 900, letterSpacing: '-0.05em' }}>{stat.value}</div>
                <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em' }}>{stat.label}</div>
              </div>
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
              placeholder="you@solvit.co.ke"
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
          <p style={{ fontSize: '12px', color: '#525252', textAlign: 'center', margin: 0 }}>
            Need access? Contact your IT Administrator.
          </p>
        </div>
      </div>
    </div>
  );
}
