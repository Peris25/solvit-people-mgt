import React, { useEffect, useRef } from 'react';
import { X, CheckCircle2 } from 'lucide-react';
import './FormDialog.css';

export function fieldErrorsFrom(error) {
  const detail = error?.response?.data?.detail;
  if (!Array.isArray(detail)) return {};
  return Object.fromEntries(detail.filter(item => Array.isArray(item.loc) && typeof item.msg === 'string')
    .map(item => [item.loc.filter(part => typeof part === 'string' && part !== 'body').pop(), item.msg]));
}

export function FieldError({ field, errors }) {
  return errors[field] ? <span id={`form-error-${field}`} className="workspace-field-error">{errors[field]}</span> : null;
}

export function FormNotice({ message, onDismiss }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(() => onDismiss(''), 5000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);
  return message ? <div className="workspace-form-notice" role="status"><CheckCircle2 size={18} aria-hidden="true" /><span>{message}</span><button type="button" aria-label="Dismiss confirmation" onClick={() => onDismiss('')}><X size={16} /></button></div> : null;
}

export default function FormDialog({ title, description, busy, onClose, children, id }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
    dialog.querySelector('input:not([disabled]),select:not([disabled]),textarea:not([disabled])')?.focus();
    return () => { if (dialog.close) dialog.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="workspace-form-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="workspace-form-heading"><div><h2 id={`${id}-title`}>{title}</h2><p id={`${id}-description`}>{description}</p></div>
      <button className="workspace-form-close" type="button" aria-label="Close form" disabled={busy} onClick={onClose}><X size={20} /></button>
    </header>
    {children}
  </dialog>;
}
