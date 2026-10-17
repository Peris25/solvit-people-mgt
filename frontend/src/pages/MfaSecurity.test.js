import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import MfaSecurity from './MfaSecurity';
import { useAuth } from '../context/AuthContext';
jest.mock('../context/AuthContext');
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root, auth;
const status = extra => ({configured: true, mfa_enrolled: false, mfa_verified: false, recovery_codes_remaining: 0, ...extra});
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  auth = {user: {id: 'privileged-account', role: 'hr_admin', mfa_required: true, mfa_verified: false}, logout: jest.fn(), checkAuth: jest.fn().mockResolvedValue(), getMfaStatus: jest.fn().mockResolvedValue(status()), startMfa: jest.fn(), confirmMfa: jest.fn(), verifyMfa: jest.fn().mockResolvedValue(), rotateRecoveryCodes: jest.fn(), resetMfa: jest.fn()};
  useAuth.mockImplementation(() => auth);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async (required = true) => { await act(async () => root.render(<MfaSecurity required={required} />)); };
const input = async (id, value) => { await act(async () => { const node = container.querySelector('#'+id); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(node,value); node.dispatchEvent(new Event('input',{bubbles:true})); }); };
const submit = async () => { await act(async () => container.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))); };
const click = async text => { const button = [...container.querySelectorAll('button')].find(node => node.textContent === text); expect(button).toBeTruthy(); await act(async () => button.click()); };

test('enrollment shows setup key only after password proof, then retains recovery screen until saved', async () => {
  auth.startMfa.mockResolvedValue({secret:'SYNTHETICSETUPKEY'}); auth.confirmMfa.mockResolvedValue({user:{id:'privileged-account',mfa_verified:true},recovery_codes:['RECOVERY-ONE','RECOVERY-TWO']});
  await render(); expect(container.textContent).not.toContain('SYNTHETICSETUPKEY'); await input('mfa-password','local-password'); await submit();
  expect(auth.startMfa).toHaveBeenCalledWith('local-password'); expect(container.textContent).toContain('SYNTHETICSETUPKEY');
  await input('mfa-code','123456'); await submit(); expect(auth.confirmMfa).toHaveBeenCalledWith('123456');
  expect(container.textContent).toContain('RECOVERY-ONE'); expect(container.textContent).not.toContain('SYNTHETICSETUPKEY'); expect(auth.checkAuth).not.toHaveBeenCalled();
  await click('I have saved my codes'); expect(auth.checkAuth).toHaveBeenCalled(); expect(container.textContent).not.toContain('RECOVERY-ONE');
});

test('verification supports authenticator and one-use recovery without exposing passwords', async () => {
  auth.getMfaStatus.mockResolvedValue(status({mfa_enrolled:true})); await render(); await input('mfa-code','654321'); await submit(); expect(auth.verifyMfa).toHaveBeenCalledWith('654321',false);
  await click('Use a recovery code'); await input('mfa-code','SYNTHETIC-RECOVERY'); await submit(); expect(auth.verifyMfa).toHaveBeenLastCalledWith('SYNTHETIC-RECOVERY',true);
  expect(container.querySelector('#mfa-password')).toBeNull(); expect(auth.checkAuth).toHaveBeenCalled();
});

test('missing server configuration gives support guidance and no enroll action', async () => {
  auth.getMfaStatus.mockResolvedValue(status({configured:false})); await render();
  expect(container.textContent).toContain('awaiting IT configuration'); expect(container.querySelector('form button')).toBeNull();
});

test('failed proof displays server-safe guidance and retains the MFA gate', async () => {
  auth.getMfaStatus.mockResolvedValue(status({mfa_enrolled:true})); auth.verifyMfa.mockRejectedValue({response:{data:{detail:'Too many MFA attempts. Wait 15 minutes and try again'}}});
  await render(); await input('mfa-code','000000'); await submit();
  expect(container.querySelector('[role="alert"]').textContent).toContain('Wait 15 minutes'); expect(auth.checkAuth).not.toHaveBeenCalled(); expect(container.querySelector('#mfa-code').value).toBe('');
});

test('account switch removes pending setup and never publishes a stale status', async () => {
  let old; auth.getMfaStatus.mockImplementationOnce(() => new Promise(resolve => { old=resolve; })); await render();
  auth={...auth,user:{id:'other-account',role:'employee'}}; await render(false); await act(async()=>old(status({mfa_enrolled:true})));
  expect(container.textContent).not.toContain('Authenticator enabled.'); expect(container.textContent).toContain('Authenticator not yet enrolled.');
});

test('only verified IT accounts see assisted recovery administration', async () => {
  auth.user={id:'it',role:'it_admin'}; auth.getMfaStatus.mockResolvedValue(status({mfa_enrolled:true,mfa_verified:true,can_reset_other:true})); await render(false);
  expect(container.textContent).toContain('IT assisted recovery'); await input('mfa-target','synthetic-account-id'); await input('mfa-reference','APPROVED-TICKET'); await input('mfa-admin-password','local-password');
  const forms=container.querySelectorAll('form'); await act(async()=>forms[1].dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(auth.resetMfa).toHaveBeenCalledWith('synthetic-account-id','local-password','APPROVED-TICKET');
});

test('setup and recovery secrets are never saved in browser storage', async () => {
  localStorage.clear(); sessionStorage.clear(); auth.startMfa.mockResolvedValue({secret:'SECRET-SETUP'}); await render(); await input('mfa-password','local-password'); await submit();
  expect(JSON.stringify(localStorage)).not.toContain('SECRET'); expect(JSON.stringify(sessionStorage)).not.toContain('SECRET');
});
