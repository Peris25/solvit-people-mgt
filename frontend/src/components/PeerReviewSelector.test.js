import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PeerReviewSelector from './PeerReviewSelector';
import * as api from '../services/api';
jest.mock('../services/api');
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
const task = (id, name, can_submit = true) => ({ id, employee_name: name, role_title: 'Synthetic role', department: 'Synthetic department', status: 'Assigned', due_on: '2099-11-07', can_submit });
const data = peers => ({ data: { peers, peer_questions: ['Integrity', 'Ownership', 'Teamwork', 'Solutions', 'Timeliness'] } });
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); api.getPerformanceV3Tasks.mockResolvedValue(data([task('one', 'First colleague'), task('two', 'Second colleague'), task('closed', 'Expired colleague', false)])); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
const render = async () => { await act(async () => root.render(<PeerReviewSelector />)); };
const change = async (element, value) => { await act(async () => { Object.getOwnPropertyDescriptor(element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLSelectElement.prototype, 'value').set.call(element, value); element.dispatchEvent(new Event('change', { bubbles: true })); element.dispatchEvent(new Event('input', { bubbles: true })); }); };

test('colleague dropdown shows only eligible assigned colleagues', async () => {
  await render(); const select = container.querySelector('[aria-label="Colleague to review"]');
  expect(select.textContent).toContain('First colleague'); expect(select.textContent).toContain('Second colleague');
  expect(select.textContent).not.toContain('Expired colleague'); expect(container.querySelectorAll('[aria-label^="Peer value"]')).toHaveLength(0);
});

test('submits selected task using V3 scale and removes it after success', async () => {
  api.performanceV3Action.mockResolvedValue({ data: { status: 'Submitted' } }); await render();
  await change(container.querySelector('[aria-label="Colleague to review"]'), 'two');
  for (const select of container.querySelectorAll('[aria-label^="Peer value"]')) await change(select, '8');
  const selects = [...container.querySelectorAll('select')]; await change(selects[selects.length - 1], '10');
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(api.performanceV3Action).toHaveBeenCalledWith('peers', 'two', 'submit', { scores: [8, 8, 8, 8, 8], retain: 10, relationship: 'Peer', comment: '' });
  expect(api.submitForm).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Second colleague submitted successfully');
  expect([...container.querySelector('[aria-label="Colleague to review"]').options].some(o => o.value === 'two')).toBe(false);
});

test('changing colleague clears unsaved ratings to prevent accidental attribution', async () => {
  await render(); const select = container.querySelector('[aria-label="Colleague to review"]');
  await change(select, 'one'); await change(container.querySelector('[aria-label="Peer value 1"]'), '9');
  await change(select, 'two'); expect(container.querySelector('[aria-label="Peer value 1"]').value).toBe('');
});

test('empty and failed loading states are explicit', async () => {
  api.getPerformanceV3Tasks.mockResolvedValue(data([])); await render(); expect(container.textContent).toContain('No peer reviews are currently open');
  await act(async () => root.unmount()); root = createRoot(container); api.getPerformanceV3Tasks.mockRejectedValue(new Error('Unavailable')); await render();
  expect(container.querySelector('[role="alert"]').textContent).toContain('Unable to load eligible colleagues');
});
