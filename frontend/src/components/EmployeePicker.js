/**
 * EmployeePicker — shared searchable dropdown for selecting an employee.
 * Use anywhere an employee must be picked. NEVER allow free-text typing of an employee name.
 *
 * Props:
 *  - value: employee_id (string) currently selected
 *  - onChange: ({ id, full_name, role_title, department }) => void
 *  - excludeId: optional employee_id to filter out (e.g. self for handover contact)
 *  - placeholder: text when nothing selected
 *  - testId: data-testid override
 *  - required: bool — adds visual marker
 *  - disabled: bool
 */
import React, { useState, useEffect, useRef } from 'react';
import * as api from '../services/api';

export default function EmployeePicker({ value, onChange, excludeId, placeholder = 'Select an employee...', testId = 'employee-picker', required, disabled }) {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    let cancelled = false;
    api.getEmployees().then(r => {
      if (!cancelled) {
        setEmployees((r.data || []).filter(e => e.lifecycle_state !== 'Exited'));
        setLoading(false);
      }
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selected = employees.find(e => e.id === value);
  const filtered = employees
    .filter(e => !excludeId || e.id !== excludeId)
    .filter(e => {
      if (!search) return true;
      const s = search.toLowerCase();
      return [e.full_name, e.role_title, e.department, e.work_email].some(x => (x || '').toLowerCase().includes(s));
    })
    .slice(0, 50);

  return (
    <div ref={ref} data-testid={testId} style={{ position: 'relative', fontFamily: 'Arial' }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)',
          backgroundColor: disabled ? '#F5F5F5' : '#fff', textAlign: 'left',
          fontSize: '13px', cursor: disabled ? 'not-allowed' : 'pointer', boxSizing: 'border-box',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px',
        }}
      >
        <span style={{ color: selected ? '#191919' : '#9CA3AF', fontWeight: selected ? 600 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selected ? `${selected.full_name} · ${selected.role_title || ''}` : (loading ? 'Loading employees...' : placeholder)}
          {required && !selected && <span style={{ color: '#FF353F' }}> *</span>}
        </span>
        <span style={{ color: '#9CA3AF' }}>▾</span>
      </button>

      {open && !disabled && (
        <div data-testid={`${testId}-dropdown`} style={{
          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px',
          backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.15)', boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          zIndex: 200, maxHeight: '320px', display: 'flex', flexDirection: 'column'
        }}>
          <input
            data-testid={`${testId}-search`}
            type="text"
            autoFocus
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Type to filter…"
            style={{ padding: '8px 10px', border: 'none', borderBottom: '1px solid rgba(25,25,25,0.1)', fontSize: '12px', outline: 'none', fontFamily: 'Arial' }}
          />
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.length === 0 ? (
              <div style={{ padding: '14px', textAlign: 'center', color: '#9CA3AF', fontSize: '12px' }}>No matches</div>
            ) : filtered.map(e => (
              <button
                key={e.id}
                type="button"
                data-testid={`${testId}-option-${e.id}`}
                onClick={() => { onChange(e); setOpen(false); setSearch(''); }}
                style={{
                  display: 'block', width: '100%', padding: '8px 10px',
                  background: e.id === value ? '#FEF2F2' : 'transparent',
                  border: 'none', textAlign: 'left', cursor: 'pointer', borderBottom: '1px solid rgba(25,25,25,0.05)',
                  fontFamily: 'Arial'
                }}
                onMouseEnter={ev => ev.currentTarget.style.backgroundColor = '#F5F5F5'}
                onMouseLeave={ev => ev.currentTarget.style.backgroundColor = e.id === value ? '#FEF2F2' : 'transparent'}
              >
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#191919' }}>{e.full_name}</div>
                <div style={{ fontSize: '11px', color: '#525252' }}>{e.role_title} · {e.department}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
