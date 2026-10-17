import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
const AUTH_HINT = 'solvit_auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = not auth'd, obj = auth'd

  const checkAuth = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/auth/me`, {
        withCredentials: true,
        validateStatus: (s) => s < 500
      });
      if (res.status === 200) {
        setUser(res.data);
      } else {
        localStorage.removeItem(AUTH_HINT);
        setUser(null);
      }
    } catch {
      localStorage.removeItem(AUTH_HINT);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem(AUTH_HINT)) {
      checkAuth();
    } else {
      setUser(null);
    }
  }, [checkAuth]);

  useEffect(() => {
    const requirePasswordChange = () => setUser(current => current ? { ...current, must_change_password: true } : current);
    const requireMfa = event => setUser(current => current ? { ...current, mfa_required: true, mfa_verified: false, mfa_action: event.detail?.action || 'verify' } : current);
    window.addEventListener('solvit:mfa-required', requireMfa);
    window.addEventListener('solvit:password-change-required', requirePasswordChange);
    return () => { window.removeEventListener('solvit:password-change-required', requirePasswordChange); window.removeEventListener('solvit:mfa-required', requireMfa); };
  }, []);

  const login = async (email, password) => {
    const res = await axios.post(
      `${API}/api/auth/login`,
      { email, password },
      { withCredentials: true }
    );
    localStorage.setItem(AUTH_HINT, '1');
    setUser(res.data);
    return res.data;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/api/auth/logout`, {}, { withCredentials: true });
    } catch { /* ignore */ }
    localStorage.removeItem(AUTH_HINT);
    setUser(null);
  };

  const changePassword = async (currentPassword, newPassword) => {
    const res = await axios.post(`${API}/api/auth/password/change`, {
      current_password: currentPassword,
      new_password: newPassword,
    }, { withCredentials: true });
    // The backend invalidates all pre-change sessions. Sign in again with the
    // new credential instead of treating this restricted session as upgraded.
    localStorage.removeItem(AUTH_HINT);
    setUser(null);
    return res.data;
  };

  const mfaCall = useCallback(async (path, body) => (await axios.post(`${API}/api/auth/mfa/${path}`, body, { withCredentials: true })).data, []);
  const getMfaStatus = useCallback(async () => (await axios.get(`${API}/api/auth/mfa/status`, { withCredentials: true })).data, []);
  const startMfa = password => mfaCall('enroll', { password });
  // Keep the recovery-code screen mounted until the user saves its one-time output.
  const confirmMfa = code => mfaCall('confirm', { code });
  const verifyMfa = async (value, recovery = false) => {
    const data = await mfaCall('verify', recovery ? { recovery_code: value } : { code: value });
    setUser(data);
    return data;
  };
  const rotateRecoveryCodes = password => mfaCall('recovery-codes', { password });
  const resetMfa = (accountId, password, reference) => mfaCall(`reset/${encodeURIComponent(accountId)}`, { password, reference });

  return (
    <AuthContext.Provider value={{ user, login, logout, checkAuth, changePassword, getMfaStatus, startMfa, confirmMfa, verifyMfa, rotateRecoveryCodes, resetMfa }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
