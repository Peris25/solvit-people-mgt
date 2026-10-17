import axios from 'axios';
import './api';

jest.mock('axios', () => ({
  create: jest.fn(() => ({ interceptors: { response: { use: jest.fn() } } })),
}));

const reject = axios.create.mock.results[0].value.interceptors.response.use.mock.calls[0][1];

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
