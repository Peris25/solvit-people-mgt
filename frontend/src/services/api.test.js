import axios from 'axios';
import './api';

jest.mock('axios', () => ({
  post: jest.fn(),
  create: jest.fn(() => ({ request: jest.fn(), interceptors: { response: { use: jest.fn() } } })),
}));

const reject = axios.create.mock.results[0].value.interceptors.response.use.mock.calls[0][1];
const client = axios.create.mock.results[0].value;

test('protected API requests renew expired access and replay once with original config', async () => {
  localStorage.setItem('solvit_auth', '1');
  axios.post.mockResolvedValueOnce({ status: 200 });
  client.request.mockResolvedValueOnce({ data: 'saved' });
  const config = { url: '/leave', method: 'get' };
  expect(await reject({ config, response: { status: 401 } })).toEqual({ data: 'saved' });
  expect(client.request).toHaveBeenCalledWith({ ...config, _sessionRetry: true });
  expect(localStorage.getItem('solvit_auth')).toBe('1');
  localStorage.clear();
});

test('invalid login does not renew or end another valid session', async () => {
  localStorage.setItem('solvit_auth', '1');
  const failure = { config: { url: '/auth/login' }, response: { status: 401 } };
  const count = axios.post.mock.calls.length;
  await expect(reject(failure)).rejects.toBe(failure);
  expect(axios.post.mock.calls.length).toBe(count);
  expect(localStorage.getItem('solvit_auth')).toBe('1');
  localStorage.clear();
});

test('password-required responses notify authentication state and keep the error rejected', async () => {
  const dispatch = jest.spyOn(window, 'dispatchEvent');
  const error = { response: { status: 403, data: { detail: { code: 'password_change_required' } } } };
  try {
    await expect(reject(error)).rejects.toBe(error);
    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch.mock.calls[0][0].type).toBe('solvit:password-change-required');
  } finally {
    dispatch.mockRestore();
  }
});

test('ordinary permission errors do not force a password change', async () => {
  const dispatch = jest.spyOn(window, 'dispatchEvent');
  const error = { response: { status: 403, data: { detail: 'Insufficient permissions' } } };
  try {
    await expect(reject(error)).rejects.toBe(error);
    expect(dispatch).not.toHaveBeenCalled();
  } finally {
    dispatch.mockRestore();
  }
});


test('MFA-required responses gate the current UI without treating verification as complete', async () => {
  const dispatch = jest.spyOn(window,'dispatchEvent');
  const detail = {code:'mfa_required',action:'enroll'};
  const error = {response:{status:403,data:{detail}}};
  try {
    await expect(reject(error)).rejects.toBe(error);
    expect(dispatch.mock.calls[0][0].type).toBe('solvit:mfa-required');
    expect(dispatch.mock.calls[0][0].detail).toEqual(detail);
  } finally { dispatch.mockRestore(); }
});


test('blocked mutation reports the required next step while preserving rejection for local handling',async()=>{
 const dispatch=jest.spyOn(window,'dispatchEvent');
 const error={config:{url:'/leave/decision',method:'put'},response:{status:409,data:{detail:'Enter an approval reason first.'}}};
 try{await expect(reject(error)).rejects.toBe(error);expect(dispatch.mock.calls[0][0].detail.message).toBe('Enter an approval reason first.');}finally{dispatch.mockRestore();}
});
test('uncertain server failure never exposes internal diagnostics as an action message',async()=>{
 const dispatch=jest.spyOn(window,'dispatchEvent');
 const error={config:{url:'/private/save',method:'post'},response:{status:500,data:{detail:'PRIVATE_DATABASE_TRACE'}}};
 try{const result=await reject(error);expect(result.status).toBe(500);expect(dispatch.mock.calls[0][0].detail.message).toContain('could not be confirmed');expect(dispatch.mock.calls[0][0].detail.message).not.toContain('PRIVATE');}finally{dispatch.mockRestore();}
});
