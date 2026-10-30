import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

global.IS_REACT_ACT_ENVIRONMENT = true;
let container, root;
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
afterEach(() => { act(() => root.unmount()); container.remove(); });
const render = element => act(() => root.render(element));
const screen = {
  getByLabelText: name => container.querySelector(`[aria-label="${name}"]`),
  getAllByRole: (role, { name }) => [...container.querySelectorAll('button')].filter(button => button.getAttribute('aria-label') === name),
  getByRole: (role, { name }) => container.querySelector(`button[aria-label="${name}"]`),
  queryByRole: () => container.querySelector('button'),
};
const fireEvent = { click: element => act(() => element.click()) };

import PasswordInput from './PasswordInput';

test('password starts hidden and can be revealed and hidden without changing its value or submitting', () => {
  const submit = jest.fn(event => event.preventDefault());
  render(<form onSubmit={submit}><PasswordInput aria-label="Password" defaultValue="Synthetic-test-value" autoComplete="new-password" required minLength={12} /></form>);
  const input = screen.getByLabelText('Password');
  expect(input.type).toBe('password');
  fireEvent.click(screen.getByRole('button', { name: 'Show password' }));
  expect(input.type).toBe('text');
  expect(input.value).toBe('Synthetic-test-value');
  expect(input.autocomplete).toBe('new-password');
  expect(input.required).toBe(true);
  expect(input.minLength).toBe(12);
  fireEvent.click(screen.getByRole('button', { name: 'Hide password' }));
  expect(input.type).toBe('password');
  expect(submit).not.toHaveBeenCalled();
});

test('each field has an independent toggle and disabled fields cannot be revealed', () => {
  render(<><PasswordInput aria-label="First" /><PasswordInput aria-label="Second" disabled /></>);
  fireEvent.click(screen.getAllByRole('button', { name: 'Show password' })[0]);
  expect(screen.getByLabelText('First').type).toBe('text');
  expect(screen.getByLabelText('Second').type).toBe('password');
  expect(screen.getByRole('button', { name: 'Show password' }).disabled).toBe(true);
});

test('dynamic non-password settings remain ordinary inputs', () => {
  render(<PasswordInput aria-label="Port" type="number" />);
  expect(screen.getByLabelText('Port').type).toBe('number');
  expect(screen.queryByRole('button')).toBeNull();
});
