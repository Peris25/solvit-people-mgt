import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../services/api';

const inputStyle = { width: '100%', boxSizing: 'border-box', padding: '12px', margin: '6px 0 18px', border: '1px solid #aaa', fontSize: '14px' };
const buttonStyle = { width: '100%', padding: '12px', background: '#FF353F', color: '#fff', border: 0, fontWeight: 700, cursor: 'pointer' };
function RecoveryPage({ title, children }) {
  return <main style={{ minHeight: '100vh', display: 'flex', justifyContent: 'center', alignItems: 'center', background: '#F5F5F5', fontFamily: 'Arial, Helvetica, sans-serif', padding: '20px', boxSizing: 'border-box' }}>
    <section style={{ width: '100%', maxWidth: '440px', background: '#fff', padding: '28px', border: '1px solid #ddd' }}>
      <img src="/solvit-logo.png" alt="Solvit" style={{ width: '120px', marginBottom: '20px' }} />
      <h1 style={{ fontSize: '26px', marginTop: 0 }}>{title}</h1>{children}
      <p style={{ marginBottom: 0 }}><Link to="/login">Back to sign in</Link></p>
    </section>
  </main>;
}
const safeError = (error, fallback) => typeof error.response?.data?.detail === 'string' ? error.response.data.detail : fallback;

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await api.forgotPassword(email);
      if (!response.data?.message || response._serverError) throw new Error('Unavailable');
      setSent(true);
    } catch { setError('Could not request a reset link. Please retry or contact IT.'); }
    finally { setBusy(false); }
  };
  return <RecoveryPage title="Forgot password?">
    {sent ? <p role="status">If an eligible account exists, a reset link will be sent to your work email. The link expires in 15 minutes. If it does not arrive, check junk mail or contact IT.</p> : <>
      <p>Enter the email you use to sign in. We will send a password reset link if your account is eligible.</p>
      <form onSubmit={submit}>
        <label htmlFor="recovery-email">Work email</label>
        <input id="recovery-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} style={inputStyle} disabled={busy} />
        {error && <p role="alert">{error}</p>}
        <button disabled={busy} type="submit" style={buttonStyle}>{busy ? 'Requesting...' : 'Send reset link'}</button>
      </form>
    </>}
  </RecoveryPage>;
}

export function ResetPassword() {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { window.history.replaceState(null, '', window.location.pathname); }, []);
  const submit = async event => {
    event.preventDefault(); setError('');
    if (password !== confirmation) { setError('The passwords do not match.'); return; }
    setBusy(true);
    try {
      const response = await api.resetPassword(token, password);
      if (!response.data?.message || response._serverError) throw new Error('Unavailable');
      setDone(true); setToken('');
    } catch (failure) { setError(safeError(failure, 'Could not reset your password. Retry or request a new link.')); }
    finally { setBusy(false); setPassword(''); setConfirmation(''); }
  };
  return <RecoveryPage title="Choose a new password">
    {done ? <p role="status">Password updated. Sign in again using your new password. Previous sessions have ended.</p> : !token ? <p role="alert">This reset link is missing or invalid. <Link to="/forgot-password">Request a new link</Link>.</p> : <>
      <p>Use at least 12 characters and choose a password you have not used before. This does not change your account permissions or MFA requirements.</p>
      <form onSubmit={submit}>
        <label htmlFor="recovery-password">New password</label>
        <input id="recovery-password" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={password} onChange={event => setPassword(event.target.value)} style={inputStyle} disabled={busy} />
        <label htmlFor="recovery-confirmation">Confirm new password</label>
        <input id="recovery-confirmation" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={confirmation} onChange={event => setConfirmation(event.target.value)} style={inputStyle} disabled={busy} />
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy} style={buttonStyle}>{busy ? 'Updating...' : 'Reset password'}</button>
      </form>
    </>}
  </RecoveryPage>;
}
