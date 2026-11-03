import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RolesPermissions from './RolesPermissions';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
jest.mock('../context/AuthContext');
jest.mock('../services/api');
jest.mock('../components/EmployeeAccountForm', () => () => null);
jest.mock('../components/EmployeeLoginReview', () => () => null);
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container=document.createElement('div'); document.body.appendChild(container); root=createRoot(container);
  api.getAccessMatrix.mockResolvedValue({data:{roles_order:['it_admin','employee','line_manager','general_manager'],assignable_roles:['employee','line_manager','general_manager'],role_labels:{},matrix:{}}});
  api.listUsersWithRoles.mockResolvedValue({data:[{id:'staff',full_name:'Synthetic Staff',role:'employee',can_assign_role:true}]});
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.resetAllMocks(); });
test('HR opens business assignments directly without matrix or custom-role controls', async () => {
  useAuth.mockReturnValue({user:{id:'hr',role:'hr_admin'}});
  await act(async () => root.render(<RolesPermissions />));
  expect(container.querySelector('[data-testid="users-tab"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="roles-tab-matrix"]')).toBeNull();
  expect(container.querySelector('[data-testid="roles-tab-roles"]')).toBeNull();
  const select=container.querySelector('select');
  expect([...select.options].map(o => o.value)).toEqual(['employee','line_manager','general_manager']);
});
test('ordinary employee cannot load administrative account data', async () => {
  useAuth.mockReturnValue({user:{id:'staff',role:'employee'}});
  await act(async () => root.render(<RolesPermissions />));
  expect(api.listUsersWithRoles).not.toHaveBeenCalled();
  expect(api.getAccessMatrix).not.toHaveBeenCalled();
});
