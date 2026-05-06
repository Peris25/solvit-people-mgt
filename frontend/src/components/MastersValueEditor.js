/**
 * MastersValueEditor — generic JSON value editor for the Masters Settings UI.
 * Handles primitives, primitive arrays, object arrays, and nested objects.
 */
import React from 'react';

export const prettify = (k) => k.split('_').map(w => w[0]?.toUpperCase() + w.slice(1)).join(' ');
const inputStyle = { padding: '6px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', fontFamily: 'Arial', boxSizing: 'border-box', width: '100%' };
const isPrim = (v) => v == null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';

function PrimitiveEditor(props) {
  const { value, onChange, disabled, testId } = props;
  if (typeof value === 'boolean') {
    return React.createElement('label',
      { style: { display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px' } },
      React.createElement('input', { 'data-testid': testId, type: 'checkbox', disabled, checked: value, onChange: (e) => onChange(e.target.checked) }),
      React.createElement('span', null, value ? 'On' : 'Off')
    );
  }
  if (typeof value === 'number') {
    return React.createElement('input', {
      'data-testid': testId, disabled, type: 'number', value,
      onChange: (e) => onChange(e.target.value === '' ? '' : Number(e.target.value)),
      style: Object.assign({}, inputStyle, { width: '180px' })
    });
  }
  const sval = value == null ? '' : value;
  if (typeof value === 'string' && (sval.length > 60 || sval.indexOf('\n') !== -1)) {
    return React.createElement('textarea', {
      'data-testid': testId, disabled, value: sval, rows: 4,
      onChange: (e) => onChange(e.target.value),
      style: Object.assign({}, inputStyle, { width: '100%', fontFamily: 'monospace' })
    });
  }
  return React.createElement('input', {
    'data-testid': testId, disabled, type: 'text', value: sval,
    onChange: (e) => onChange(e.target.value),
    style: Object.assign({}, inputStyle, { width: '320px' })
  });
}

function ArrayOfPrimitivesEditor(props) {
  const { value, onChange, disabled, testId } = props;
  const items = value.map((v, i) => React.createElement('div',
    { key: i, style: { display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#F5F5F5', padding: '4px 6px' } },
    React.createElement('input', {
      disabled, value: v == null ? '' : v,
      onChange: (e) => {
        const nv = value.slice();
        nv[i] = typeof v === 'number' ? Number(e.target.value) : e.target.value;
        onChange(nv);
      },
      style: { border: 'none', background: 'transparent', fontSize: '12px', minWidth: '80px', maxWidth: '160px' }
    }),
    !disabled ? React.createElement('button', {
      onClick: () => { const nv = value.slice(); nv.splice(i, 1); onChange(nv); },
      style: { background: 'none', border: 'none', color: '#FF353F', cursor: 'pointer', padding: 0 }
    }, '×') : null
  ));
  if (!disabled) {
    items.push(React.createElement('button', {
      key: 'add',
      onClick: () => onChange(value.concat([typeof value[0] === 'number' ? 0 : ''])),
      style: { background: '#fff', border: '1px dashed rgba(25,25,25,0.2)', padding: '4px 8px', fontSize: '11px', cursor: 'pointer' }
    }, '+ Add'));
  }
  return React.createElement('div', { 'data-testid': testId, style: { display: 'flex', flexWrap: 'wrap', gap: '6px' } }, items);
}

function ArrayOfObjectsEditor(props) {
  const { value, onChange, disabled, testId } = props;
  const cols = Object.keys(value[0] || {});
  const blank = {};
  cols.forEach(c => { blank[c] = typeof (value[0] || {})[c] === 'number' ? 0 : ''; });

  const headerCells = cols.map(c => React.createElement('th', {
    key: c,
    style: { padding: '6px 8px', textAlign: 'left', fontWeight: 700, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252' }
  }, prettify(c)));
  if (!disabled) headerCells.push(React.createElement('th', { key: '_act', style: { width: '32px' } }));

  const rows = value.map((row, i) => {
    const cells = cols.map(c => React.createElement('td', { key: c, style: { padding: '4px 6px' } },
      React.createElement('input', {
        disabled,
        type: typeof row[c] === 'number' ? 'number' : 'text',
        value: row[c] == null ? '' : row[c],
        onChange: (e) => {
          const nv = value.slice();
          const val = typeof row[c] === 'number' ? Number(e.target.value) : e.target.value;
          nv[i] = Object.assign({}, row, { [c]: val });
          onChange(nv);
        },
        style: Object.assign({}, inputStyle, { padding: '4px 6px', fontSize: '11px' })
      })
    ));
    if (!disabled) {
      cells.push(React.createElement('td', { key: '_del', style: { textAlign: 'right' } },
        React.createElement('button', {
          onClick: () => { const nv = value.slice(); nv.splice(i, 1); onChange(nv); },
          style: { background: 'none', border: 'none', color: '#FF353F', cursor: 'pointer', padding: '4px' }
        }, '×')
      ));
    }
    return React.createElement('tr', { key: i, style: { borderTop: '1px solid rgba(25,25,25,0.05)' } }, cells);
  });

  return React.createElement('div', { 'data-testid': testId, style: { overflowX: 'auto', border: '1px solid rgba(25,25,25,0.08)' } },
    React.createElement('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: '11px' } },
      React.createElement('thead', null, React.createElement('tr', { style: { backgroundColor: '#F5F5F5' } }, headerCells)),
      React.createElement('tbody', null, rows)
    ),
    !disabled ? React.createElement('button', {
      onClick: () => onChange(value.concat([blank])),
      style: { width: '100%', padding: '6px', background: 'none', border: 'none', borderTop: '1px dashed rgba(25,25,25,0.15)', fontSize: '11px', cursor: 'pointer', color: '#525252' }
    }, '+ Add row') : null
  );
}

function NestedObjectEditor(props) {
  const { value, onChange, disabled, depth, testIdPrefix } = props;
  const rows = Object.entries(value).map(([k, v]) => React.createElement('div', {
    key: k,
    style: { display: 'grid', gridTemplateColumns: '160px 1fr', gap: '8px', alignItems: 'flex-start', padding: '4px 0' }
  },
    React.createElement('label', { style: { fontSize: '11px', fontWeight: 600, color: '#525252', paddingTop: '6px' } }, prettify(k)),
    React.createElement(ValueEditor, {
      keyName: k,
      value: v,
      disabled,
      depth: depth + 1,
      testIdPrefix,
      onChange: (nv) => onChange(Object.assign({}, value, { [k]: nv }))
    })
  ));
  return React.createElement('div', {
    style: { border: '1px solid rgba(25,25,25,0.08)', padding: '8px 10px', backgroundColor: depth > 1 ? '#fff' : '#FAFAFA' }
  }, rows);
}

export default function ValueEditor(props) {
  const { keyName, value, onChange, disabled, depth = 0, testIdPrefix = '' } = props;
  const tid = `${testIdPrefix}field-${(keyName || '').replace(/[^a-z0-9]/gi, '_')}`;
  if (isPrim(value)) {
    return React.createElement(PrimitiveEditor, { value, onChange, disabled, testId: tid });
  }
  if (Array.isArray(value)) {
    if (value.length === 0 || value.every(isPrim)) {
      return React.createElement(ArrayOfPrimitivesEditor, { value, onChange, disabled, testId: tid });
    }
    return React.createElement(ArrayOfObjectsEditor, { value, onChange, disabled, testId: tid });
  }
  return React.createElement(NestedObjectEditor, { value, onChange, disabled, depth, testIdPrefix: tid + '.' });
}
