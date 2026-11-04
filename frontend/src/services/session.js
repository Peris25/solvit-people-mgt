import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;
let refreshing = null;

export function expireSession() {
  localStorage.removeItem('solvit_auth');
  window.dispatchEvent(new CustomEvent('solvit:session-expired'));
}

export function refreshSession() {
  if (!refreshing) {
    const rotate = () => {
      if (!localStorage.getItem('solvit_auth')) throw Object.assign(new Error('Signed out'), { response: { status: 401 } });
      return axios.post(`${API}/api/auth/refresh`, {}, { withCredentials: true });
    };
    // Serialize cookie rotation across tabs as well as concurrent API calls.
    const locks = typeof navigator !== 'undefined' ? navigator.locks : null;
    refreshing = Promise.resolve().then(() => locks?.request ? locks.request('solvit-session-refresh', rotate) : rotate())
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function sessionRequest(send) {
  const attempt = async () => {
    const response = await send();
    if (response?.status === 401) throw Object.assign(new Error('Session expired'), { response });
    return response;
  };
  try { return await attempt(); }
  catch (error) {
    if (error?.response?.status !== 401 || !localStorage.getItem('solvit_auth')) throw error;
    try { await refreshSession(); }
    catch (failure) {
      if ([401, 403].includes(failure?.response?.status)) expireSession();
      throw failure;
    }
    try {
      if (!localStorage.getItem('solvit_auth')) throw error;
      return await attempt();
    }
    catch (failure) {
      if (failure?.response?.status === 401) expireSession();
      throw failure;
    }
  }
}
