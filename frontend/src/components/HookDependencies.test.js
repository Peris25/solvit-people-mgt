import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Calendar from '../pages/Calendar';
import EmailDelivery from './EmailDelivery';
import AIAgent from './AIAgent';
import * as api from '../services/api';

let mockUser = { full_name: 'Synthetic User' };
jest.mock('../services/api');
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock('../context/ThemeContext', () => ({ useTheme: () => ({ theme: 'light' }), themeTokens: () => ({}) }));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => {
  mockUser = { full_name: 'Synthetic User' };
  Element.prototype.scrollIntoView = jest.fn();
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.clearAllMocks(); });

test('calendar fetches once per selected window without a render/refetch loop', async () => {
  api.getCalendarEvents.mockResolvedValue({ data: [] });
  await act(async () => root.render(<Calendar />));
  expect(api.getCalendarEvents).toHaveBeenCalledTimes(1);
  expect(api.getCalendarEvents).toHaveBeenLastCalledWith(90);
  await act(async () => container.querySelector('[data-testid="days-30"]').click());
  expect(api.getCalendarEvents).toHaveBeenCalledTimes(2);
  expect(api.getCalendarEvents).toHaveBeenLastCalledWith(30);
  await act(async () => root.render(<Calendar />));
  expect(api.getCalendarEvents).toHaveBeenCalledTimes(2);
});

test('email log filters do not refetch settings or erase unsaved edits', async () => {
  api.getEmailDelivery.mockResolvedValue({ data: { can_edit: true, testing: { smtp_host: 'original.local' }, production: {} } });
  api.getEmailDeliveryAudit.mockResolvedValue({ data: [] });
  api.getEmailLog.mockResolvedValue({ data: [] });
  await act(async () => root.render(<EmailDelivery />));
  const input = container.querySelector('[data-testid="testing-smtp_host"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'draft.local');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => container.querySelector('[data-testid="log-filter-failed"]').click());
  expect(api.getEmailDelivery).toHaveBeenCalledTimes(1);
  expect(api.getEmailLog).toHaveBeenLastCalledWith('failed');
  expect(input.value).toBe('draft.local');
});

test('AI greeting initializes once; manual refresh uses the latest user name', async () => {
  api.getAiSnapshot.mockResolvedValue({ data: { headcount: { total_active_fte: 0, by_department: {} }, leave: {}, performance: {}, recruitment: {}, solvers: {}, recognition: {}, onboarding: {} } });
  await act(async () => root.render(<AIAgent />));
  expect(api.getAiSnapshot).toHaveBeenCalledTimes(1);
  mockUser = { full_name: 'Updated User' };
  await act(async () => root.render(<AIAgent />));
  expect(api.getAiSnapshot).toHaveBeenCalledTimes(1);
  await act(async () => container.querySelector('[data-testid="ai-refresh"]').click());
  expect(api.getAiSnapshot).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('Updated');
});
