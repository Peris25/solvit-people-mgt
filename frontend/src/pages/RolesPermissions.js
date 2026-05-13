/**
 * RolesPermissions — IT Admin only.
 *
 *  Tab 1 (Matrix): click any cell to edit its level/scope. Reset returns it
 *                  to the seed default. Save persists an override that takes
 *                  effect immediately platform-wide.
 *  Tab 2 (Users):  list every platform user and change their primary role
 *                  (system roles + any IT-Admin-created custom roles).
 *  Tab 3 (Custom Roles): create new roles that inherit from a base role. Any
 *                  per-cell overrides for the role are applied via Tab 1.
 */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
import {
  Shield, Users as UsersIcon, RefreshCw, Plus, Trash2, X, Save, Undo2, KeyRound,
} from 'lucide-react';

const LEVEL_COLORS = {
  Full: { bg: '#FEE2E2', fg: '#7F1D1D', label: 'FULL' },
  Manage: { bg: '#FEF3C7', fg: '#92400E', label: 'MANAGE' },
  Read: { bg: '#DBEAFE', fg: '#1E3A8A', label: 'READ' },
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
  const [editCell, setEditCell] = useState(null);          // { module_id, role }
  const [showRoleModal, setShowRoleModal] = useState(false);

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

  const toast = (msg, ok = true) => {
    setFlash((ok ? '✓ ' : '✗ ') + msg);
    setTimeout(() => setFlash(''), 4500);
  };

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
    try { await api.updateUserRole(u.id, newRole); toast(`${u.full_name} → ${newRole}`); load(); }
    catch (e) { toast(e.response?.data?.detail || 'Update failed', false); }
    finally { setSaving(''); }
  };

  const saveCell = async (module_id, role, level, scope) => {
    setSaving(`${module_id}:${role}`);
    try {
      await api.updateMatrixCell(module_id, role, level, scope || null);
      toast(`${module_id} × ${role} = ${level || 'No access'}`);
      setEditCell(null);
      load();
    } catch (e) { toast(e.response?.data?.detail || 'Save failed', false); }
    finally { setSaving(''); }
  };

  const resetCell = async (module_id, role) => {
    if (!window.confirm(`Reset ${module_id} × ${role} to the seed default?`)) return;
    setSaving(`${module_id}:${role}`);
    try {
      await api.resetMatrixCell(module_id, role);
      toast(`${module_id} × ${role} reset to default`);
      setEditCell(null);
      load();
    } catch (e) { toast(e.response?.data?.detail || 'Reset failed', false); }
    finally { setSaving(''); }
  };

  const deleteRole = async (key) => {
    if (!window.confirm(`Delete custom role "${key}"?\nAny users assigned this role will be moved to "employee".`)) return;
    setSaving(key);
    try { await api.deleteCustomRole(key); toast(`Role "${key}" deleted`); load(); }
    catch (e) { toast(e.response?.data?.detail || 'Delete failed', false); }
    finally { setSaving(''); }
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
        display: 'inline-flex', alignItems: 'center', gap: '8px',
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
            Click any matrix cell to edit. Changes take effect immediately and are audited.
          </p>
        </div>
        <button data-testid="roles-refresh" onClick={load} style={btnSecondary}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {flash && (
        <div data-testid="roles-flash" style={{ padding: '8px 14px', backgroundColor: flash.startsWith('✓') ? '#DCFCE7' : '#FEE2E2', color: flash.startsWith('✓') ? '#166534' : '#7F1D1D', fontSize: '12px', fontWeight: 700, marginBottom: '12px' }}>
          {flash}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        <TabButton id="matrix" label="Access Matrix" Icon={Shield} />
        <TabButton id="users" label="User Assignments" Icon={UsersIcon} />
        <TabButton id="roles" label="Custom Roles" Icon={KeyRound} />
      </div>

      {loading ? <div style={{ padding: '40px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
        tab === 'matrix' ? (
          <MatrixTable matrix={matrix} onEdit={(m, r) => setEditCell({ module_id: m, role: r })} saving={saving} />
        ) : tab === 'users' ? (
          <UsersTable users={users} matrix={matrix} onChange={changeRole} saving={saving} />
        ) : (
          <CustomRoles matrix={matrix} onDelete={deleteRole} onNew={() => setShowRoleModal(true)} saving={saving} />
        )
      )}

      {editCell && matrix && (
        <CellEditor
          matrix={matrix}
          cell={editCell}
          onClose={() => setEditCell(null)}
          onSave={saveCell}
          onReset={resetCell}
        />
      )}

      {showRoleModal && matrix && (
        <NewRoleModal
          matrix={matrix}
          onClose={() => setShowRoleModal(false)}
          onCreated={() => { setShowRoleModal(false); load(); toast('Custom role created'); }}
          onError={(msg) => toast(msg, false)}
        />
      )}
    </div>
  );
}

function MatrixTable({ matrix, onEdit, saving }) {
  if (!matrix) return null;
  const modules = Object.keys(matrix.matrix || {});
  const roles = matrix.roles_order || [];
  return (
    <div data-testid="matrix-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', overflowX: 'auto' }}>
      <div style={panelHeader}>
        <div style={panelTitle}>Module × Role Access</div>
        <div style={panelHint}>
          Click a cell to edit. <strong>Full</strong> = read+write+configure, <strong>Manage</strong> = read+write+approve, <strong>Read</strong> = view only. Scope qualifier shown beneath the level chip.
        </div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
        <thead>
          <tr style={{ backgroundColor: '#FAFAFA' }}>
            <th style={th}>Module</th>
            {roles.map(r => (
              <th key={r} style={th} data-testid={`matrix-col-${r}`}>
                {matrix.role_labels?.[r] || r}
                {!matrix.system_roles?.includes(r) && (
                  <div style={{ fontSize: '8px', color: '#FF353F', marginTop: '2px' }}>CUSTOM</div>
                )}
              </th>
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
                const isSaving = saving === `${mod}:${r}`;
                return (
                  <td key={r} style={{ ...td, textAlign: 'center', cursor: 'pointer' }}
                    data-testid={`matrix-cell-${mod}-${r}`}
                    onClick={() => onEdit(mod, r)}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = '#FEF2F2'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = ''}
                    title="Click to edit">
                    <span style={{ display: 'inline-block', padding: '2px 8px', backgroundColor: color.bg, color: color.fg, fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', opacity: isSaving ? 0.5 : 1 }}>
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

function CellEditor({ matrix, cell, onClose, onSave, onReset }) {
  const { module_id, role } = cell;
  const existing = matrix.matrix[module_id]?.[role];
  const [level, setLevel] = useState(existing?.level || '');
  const [scope, setScope] = useState(existing?.scope || '');
  const levels = ['', ...(matrix.valid_levels || ['Full', 'Manage', 'Read'])];

  return (
    <div data-testid="cell-editor" style={modalOverlay}>
      <div style={{ ...modalBox, maxWidth: '460px' }}>
        <div style={modalHeader}>
          <div>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', fontWeight: 700, fontFamily: 'Barlow' }}>Edit access</div>
            <div style={{ fontSize: '18px', fontWeight: 900, marginTop: '4px', fontFamily: 'Barlow', letterSpacing: '-0.02em' }}>
              {module_id} · {matrix.role_labels?.[role] || role}
            </div>
            <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px' }}>{matrix.module_labels?.[module_id]}</div>
          </div>
          <button data-testid="cell-editor-close" onClick={onClose} style={iconBtn}><X size={16} /></button>
        </div>

        <div style={{ padding: '18px' }}>
          <label style={lbl}>Level</label>
          <select data-testid="cell-level-select" value={level} onChange={e => setLevel(e.target.value)} style={inp}>
            {levels.map(l => <option key={l} value={l}>{l || 'No access'}</option>)}
          </select>

          <label style={{ ...lbl, marginTop: '14px' }}>Scope qualifier (optional)</label>
          <input data-testid="cell-scope-input" type="text" value={scope} onChange={e => setScope(e.target.value)}
            placeholder="e.g. own_record, own_team, statutory_only"
            style={inp} />
          <div style={{ fontSize: '10px', color: '#525252', marginTop: '6px', fontStyle: 'italic' }}>
            Common scopes: own_record · own_team · own_reports · own_dept_pipeline · aggregate · salary_band · statutory_only
          </div>
        </div>

        <div style={modalFooter}>
          <button data-testid="cell-reset" onClick={() => onReset(module_id, role)} style={btnGhost}>
            <Undo2 size={12} /> Reset to default
          </button>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={onClose} style={btnSecondary}>Cancel</button>
            <button data-testid="cell-save" onClick={() => onSave(module_id, role, level || null, scope)} style={btnPrimary}>
              <Save size={12} /> Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UsersTable({ users, matrix, onChange, saving }) {
  const roles = matrix?.roles_order || [];
  return (
    <div data-testid="users-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={panelHeader}>
        <div style={panelTitle}>User Role Assignments</div>
        <div style={panelHint}>Changes take effect on the user's next request and are written to the audit log.</div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead><tr style={{ backgroundColor: '#FAFAFA' }}>
          {['Name', 'Email', 'Department', 'Current Role', 'Change To'].map(h => <th key={h} style={th}>{h}</th>)}
        </tr></thead>
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
                <select data-testid={`role-select-${u.id}`} disabled={saving === u.id} value={u.role}
                  onChange={(e) => onChange(u, e.target.value)}
                  style={{ padding: '6px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', fontFamily: 'Nunito Sans' }}>
                  {roles.map(r => <option key={r} value={r}>{matrix?.role_labels?.[r] || r}</option>)}
                </select>
                {saving === u.id && <span style={{ marginLeft: '8px', fontSize: '10px', color: '#525252' }}>Saving…</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CustomRoles({ matrix, onDelete, onNew, saving }) {
  const list = matrix?.custom_roles || [];
  return (
    <div data-testid="custom-roles-tab" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
      <div style={{ ...panelHeader, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={panelTitle}>Custom Roles</div>
          <div style={panelHint}>Create roles that inherit from a base role. Override individual cells via the Access Matrix tab.</div>
        </div>
        <button data-testid="new-role-btn" onClick={onNew} style={btnPrimary}><Plus size={12} /> New Role</button>
      </div>
      {list.length === 0 ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>
          No custom roles yet. Click <strong>New Role</strong> to define one.
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead><tr style={{ backgroundColor: '#FAFAFA' }}>
            {['Key', 'Label', 'Inherits From', 'Description', ''].map(h => <th key={h} style={th}>{h}</th>)}
          </tr></thead>
          <tbody>
            {list.map(r => (
              <tr key={r.key} data-testid={`custom-role-${r.key}`} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)' }}>
                <td style={{ ...td, fontWeight: 700, fontFamily: 'monospace', color: '#191919' }}>{r.key}</td>
                <td style={td}>{r.label}</td>
                <td style={td}>
                  <span style={{ fontSize: '10px', padding: '2px 8px', backgroundColor: '#F5F5F5', color: '#525252', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    {matrix.role_labels?.[r.inherits_from] || r.inherits_from}
                  </span>
                </td>
                <td style={{ ...td, color: '#525252' }}>{r.description || '—'}</td>
                <td style={{ ...td, textAlign: 'right' }}>
                  <button data-testid={`delete-role-${r.key}`} disabled={saving === r.key} onClick={() => onDelete(r.key)} style={{ ...btnGhost, color: '#FF353F' }}>
                    <Trash2 size={12} /> Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NewRoleModal({ matrix, onClose, onCreated, onError }) {
  const [key, setKey] = useState('');
  const [label, setLabel] = useState('');
  const [description, setDescription] = useState('');
  const [inherits, setInherits] = useState('employee');
  const [busy, setBusy] = useState(false);
  const systemRoles = matrix.system_roles || ['hr_admin', 'hr_manager', 'line_manager', 'finance', 'employee', 'solver', 'executive'];

  const submit = async () => {
    if (!key || !label) return onError('Key and Label are required');
    setBusy(true);
    try { await api.createCustomRole({ key, label, description, inherits_from: inherits }); onCreated(); }
    catch (e) { onError(e.response?.data?.detail || 'Create failed'); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="new-role-modal" style={modalOverlay}>
      <div style={modalBox}>
        <div style={modalHeader}>
          <div style={{ fontSize: '18px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.02em' }}>Create Custom Role</div>
          <button onClick={onClose} style={iconBtn}><X size={16} /></button>
        </div>
        <div style={{ padding: '18px', display: 'grid', gap: '12px' }}>
          <div>
            <label style={lbl}>Role Key (lowercase, underscores)</label>
            <input data-testid="new-role-key" type="text" value={key} onChange={e => setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
              placeholder="e.g. ops_lead" style={inp} />
          </div>
          <div>
            <label style={lbl}>Display Label</label>
            <input data-testid="new-role-label" type="text" value={label} onChange={e => setLabel(e.target.value)}
              placeholder="e.g. Operations Lead" style={inp} />
          </div>
          <div>
            <label style={lbl}>Inherits Permissions From</label>
            <select data-testid="new-role-inherits" value={inherits} onChange={e => setInherits(e.target.value)} style={inp}>
              {systemRoles.map(r => <option key={r} value={r}>{matrix.role_labels?.[r] || r}</option>)}
            </select>
          </div>
          <div>
            <label style={lbl}>Description (optional)</label>
            <textarea data-testid="new-role-desc" value={description} onChange={e => setDescription(e.target.value)} rows={3}
              placeholder="What this role does on the platform"
              style={{ ...inp, resize: 'vertical', fontFamily: 'Nunito Sans' }} />
          </div>
        </div>
        <div style={modalFooter}>
          <button onClick={onClose} style={btnSecondary}>Cancel</button>
          <button data-testid="new-role-create" disabled={busy} onClick={submit} style={btnPrimary}>
            <Plus size={12} /> {busy ? 'Creating…' : 'Create Role'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- inline style tokens (kept colocated for component-scoped clarity) ----------
const th = { padding: '10px 14px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', borderBottom: '1px solid rgba(25,25,25,0.08)', fontFamily: 'Barlow' };
const td = { padding: '10px 14px', verticalAlign: 'top' };
const lbl = { display: 'block', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box', outline: 'none', fontFamily: 'Nunito Sans' };
const panelHeader = { padding: '14px 18px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5' };
const panelTitle = { fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', fontFamily: 'Barlow' };
const panelHint = { fontSize: '11px', color: '#525252', marginTop: '4px' };
const btnPrimary = { padding: '8px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '6px' };
const btnSecondary = { padding: '8px 14px', backgroundColor: 'transparent', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '6px' };
const btnGhost = { padding: '6px 10px', backgroundColor: 'transparent', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '6px' };
const iconBtn = { padding: '4px', backgroundColor: 'transparent', border: 'none', cursor: 'pointer', color: '#525252' };
const modalOverlay = { position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 };
const modalBox = { backgroundColor: '#fff', minWidth: '420px', maxWidth: '520px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' };
const modalHeader = { padding: '18px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' };
const modalFooter = { padding: '14px 18px', borderTop: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#FAFAFA', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' };
