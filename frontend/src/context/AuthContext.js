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
    window.addEventListener('solvit:password-change-required', requirePasswordChange);
    return () => window.removeEventListener('solvit:password-change-required', requirePasswordChange);
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

  return (
    <AuthContext.Provider value={{ user, login, logout, checkAuth, changePassword }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
