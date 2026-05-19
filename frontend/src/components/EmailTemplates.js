/**
 * EmailTemplates — IT Admin can edit, HR Admin/HR Manager can view & preview.
 * Drop-in section for MastersSettings.
 */
import React, { useEffect, useState } from 'react';
import DOMPurify from 'dompurify';
import * as api from '../services/api';

// Allow only safe inline / structural HTML in template bodies.
// Templates can contain {{merge_tags}}, basic formatting, lists, links.
const SANITIZE_OPTS = {
  ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'a', 'ul', 'ol', 'li',
                 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'hr', 'code', 'font'],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'style', 'size'],
  ALLOW_DATA_ATTR: false,
};
const sanitize = (html) => DOMPurify.sanitize(html || '', SANITIZE_OPTS);

export default function EmailTemplates() {
  const [groups, setGroups] = useState({});
  const [canEdit, setCanEdit] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [detail, setDetail] = useState(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.listEmailTemplates();
      setGroups(r.data?.groups || {});
      setCanEdit(!!r.data?.can_edit);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openTemplate = async (key) => {
    setSelectedKey(key); setPreview(null);
    try {
      const r = await api.getEmailTemplate(key);
      setDetail(r.data);
      setSubject(r.data.subject || '');
      setBody(r.data.body || '');
    } catch { setDetail(null); }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.updateEmailTemplate(selectedKey, { subject, body });
      await openTemplate(selectedKey);
      await load();
    } finally { setSaving(false); }
  };

  const reset = async () => {
    if (!window.confirm('Reset this template to the system default?')) return;
    await api.resetEmailTemplate(selectedKey);
    await openTemplate(selectedKey);
    await load();
  };

  const runPreview = async () => {
    const r = await api.previewEmailTemplate(selectedKey, {});
    setPreview(r.data);
  };

  return (
    <div data-testid="email-templates-section" style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '20px', fontFamily: 'Nunito Sans, sans-serif' }}>
      <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', maxHeight: '70vh', overflowY: 'auto' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(25,25,25,0.08)', backgroundColor: '#F5F5F5' }}>
          <strong style={{ fontFamily: 'Barlow', fontSize: '12px', letterSpacing: '0.05em' }}>Templates</strong>
          {!canEdit && <div style={{ fontSize: '10px', color: '#525252', marginTop: '2px' }}>View / preview only</div>}
        </div>
        {loading ? <div style={{ padding: '20px', textAlign: 'center', color: '#525252' }}>Loading…</div> : (
          Object.entries(groups).map(([module, items]) => (
            <div key={module}>
              <div style={{ padding: '10px 16px 4px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#FF353F', fontFamily: 'Barlow' }}>{module}</div>
              {items.map(t => (
                <button key={t.key} data-testid={`tpl-${t.key}`} onClick={() => openTemplate(t.key)} style={{
                  display: 'block', width: '100%', padding: '8px 16px', textAlign: 'left',
                  backgroundColor: selectedKey === t.key ? '#FEF2F2' : 'transparent',
                  borderLeftWidth: '3px',
                  borderLeftStyle: 'solid',
                  borderLeftColor: selectedKey === t.key ? '#FF353F' : 'transparent',
                  border: 'none', cursor: 'pointer', fontSize: '11px',
                  fontWeight: selectedKey === t.key ? 700 : 400, color: '#191919',
                  fontFamily: 'Nunito Sans'
                }}>{t.name}</button>
              ))}
            </div>
          ))
        )}
      </div>

      <div>
        {!detail ? (
          <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '32px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>
            Select a template to view or edit.
          </div>
        ) : (
          <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
            <div style={{ padding: '16px 22px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
              <div>
                <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.18em', color: '#FF353F', fontFamily: 'Barlow', fontWeight: 700 }}>{detail.module}</div>
                <h3 style={{ margin: '4px 0 0', fontFamily: 'Barlow', fontWeight: 900, letterSpacing: '-0.02em' }}>{detail.name}</h3>
                <code style={{ fontSize: '10px', color: '#525252' }}>{detail.key}</code>
                {detail.updated_at && <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '4px' }}>Last edited {new Date(detail.updated_at).toLocaleString('en-GB')}{detail.updated_by_name ? ` · ${detail.updated_by_name}` : ''}</div>}
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button data-testid="tpl-preview-btn" onClick={runPreview} style={btnGhost}>Preview</button>
                {canEdit && <button data-testid="tpl-reset-btn" onClick={reset} style={btnGhost}>Reset to Default</button>}
                {canEdit && <button data-testid="tpl-save-btn" onClick={save} disabled={saving} style={btnRed}>{saving ? 'Saving…' : 'Save'}</button>}
              </div>
            </div>

            <div style={{ padding: '20px 22px', display: 'grid', gridTemplateColumns: '1fr 200px', gap: '20px' }}>
              <div>
                <label style={lbl}>Subject Line</label>
                <input data-testid="tpl-subject" value={subject} onChange={e => setSubject(e.target.value)} disabled={!canEdit} style={inp} />
                <label style={{ ...lbl, marginTop: '14px' }}>Body (HTML supported)</label>
                {canEdit ? (
                  <RichBody value={body} onChange={setBody} />
                ) : (
                  <div style={{ border: '1px solid rgba(25,25,25,0.15)', padding: '12px', minHeight: '220px', fontSize: '12px', backgroundColor: '#F9FAFB' }} dangerouslySetInnerHTML={{ __html: sanitize(body) }} />
                )}
              </div>
              <div>
                <label style={lbl}>Merge Tags</label>
                <div style={{ border: '1px solid rgba(25,25,25,0.1)', padding: '8px', backgroundColor: '#F5F5F5', maxHeight: '320px', overflowY: 'auto' }}>
                  {(detail.merge_tags || []).length === 0 ? <div style={{ fontSize: '10px', color: '#9CA3AF' }}>No tags</div> : (detail.merge_tags || []).map(t => (
                    <code data-testid={`tag-${t}`} key={t} onClick={() => { if (canEdit) { navigator.clipboard?.writeText(`{{${t}}}`); } }} style={{ display: 'block', fontSize: '10px', padding: '3px 0', color: '#191919', cursor: canEdit ? 'copy' : 'default' }}>{`{{${t}}}`}</code>
                  ))}
                </div>
                {canEdit && <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '6px' }}>Click a tag to copy it to your clipboard.</div>}
              </div>
            </div>

            {preview && (
              <div data-testid="tpl-preview" style={{ borderTop: '1px solid rgba(25,25,25,0.08)', padding: '20px 22px', backgroundColor: '#F9FAFB' }}>
                <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px', fontFamily: 'Barlow' }}>Preview · Subject</div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#191919', marginBottom: '12px' }}>{preview.subject}</div>
                <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', marginBottom: '6px', fontFamily: 'Barlow' }}>Body</div>
                <div style={{ border: '1px solid rgba(25,25,25,0.1)', padding: '14px', backgroundColor: '#fff', fontSize: '12px' }} dangerouslySetInnerHTML={{ __html: sanitize(preview.body_html) }} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function RichBody({ value, onChange }) {
  // Lightweight contenteditable rich text editor — bold/italic/list/link/font-size.
  const ref = React.useRef(null);
  const lastValue = React.useRef(value);
  React.useEffect(() => {
    if (ref.current && value !== lastValue.current) {
      // Sanitize before injecting into the contenteditable — same allowlist
      // used everywhere else in this component.
      ref.current.innerHTML = sanitize(value);
      lastValue.current = value;
    }
  }, [value]);
  const exec = (cmd, arg) => { document.execCommand(cmd, false, arg); ref.current && pushUpdate(); };
  const pushUpdate = () => {
    const html = ref.current.innerHTML;
    lastValue.current = html;
    onChange(html);
  };
  const link = () => {
    const url = window.prompt('Link URL', 'https://');
    if (url) exec('createLink', url);
  };
  return (
    <div>
      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', padding: '6px', backgroundColor: '#F5F5F5', border: '1px solid rgba(25,25,25,0.15)', borderBottomWidth: 0 }}>
        <ToolBtn onClick={() => exec('bold')}>B</ToolBtn>
        <ToolBtn onClick={() => exec('italic')} italic>I</ToolBtn>
        <ToolBtn onClick={() => exec('insertUnorderedList')}>• List</ToolBtn>
        <ToolBtn onClick={link}>Link</ToolBtn>
        <select onChange={e => exec('fontSize', e.target.value)} defaultValue="3" style={{ padding: '4px 6px', fontSize: '11px', border: '1px solid rgba(25,25,25,0.15)' }}>
          <option value="2">Small</option><option value="3">Normal</option><option value="4">Large</option><option value="5">XL</option>
        </select>
      </div>
      <div
        data-testid="tpl-body-editor"
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={pushUpdate}
        style={{ border: '1px solid rgba(25,25,25,0.15)', padding: '12px', minHeight: '220px', fontSize: '13px', fontFamily: 'Nunito Sans', outline: 'none', backgroundColor: '#fff', lineHeight: 1.5 }}
      />
    </div>
  );
}

function ToolBtn({ children, onClick, italic }) {
  return <button type="button" onClick={onClick} style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 700, fontStyle: italic ? 'italic' : 'normal', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.15)', cursor: 'pointer', fontFamily: 'Barlow' }}>{children}</button>;
}

const lbl = { display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '5px', fontFamily: 'Barlow' };
const inp = { width: '100%', padding: '8px 10px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', fontFamily: 'Nunito Sans', boxSizing: 'border-box' };
const btnRed = { padding: '8px 16px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' };
const btnGhost = { padding: '8px 14px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' };
