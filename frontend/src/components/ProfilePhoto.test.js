import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ProfilePhoto from './ProfilePhoto';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  api.getMyProfilePhoto.mockRejectedValue({ response: { status: 404 } });
  URL.createObjectURL = jest.fn(() => 'blob:private-photo'); URL.revokeObjectURL = jest.fn();
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<ProfilePhoto initials="MP" />)); };
const choose = async file => { const input = container.querySelector('input[type="file"]'); Object.defineProperty(input, 'files', { configurable: true, value: [file] }); await act(async () => input.dispatchEvent(new Event('change', { bubbles: true }))); };
test('requires consent and uploads own photo, then displays the protected image', async () => {
  await render(); expect(container.textContent).toContain('MP');
  expect(container.querySelector('input[type="file"]').disabled).toBe(true);
  await act(async () => container.querySelector('input[type="checkbox"]').click());
  api.uploadMyProfilePhoto.mockResolvedValue({ data: { id: 'photo' } });
  api.getMyProfilePhoto.mockResolvedValue({ data: new Blob(['photo']) });
  const file = new File(['photo'], 'photo.png', { type: 'image/png' }); await choose(file);
  expect(api.uploadMyProfilePhoto).toHaveBeenCalledWith(file, true);
  expect(container.querySelector('img').src).toContain('blob:private-photo');
  expect(container.textContent).toContain('Profile photo updated.');
});
test('invalid files are rejected without upload', async () => {
  await render(); await act(async () => container.querySelector('input[type="checkbox"]').click());
  await choose(new File(['pdf'], 'file.pdf', { type: 'application/pdf' }));
  expect(api.uploadMyProfilePhoto).not.toHaveBeenCalled(); expect(container.textContent).toContain('Choose a JPG or PNG');
});
test('scanner failure is shown without claiming success', async () => {
  await render(); await act(async () => container.querySelector('input[type="checkbox"]').click());
  api.uploadMyProfilePhoto.mockRejectedValue({ response: { data: { detail: 'Document scanning is unavailable; upload was not saved' } } });
  await choose(new File(['photo'], 'photo.png', { type: 'image/png' }));
  expect(container.textContent).toContain('Document scanning is unavailable');
  expect(container.querySelector('img')).toBeNull();
});

test('soft server errors cannot be mistaken for an uploaded photo', async () => {
  await render(); await act(async () => container.querySelector('input[type="checkbox"]').click());
  api.uploadMyProfilePhoto.mockResolvedValue({ data: null, status: 503, _serverError: true });
  await choose(new File(['photo'], 'photo.png', { type: 'image/png' }));
  expect(container.textContent).toContain('Photo upload failed');
  expect(container.textContent).not.toContain('Profile photo updated');
});
