import React, { useState, useEffect, useRef } from 'react';
import * as api from '../services/api';

export default function ProfilePhoto({ initials }) {
  const picker = useRef(null);
  const [photo, setPhoto] = useState('');
  const [version, setVersion] = useState(0);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    let live = true, url;
    api.getMyProfilePhoto().then(response => {
      if (!(response.data instanceof Blob) || response._serverError || response._silentAuth) throw new Error('Photo unavailable');
      if (live) { url = URL.createObjectURL(response.data); setPhoto(url); }
    }).catch(error => { if (live && error.response?.status !== 404) setMessage('Photo unavailable. Try again later.'); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [version]);
  const upload = async event => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file || !consent || busy) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setMessage('Choose a JPG or PNG photo, up to 2 MB.'); return;
    }
    setBusy(true); setMessage('');
    try { const response = await api.uploadMyProfilePhoto(file, consent); if (!response.data?.id) throw new Error('Upload not confirmed'); setVersion(value => value + 1); setMessage('Profile photo updated.'); }
    catch (error) { setMessage(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Photo upload failed. Please try again.'); }
    finally { setBusy(false); }
  };
  return <div style={{ maxWidth: 200 }}>
    <div style={{ width: 72, height: 72, borderRadius: '50%', overflow: 'hidden', background: '#FF353F', display: 'grid', placeItems: 'center', fontSize: 24, fontWeight: 900 }}>
      {photo ? <img src={photo} alt="Your profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : initials}
    </div>
    <label style={{ display: 'block', fontSize: 12, marginTop: 10 }}><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> Use my photo on My Profile. It is not shared in the Staff Directory.</label>
    <button type="button" disabled={!consent || busy} onClick={() => picker.current?.click()} style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, border: 'none', background: '#FF353F', color: '#fff', cursor: consent && !busy ? 'pointer' : 'default', opacity: consent ? 1 : 0.6 }}>
      {busy ? 'Uploading...' : 'Upload photo'}
    </button>
    <input ref={picker} aria-label="Upload profile photo" type="file" accept="image/jpeg,image/png" disabled={!consent || busy} onChange={upload} hidden />
    <div style={{ fontSize: 11, marginTop: 6 }}>JPG or PNG - Up to 2 MB</div>
    {message && <p role="status" style={{ fontSize: 12 }}>{message}</p>}
  </div>;
}
