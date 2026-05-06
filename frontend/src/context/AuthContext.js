import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
const AUTH_HINT = 'solvit_auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading, null = not auth'd, obj = auth'd

  useEffect(() => {
    // Only probe /auth/me if we have a previous-session hint, otherwise treat as logged-out immediately
    if (typeof window !== 'undefined' && localStorage.getItem(AUTH_HINT)) {
      checkAuth();
    } else {
      setUser(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkAuth = async () => {
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
  };

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

  return (
    <AuthContext.Provider value={{ user, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
