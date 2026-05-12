import React, { useEffect, useState } from 'react';
import * as api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Upload, Download, FileSpreadsheet, History as HistoryIcon } from 'lucide-react';

const KINDS = [
  { k: 'fte_employee', label: 'FTE Employee Import' },
  { k: 'solver', label: 'Solver Import' },
  { k: 'historical_performance', label: 'Historical Performance Data Import' },
];

export default function DataImport() {
  const { user } = useAuth();
  const isHR = ['hr_admin', 'hr_manager'].includes(user?.role);
  const isITAuditView = user?.role === 'it_admin';

  const [tab, setTab] = useState(isHR ? 'upload' : 'templates');
  const [kind, setKind] = useState('fte_employee');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [validation, setValidation] = useState(null);
  const [onlyValid, setOnlyValid] = useState(true);
  const [history, setHistory] = useState([]);

  useEffect(() => { loadHistory(); }, []);

  const loadHistory = async () => {
    try {
      const r = await api.getImportHistory();
      setHistory(r.data || []);
    } catch {}
  };

  if (!isHR && !isITAuditView) {
    return <div data-testid="data-import-locked" style={{ padding: '32px', textAlign: 'center', color: '#525252', fontFamily: 'Nunito Sans' }}>You don't have access to Data Import.</div>;
  }

  const downloadTemplate = (k) => { window.location.href = api.dataImportTemplateUrl(k); };

  const runValidate = async (e) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('kind', kind);
      fd.append('file', file);
      const r = await api.validateImport(fd);
      setValidation(r.data);
    } catch (err) {
      alert('Validation failed: ' + (err?.response?.data?.detail || err.message));
    } finally { setBusy(false); }
  };

  const runImport = async () => {
    if (!validation) return;
    setBusy(true);
    try {
      const r = await api.executeImport({ kind, cache_id: validation.cache_id, only_valid: onlyValid, filename: validation.filename });
      alert(`Imported ${r.data.imported} row(s). Skipped ${r.data.skipped}.`);
      setValidation(null);
      setFile(null);
      loadHistory();
      setTab('history');
    } catch (err) {
      alert('Import failed: ' + (err?.response?.data?.detail || err.message));
    } finally { setBusy(false); }
  };

  const downloadErrors = async () => {
    if (!validation) return;
    try {
      const r = await api.downloadErrorReport(validation.rows.filter(x => !x.valid));
      const blob = new Blob([r.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'solvit_import_errors.xlsx'; a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert('Could not download error report: ' + err.message);
    }
  };

  return (
    <div data-testid="data-import-page" style={{ fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0, fontFamily: 'Barlow' }}>Data Import</h1>
        <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>Bulk-import employees, solvers and historical performance from Excel.</p>
      </div>

      <div style={{ display: 'flex', borderBottom: '2px solid rgba(25,25,25,0.1)', marginBottom: '20px' }}>
        {isHR && <Tab id="upload" label="Upload & Import" Icon={Upload} tab={tab} setTab={setTab} />}
        <Tab id="templates" label="Templates" Icon={Download} tab={tab} setTab={setTab} />
        <Tab id="history" label="Import History" Icon={HistoryIcon} tab={tab} setTab={setTab} />
      </div>

      {tab === 'templates' && (
        <div data-testid="templates-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <p style={{ fontSize: '12px', color: '#525252', marginTop: 0 }}>Download a template, fill in your data (delete row 2 — the sample row — before importing), then return to the Upload tab.</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
            {KINDS.map(k => (
              <div key={k.k} style={{ border: '1px solid rgba(25,25,25,0.08)', padding: '16px', backgroundColor: '#F5F5F5' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                  <FileSpreadsheet size={18} color="#FF353F" />
                  <strong style={{ fontFamily: 'Barlow', letterSpacing: '-0.01em' }}>{k.label}</strong>
                </div>
                <button data-testid={`tpl-${k.k}`} onClick={() => downloadTemplate(k.k)} style={{ padding: '8px 14px', backgroundColor: '#191919', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <Download size={12} /> Download .xlsx
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'upload' && isHR && (
        <div data-testid="upload-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '20px' }}>
          <form onSubmit={runValidate} style={{ display: 'flex', gap: '14px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div>
              <label style={lbl}>Import Type</label>
              <select data-testid="import-kind" value={kind} onChange={e => { setKind(e.target.value); setValidation(null); }} style={inp}>
                {KINDS.map(k => <option key={k.k} value={k.k}>{k.label}</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: '260px' }}>
              <label style={lbl}>Excel File (.xlsx)</label>
              <input data-testid="import-file" type="file" accept=".xlsx" required onChange={e => { setFile(e.target.files[0]); setValidation(null); }} style={{ ...inp, padding: '6px 4px' }} />
            </div>
            <button data-testid="validate-btn" type="submit" disabled={busy || !file} style={btnRed}>{busy ? 'Validating…' : 'Validate'}</button>
          </form>

          {validation && (
            <div data-testid="validation-result" style={{ marginTop: '24px' }}>
              <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', marginBottom: '14px' }}>
                <Stat label="Total rows" value={validation.total_rows} />
                <Stat label="Valid" value={validation.valid_count} color="#22C55E" />
                <Stat label="Errors" value={validation.error_count} color="#FF353F" />
              </div>
              <div style={{ maxHeight: '380px', overflowY: 'auto', border: '1px solid rgba(25,25,25,0.08)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                  <thead><tr style={{ backgroundColor: '#F5F5F5', position: 'sticky', top: 0 }}>
                    {['Row', 'Status', 'Errors / Summary'].map(h =>
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', fontFamily: 'Barlow' }}>{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {validation.rows.map(r => (
                      <tr key={r.row_index} data-testid={`val-row-${r.row_index}`} style={{ backgroundColor: r.valid ? '#F0FDF4' : '#FEF2F2', borderBottom: '1px solid rgba(25,25,25,0.04)' }}>
                        <td style={{ padding: '6px 12px', fontWeight: 700 }}>{r.row_index}</td>
                        <td style={{ padding: '6px 12px' }}>{r.valid ? <span style={{ color: '#16A34A', fontWeight: 700 }}>OK</span> : <span style={{ color: '#FF353F', fontWeight: 700 }}>ERROR</span>}</td>
                        <td style={{ padding: '6px 12px', color: '#525252' }}>{r.valid ? Object.values(r.raw).filter(v => v).slice(0, 3).join(' · ') : (r.errors || []).join(' · ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: '14px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                <label style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <input data-testid="only-valid" type="checkbox" checked={onlyValid} onChange={e => setOnlyValid(e.target.checked)} />
                  Import valid rows only (skip errors)
                </label>
                {validation.error_count > 0 && (
                  <button data-testid="download-errors-btn" onClick={downloadErrors} style={btnGhost}>Download Error Report (.xlsx)</button>
                )}
                <button data-testid="cancel-import-btn" onClick={() => { setValidation(null); setFile(null); }} style={btnGhost}>Cancel</button>
                <button data-testid="confirm-import-btn" onClick={runImport} disabled={busy || validation.valid_count === 0} style={btnRed}>{busy ? 'Importing…' : `Import ${onlyValid ? validation.valid_count : validation.total_rows} row(s)`}</button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div data-testid="history-panel" style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead><tr style={{ backgroundColor: '#F5F5F5' }}>
              {['Type', 'File', 'Imported / Skipped', 'When', 'By', 'Original'].map(h =>
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontFamily: 'Barlow' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={h.id} style={{ borderBottom: '1px solid rgba(25,25,25,0.05)', backgroundColor: i % 2 === 0 ? '#fff' : '#FAFAFA' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700 }}>{(KINDS.find(k => k.k === h.kind) || {}).label || h.kind}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{h.filename}</td>
                  <td style={{ padding: '10px 14px' }}><strong style={{ color: '#22C55E' }}>{h.rows_imported}</strong> / <span style={{ color: '#FF353F' }}>{h.rows_skipped}</span></td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{h.imported_at ? new Date(h.imported_at).toLocaleString('en-GB') : '—'}</td>
                  <td style={{ padding: '10px 14px', color: '#525252' }}>{h.imported_by_name || '—'}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <a href={api.importHistoryDownloadUrl(h.id)} target="_blank" rel="noreferrer" style={{ fontSize: '10px', color: '#FF353F', fontWeight: 700, textDecoration: 'none', textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'Barlow' }}>Download</a>
                  </td>
                </tr>
              ))}
              {history.length === 0 && <tr><td colSpan={6} style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>No imports yet.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Tab({ id, label, Icon, tab, setTab }) {
  return (
    <button data-testid={`di-tab-${id}`} onClick={() => setTab(id)} style={{
      padding: '10px 18px', backgroundColor: 'transparent', border: 'none',
      borderBottom: tab === id ? '2px solid #FF353F' : '2px solid transparent',
      marginBottom: '-2px', cursor: 'pointer', fontSize: '12px',
      fontWeight: tab === id ? 700 : 500, color: tab === id ? '#FF353F' : '#525252',
      fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.1em',
      display: 'inline-flex', alignItems: 'center', gap: '8px'
    }}><Icon size={14} />{label}</button>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ padding: '12px 16px', backgroundColor: '#F5F5F5', borderLeftWidth: '3px', borderLeftStyle: 'solid', borderLeftColor: color || '#191919' }}>
      <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', fontFamily: 'Barlow' }}>{label}</div>
      <div style={{ fontSize: '24px', fontWeight: 900, fontFamily: 'Barlow', letterSpacing: '-0.03em', color: color || '#191919', marginTop: '2px' }}>{value}</div>
    </div>
  );
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans', boxSizing: 'border-box' };
const btnRed = { padding: '10px 22px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' };
const btnGhost = { padding: '10px 18px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '12px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };
