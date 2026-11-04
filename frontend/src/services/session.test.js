import axios from 'axios';
import { refreshSession, sessionRequest } from './session';
jest.mock('axios');
beforeEach(() => { localStorage.clear(); localStorage.setItem('solvit_auth', '1'); jest.clearAllMocks(); });
const denied = { response: { status: 401 } };

test('concurrent failures share one refresh and retry each original request once', async () => {
  let finish;
  let began;
  const started = new Promise(resolve => { began = resolve; });
  axios.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; began(); }));
  const first = jest.fn().mockRejectedValueOnce(denied).mockResolvedValueOnce({ data: 'first' });
  const second = jest.fn().mockRejectedValueOnce(denied).mockResolvedValueOnce({ data: 'second' });
  const a = sessionRequest(first); const b = sessionRequest(second);
  await started;
  expect(axios.post).toHaveBeenCalledTimes(1);
  finish({ status: 200 });
  expect(await a).toEqual({ data: 'first' }); expect(await b).toEqual({ data: 'second' });
  expect(first).toHaveBeenCalledTimes(2); expect(second).toHaveBeenCalledTimes(2);
  expect(localStorage.getItem('solvit_auth')).toBe('1');
});
test('revoked refresh ends the session without an infinite retry', async () => {
  axios.post.mockRejectedValueOnce(denied);
  const send = jest.fn().mockRejectedValue(denied);
  await expect(sessionRequest(send)).rejects.toBe(denied);
  expect(send).toHaveBeenCalledTimes(1); expect(localStorage.getItem('solvit_auth')).toBeNull();
});
test('refresh outages preserve sign-in and do not replay the operation', async () => {
  const outage = { response: { status: 503 } };
  axios.post.mockRejectedValueOnce(outage);
  const send = jest.fn().mockRejectedValue(denied);
  await expect(sessionRequest(send)).rejects.toBe(outage);
  expect(send).toHaveBeenCalledTimes(1); expect(localStorage.getItem('solvit_auth')).toBe('1');
});
test('permission or MFA denial on retry does not sign the user out', async () => {
  axios.post.mockResolvedValueOnce({ status: 200 });
  const forbidden = { response: { status: 403 } };
  const send = jest.fn().mockRejectedValueOnce(denied).mockRejectedValueOnce(forbidden);
  await expect(sessionRequest(send)).rejects.toBe(forbidden);
  expect(localStorage.getItem('solvit_auth')).toBe('1');
});
test('cross-tab cookie rotation uses the browser lock when supported', async () => {
  const request = jest.fn((name, callback) => callback());
  Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } });
  axios.post.mockResolvedValueOnce({ status: 200 });
  try { await refreshSession(); expect(request).toHaveBeenCalledWith('solvit-session-refresh', expect.any(Function)); }
  finally { delete navigator.locks; }
});

test('signing out during refresh prevents replay of the protected operation', async () => {
  axios.post.mockImplementationOnce(async () => { localStorage.removeItem('solvit_auth'); return { status: 200 }; });
  const send = jest.fn().mockRejectedValue(denied);
  await expect(sessionRequest(send)).rejects.toBe(denied);
  expect(send).toHaveBeenCalledTimes(1);
});
