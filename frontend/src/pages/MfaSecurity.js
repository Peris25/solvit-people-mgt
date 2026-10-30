import PasswordInput from '../components/PasswordInput';
import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function MfaSecurity({ required = false }) {
  const { user, logout, checkAuth, getMfaStatus, startMfa, confirmMfa, verifyMfa, rotateRecoveryCodes, resetMfa } = useAuth();
  const [status, setStatus] = useState(null);
  const [setup, setSetup] = useState(null);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [recovery, setRecovery] = useState(false);
  const [codes, setCodes] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [target, setTarget] = useState('');
  const [reference, setReference] = useState('');
  const accountId = user?.id;
  useEffect(() => {
    let active = true;
    setStatus(null); setSetup(null); setCodes([]); setPassword(''); setCode(''); setError('');
    getMfaStatus().then(value => { if (active) setStatus(value); }).catch(() => { if (active) setError('Security settings could not be loaded. Sign out and try again or contact IT.'); });
    return () => { active = false; };
    // Context functions change with auth state; the account owns this request.
  }, [accountId, getMfaStatus]);

  const run = async action => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); }
    catch (failure) {
      const detail = failure?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || 'Security verification could not be completed. Please try again.');
    } finally { setBusy(false); setPassword(''); setCode(''); }
  };
  const submitCode = event => {
    event.preventDefault();
    run(async () => {
      if (setup) { const result = await confirmMfa(code); setSetup(null); setCodes(result.recovery_codes); }
      else { await verifyMfa(code, recovery); await checkAuth(); }
    });
  };
  const input = { width: '100%', padding: '10px', margin: '6px 0 16px', boxSizing: 'border-box', border: '1px solid #D4D4D4' };
  const button = { padding: '10px 16px', background: '#FF353F', color: '#fff', border: 0, cursor: 'pointer', marginRight: '8px', marginBottom: '8px' };
  const needsVerification = status?.mfa_enrolled && required && !setup;
  return <main style={{ minHeight: required ? '100vh' : undefined, padding: '24px', background: '#F5F5F5', fontFamily: 'Arial, sans-serif', display: 'flex', justifyContent: 'center', alignItems: required ? 'center' : 'flex-start' }}>
    <section style={{ background: '#fff', padding: '28px', width: '100%', maxWidth: '560px', boxSizing: 'border-box' }}>
      <h1 style={{ color: '#191919', fontSize: '24px' }}>Account security</h1>
      <p>Use an authenticator app to protect your Solvit People account. Never share your setup key, password or recovery codes.</p>
      {error && <p role="alert" style={{ color: '#B91C1C' }}>{error}</p>}
      {message && <p role="status">{message}</p>}
      {!status && !error && <p>Loading security settings...</p>}
      {codes.length > 0 ? <div>
        <h2>Save your recovery codes</h2>
        <p>Each code works once, after your password. Keep them somewhere private and separate from your phone. They are shown only now; replacing them invalidates the old set.</p>
        <ul aria-label="Recovery codes" style={{ overflowWrap: 'anywhere', paddingLeft: '20px' }}>{codes.map(value => <li key={value}><code>{value}</code></li>)}</ul>
        <button style={button} disabled={busy} onClick={() => run(async () => { await checkAuth(); setCodes([]); setStatus(await getMfaStatus()); })}>I have saved my codes</button>
      </div> : status && <>
        {!setup && !required && <p>{status.mfa_enrolled ? 'Authenticator enabled.' : 'Authenticator not yet enrolled.'} {status.mfa_enrolled && `${status.recovery_codes_remaining} recovery codes remain.`}</p>}
        {setup ? <div>
          <h2>Add Solvit People to your authenticator</h2>
          <p>Choose a manual setup key in your authenticator app. Select time-based codes (6 digits, 30 seconds). This setup expires in 5 minutes.</p>
          <code aria-label="Authenticator setup key" style={{ display: 'block', overflowWrap: 'anywhere', background: '#F5F5F5', padding: '12px' }}>{setup.secret}</code>
        </div> : null}
        {setup || needsVerification ? <form onSubmit={submitCode}>
          <label htmlFor="mfa-code">{recovery && !setup ? 'Recovery code' : 'Authenticator code'}</label>
          <input id="mfa-code" required autoComplete="one-time-code" inputMode={recovery && !setup ? 'text' : 'numeric'} value={code} onChange={event => setCode(event.target.value)} style={input} />
          <button type="submit" style={button} disabled={busy}>{busy ? 'Checking...' : setup ? 'Confirm authenticator' : 'Verify and continue'}</button>
          {!setup && <button type="button" disabled={busy} onClick={() => { setRecovery(value => !value); setCode(''); }}>{recovery ? 'Use authenticator code' : 'Use a recovery code'}</button>}
        </form> : <form onSubmit={event => { event.preventDefault(); run(async () => { setSetup(await startMfa(password)); }); }}>
          {!status.configured ? <p>MFA setup is awaiting IT configuration. Contact IT support before your enrollment deadline.</p> : <>
            {status.mfa_enrolled && <p>To replace your authenticator or recovery codes, sign in with MFA within the last 5 minutes and confirm your password. The old authenticator stays active until the new one is confirmed.</p>}
            <label htmlFor="mfa-password">Current password</label>
            <PasswordInput id="mfa-password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required style={input} />
            <button style={button} disabled={busy} type="submit">{status.mfa_enrolled ? 'Replace authenticator' : 'Set up authenticator'}</button>
            {status.mfa_enrolled && <button type="button" disabled={busy || !password} onClick={() => run(async () => { setCodes((await rotateRecoveryCodes(password)).recovery_codes); })}>Replace recovery codes</button>}
          </>}
        </form>}
        {!required && status.can_reset_other && status.mfa_verified && <details style={{ margin: '24px 0' }}>
          <summary>IT assisted recovery for another account</summary>
          <p>Verify the account holder and obtain an approved support reference first. Use the login account ID from Roles &amp; Permissions. This ends their sessions and requires enrollment again.</p>
          <form onSubmit={event => { event.preventDefault(); run(async () => { await resetMfa(target, password, reference); setTarget(''); setReference(''); setMessage('Reset recorded. The account must sign in and enroll again.'); }); }}>
            <label htmlFor="mfa-target">Login account ID</label><input id="mfa-target" required value={target} onChange={event => setTarget(event.target.value)} style={input} />
            <label htmlFor="mfa-reference">Approved support reference</label><input id="mfa-reference" required minLength={8} maxLength={200} value={reference} onChange={event => setReference(event.target.value)} style={input} />
            <label htmlFor="mfa-admin-password">Your current password</label><PasswordInput id="mfa-admin-password" required type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} style={input} />
            <button disabled={busy} style={button}>Reset this account's MFA</button>
          </form>
        </details>}
      </>}
      <p>Lost access to both your authenticator and recovery codes? Contact IT for identity verification. Support will never ask you to send a code or setup key.</p>
      <button type="button" disabled={busy} onClick={logout}>Sign out</button>
    </section>
  </main>;
}
