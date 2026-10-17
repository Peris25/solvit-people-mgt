import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import { AuthProvider, useAuth } from './AuthContext';

jest.mock('axios');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, auth;
function Probe() {
  auth = useAuth();
  return <div>{auth.user ? String(auth.user.must_change_password) : 'signed-out'}</div>;
}
beforeEach(() => {
  localStorage.clear();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('successful change clears the session hint and requires a new sign in', async () => {
  axios.post.mockResolvedValueOnce({ data: { id: 'synthetic', must_change_password: true } });
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  await act(async () => auth.login('staff@example.com', 'Original-local-test-password-2026'));
  expect(auth.user.must_change_password).toBe(true);
  axios.post.mockResolvedValueOnce({ data: { message: 'Password updated' } });
  await act(async () => auth.changePassword('Original-local-test-password-2026', 'Updated-local-test-password-2026'));
  expect(axios.post).toHaveBeenLastCalledWith(expect.stringContaining('/api/auth/password/change'), {
    current_password: 'Original-local-test-password-2026', new_password: 'Updated-local-test-password-2026',
  }, { withCredentials: true });
  expect(auth.user).toBeNull();
  expect(localStorage.getItem('solvit_auth')).toBeNull();
});

test('failed password changes retain restricted authentication', async () => {
  localStorage.setItem('solvit_auth', '1');
  axios.get.mockResolvedValue({ status: 200, data: { id: 'synthetic', must_change_password: true } });
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  axios.post.mockRejectedValueOnce(new Error('synthetic policy rejection'));
  await act(async () => {
    await expect(auth.changePassword('local-current', 'local-new')).rejects.toThrow('synthetic policy rejection');
  });
  expect(auth.user.must_change_password).toBe(true);
  expect(localStorage.getItem('solvit_auth')).toBe('1');
});

test('a server requirement event gates a previously normal session', async () => {
  localStorage.setItem('solvit_auth', '1');
  axios.get.mockResolvedValue({ status: 200, data: { id: 'synthetic', must_change_password: false } });
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  await act(async () => window.dispatchEvent(new CustomEvent('solvit:password-change-required')));
  expect(auth.user.must_change_password).toBe(true);
  expect(axios.get).toHaveBeenCalledTimes(1);
});


test('MFA verification upgrades identity but enrollment confirmation keeps one-time recovery display pending', async () => {
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  axios.post.mockResolvedValueOnce({data:{id:'synthetic',mfa_required:true,mfa_verified:false}});
  await act(async () => auth.login('staff@example.com','local-password'));
  axios.post.mockResolvedValueOnce({data:{user:{id:'synthetic',mfa_verified:true},recovery_codes:['SYNTHETIC']}});
  let output; await act(async () => { output = await auth.confirmMfa('123456'); });
  expect(output.recovery_codes).toEqual(['SYNTHETIC']); expect(auth.user.mfa_verified).toBe(false);
  axios.post.mockResolvedValueOnce({data:{id:'synthetic',mfa_required:true,mfa_verified:true}});
  await act(async () => auth.verifyMfa('SYNTHETIC-RECOVERY',true));
  expect(auth.user.mfa_verified).toBe(true);
  expect(axios.post).toHaveBeenLastCalledWith(expect.stringContaining('/auth/mfa/verify'),{recovery_code:'SYNTHETIC-RECOVERY'},{withCredentials:true});
});

test('a server MFA requirement event removes previously verified UI access', async () => {
  localStorage.setItem('solvit_auth','1'); axios.get.mockResolvedValue({status:200,data:{id:'synthetic',mfa_verified:true}});
  await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
  await act(async () => window.dispatchEvent(new CustomEvent('solvit:mfa-required',{detail:{action:'enroll'}})));
  expect(auth.user.mfa_required).toBe(true); expect(auth.user.mfa_verified).toBe(false); expect(auth.user.mfa_action).toBe('enroll');
});
