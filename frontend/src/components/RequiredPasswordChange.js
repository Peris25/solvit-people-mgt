import PasswordInput from './PasswordInput';
import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function RequiredPasswordChange({ required = true }) {
  const { changePassword, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async event => {
    event.preventDefault();
    setError('');
    if (newPassword !== confirmation) {
      setError('New passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await changePassword(currentPassword, newPassword);
    } catch (failure) {
      const detail = failure?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || 'Unable to change your password. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = { display: 'block', width: '100%', padding: '10px', margin: '8px 0 16px', border: '1px solid #D4D4D4' };
  return (
    <main style={{ minHeight: required ? '100vh' : undefined, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#F5F5F5', padding: '24px', fontFamily: 'Nunito Sans, sans-serif' }}>
      <section style={{ width: '100%', maxWidth: '420px', padding: '32px', backgroundColor: '#fff' }}>
        <h1 style={{ fontSize: '22px', marginBottom: '16px' }}>Change your password</h1>
        <p>{required ? 'Set a new password before accessing the People System.' : 'Use your current password to choose a new password.'} You will need to sign in again after saving.</p>
        <form onSubmit={submit}>
          <label htmlFor="required-current-password">Current password</label>
          <PasswordInput id="required-current-password" type="password" autoComplete="current-password" required value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} style={inputStyle} />
          <label htmlFor="required-new-password">New password</label>
          <PasswordInput id="required-new-password" type="password" autoComplete="new-password" required minLength={12} value={newPassword} onChange={event => setNewPassword(event.target.value)} style={inputStyle} />
          <label htmlFor="required-confirm-password">Confirm new password</label>
          <PasswordInput id="required-confirm-password" type="password" autoComplete="new-password" required value={confirmation} onChange={event => setConfirmation(event.target.value)} style={inputStyle} />
          <p>Use at least 12 characters and a password you have not used before.</p>
          {error && <p role="alert" style={{ color: '#B91C1C' }}>{error}</p>}
          <button type="submit" disabled={busy} style={{ padding: '10px 16px', backgroundColor: '#FF353F', color: '#fff', border: 0 }}>{busy ? 'Saving...' : 'Save password'}</button>
          <button type="button" disabled={busy} onClick={logout} style={{ padding: '10px 16px', marginLeft: '12px' }}>Sign out</button>
        </form>
      </section>
    </main>
  );
}
