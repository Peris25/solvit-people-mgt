/**
 * RolesPermissions — IT Admin only.
 *
 * Tab 1 (Matrix): read-only 19 × 9 access matrix showing what every role can
 *                 do in every module. Sourced from /api/access/matrix.
 * Tab 2 (User Assignments): list every platform user and allow IT Admin to
 *                 change the user's primary role (audited via /api/access/users).
 */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
import { Shield, Users as UsersIcon, RefreshCw } from 'lucide-react';

const LEVEL_COLORS = {
  Full:   { bg: '#FEE2E2', fg: '#7F1D1D', label: 'FULL' },
  Manage: { bg: '#FEF3C7', fg: '#92400E', label: 'MANAGE' },
  Read:   { bg: '#DBEAFE', fg: '#1E3A8A', label: 'READ' },
};
const NO_ACCESS = { bg: '#F5F5F5', fg: '#9CA3AF', label: '—' };

export default function RolesPermissions() {
  const { user } = useAuth();
  const [tab, setTab] = useState('matrix');
  const [matrix, setMatrix] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState('');
  const [flash, setFlash] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [m, u] = await Promise.all([
        api.getAccessMatrix(),
        api.listUsersWithRoles().catch(() => ({ data: [] })),
      ]);
      setMatrix(m.data);
      setUsers(u.data || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  if (user?.role !== 'it_admin') {
    return (
      <div data-testid="roles-not-allowed" style={{ padding: '40px', textAlign: 'center', backgroundColor: '#FEE2E2', border: '1px solid #FF353F', color: '#7F1D1D' }}>
        <strong>IT Admin only.</strong> Ask your IT administrator to grant access.
      </div>
    );
  }

  const changeRole = async (u, newRole) => {
    if (u.role === newRole) return;
    if (!window.confirm(`Change role for ${u.full_name} (${u.email}) from "${u.role}" to "${newRole}"?\nThis is audited and effective immediately.`)) return;
    setSaving(u.id);
    try {
      await api.updateUserRole(u.id, newRole);
      setFlash(`✓ ${u.full_name} → ${newRole}`);
      load();
    } catch (e) {
      setFlash(`✗ ${e.response?.data?.detail || 'Update failed'}`);
    } finally {
      setSaving('');
      setTimeout(() => setFlash(''), 5000);
    }
  };

  const TabButton = ({ id, label, Icon }) => (
    <button
      data-testid={`roles-tab-${id}`}
      onClick={() => setTab(id)}
      style={{
        padding: '10px 18px', backgroundColor: 'transparent', border: 'none',
        borderBottom: tab === id ? '2px solid #FF353F' : '2px solid transparent',
        marginBottom: '-2px', cursor: 'pointer', fontSize: '12px',
        fontWeight: tab === id ? 700 : 500, color: tab === id ? '#FF353F' : '#525252',
        fontFamily: 'Barlow, sans-serif', textTransform: 'uppercase', letterSpacing: '0.1em',
        display: 'inline-flex', alignItems: 'center', gap: '8px'
      }}>
      <Icon size={14} />{label}
    </button>
  );

  return (
    <div data-testid="roles-permissions-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '30px', fontWeight: 900, letterSpacing: '-0.04em', color: '#191919', margin: 0, fontFamily: 'Barlow' }}>
            Roles & Permissions
          </h1>
          <p style={{ color: '#525252', fontSize: '12px', margin: '4px 0 0' }}>
            Access matrix (read-only) and user role assignments — IT Admin
          </p>
        </div>
        <button data-testid="roles-refresh" onClick={load} style={{ padding: '8px 14px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {flash && (
        <div data-testid="roles-flash" style={{ padding: '8px 14px', backgroundColor: flash.startsWith('✓') ? '#DCFCE7' : '#FEE2E2', color: flash.startsWith('✓') ? '#166534' : '#7F1D1D', fontSize: '12px', fontWeight: 700, marginBottom: '12px' }}>
          {flash}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        <TabButton id="matrix" label="Access Matrix" Icon={Shield} />
        <TabButton id="users" label="User Assignments" Icon={UsersIcon} />
      </div>

      {loading ? <div style={{ padding: '40px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
        tab === 'matrix' ? <MatrixTable matrix={matrix} /> : <UsersTable users={users} matrix={matrix} onChange={changeRole} saving={saving} />
      )}
    </div>
  );
}

function MatrixTable({ matrix }) {
  if (!matrix) return null;
  const modules = Object.keys(matrix.matrix || {});
  const roles = (matrix.roles_order || []).filter(r => Object.values(matrix.matrix).some(m => r in m));
  return (
    <div data-testid="matrix-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', fontFamily: 'Barlow' }}>Module × Role Access</div>
        <div style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>
          Levels: <strong>Full</strong> (read + write + configure), <strong>Manage</strong> (read + write + approve), <strong>Read</strong> (view only). Scope qualifiers shown beneath.
        </div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
        <thead>
          <tr style={{ backgroundColor: '#FAFAFA' }}>
            <th style={th}>Module</th>
            {roles.map(r => (
              <th key={r} style={th} data-testid={`matrix-col-${r}`}>{matrix.role_labels?.[r] || r}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {modules.map(mod => (
            <tr key={mod} data-testid={`matrix-row-${mod}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
              <td style={{ ...td, fontWeight: 700, color: '#191919' }}>
                <div>{mod}</div>
                <div style={{ fontSize: '10px', color: '#525252', fontWeight: 400 }}>{matrix.module_labels?.[mod]}</div>
              </td>
              {roles.map(r => {
                const cell = matrix.matrix[mod]?.[r];
                const color = cell ? (LEVEL_COLORS[cell.level] || NO_ACCESS) : NO_ACCESS;
                return (
                  <td key={r} style={{ ...td, textAlign: 'center' }} data-testid={`matrix-cell-${mod}-${r}`}>
                    <span style={{ display: 'inline-block', padding: '2px 8px', backgroundColor: color.bg, color: color.fg, fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em' }}>
                      {color.label}
                    </span>
                    {cell?.scope && <div style={{ fontSize: '9px', color: '#525252', marginTop: '2px', fontStyle: 'italic' }}>:{cell.scope}</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: '14px 18px', borderTop: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#FAFAFA' }}>
        <div style={{ fontSize: '11px', fontWeight: 700, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '6px', fontFamily: 'Barlow' }}>
          Destructive Actions (HR Admin only)
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {(matrix.destructive_actions || []).map(a => (
            <span key={a} style={{ fontSize: '10px', padding: '3px 8px', backgroundColor: '#FEE2E2', color: '#7F1D1D', fontWeight: 700, letterSpacing: '0.05em' }}>{a}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function UsersTable({ users, matrix, onChange, saving }) {
  const roles = matrix?.roles_order || [];
  return (
    <div data-testid="users-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', fontFamily: 'Barlow' }}>
          User Role Assignments
        </div>
        <div style={{ fontSize: '11px', color: '#525252', marginTop: '4px' }}>
          Changing a user's role takes effect immediately on their next request. All changes are written to the audit log.
        </div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr style={{ backgroundColor: '#FAFAFA' }}>
            {['Name', 'Email', 'Department', 'Current Role', 'Change To'].map(h => (
              <th key={h} style={th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.map((u, i) => (
            <tr key={u.id} data-testid={`user-row-${u.id}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
              <td style={{ ...td, fontWeight: 700, color: '#191919' }}>{u.full_name}</td>
              <td style={td}>{u.email}</td>
              <td style={{ ...td, color: '#525252' }}>{u.department || '—'}</td>
              <td style={td}>
                <span style={{ fontSize: '10px', padding: '2px 8px', backgroundColor: '#191919', color: '#fff', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  {matrix?.role_labels?.[u.role] || u.role}
                </span>
              </td>
              <td style={td}>
                <select
                  data-testid={`role-select-${u.id}`}
                  disabled={saving === u.id}
                  value={u.role}
                  onChange={(e) => onChange(u, e.target.value)}
                  style={{ padding: '6px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', fontFamily: 'Nunito Sans' }}>
                  {roles.map(r => <option key={r} value={r}>{matrix?.role_labels?.[r] || r}</option>)}
                </select>
                {saving === u.id && <span style={{ marginLeft: '8px', fontSize: '10px', color: '#525252' }}>Saving…</span>}
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr><td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No users found.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const th = { padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Barlow' };
const td = { padding: '10px 14px', verticalAlign: 'top' };
