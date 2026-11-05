import React, { useState, useEffect, useRef } from 'react';
import { Camera, Pencil, Trash2, LoaderCircle } from 'lucide-react';
import * as api from '../services/api';

export default function ProfilePhoto({ initials }) {
  const picker = useRef(null);
  const [photo, setPhoto] = useState('');
  const [version, setVersion] = useState(0);
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
    if (!file || busy) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setMessage('Choose a JPG or PNG photo, up to 2 MB.'); return;
    }
    setBusy(true); setMessage('');
    try { const response = await api.uploadMyProfilePhoto(file, true); if (!response.data?.id) throw new Error('Upload not confirmed'); setVersion(value => value + 1); setMessage('Profile photo updated.'); }
    catch (error) { setMessage(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Photo upload failed. Please try again.'); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (busy) return;
    setBusy(true); setMessage('');
    try {
      const response = await api.deleteMyProfilePhoto();
      if (response.data?.removed !== true) throw new Error('Removal not confirmed');
      setPhoto(''); setVersion(value => value + 1); setMessage('Profile photo removed.');
    } catch { setMessage('Could not remove your photo. Please try again.'); }
    finally { setBusy(false); }
  };
  const iconButton = { width: 36, height: 36, padding: 0, border: 'none', borderRadius: '50%', background: 'rgba(0,0,0,0.72)', color: '#fff', display: 'grid', placeItems: 'center', cursor: busy ? 'wait' : 'pointer' };
  return <div style={{ flexShrink: 0, width: 96 }}>
    <div aria-busy={busy} style={{ position: 'relative', width: 96, height: 96, borderRadius: '50%', overflow: 'hidden', background: '#FF353F', display: 'grid', placeItems: 'center', fontSize: 28, fontWeight: 900 }}>
      {photo ? <img src={photo} alt="Your profile" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <span style={{ alignSelf: 'start', marginTop: 12 }}>{initials}</span>}
      <div style={{ position: 'absolute', bottom: 4, left: 0, right: 0, display: 'flex', justifyContent: 'center', gap: 4 }}>
        <button type="button" aria-label={photo ? 'Change profile photo' : 'Upload profile photo'} title={photo ? 'Change photo' : 'Upload photo'} disabled={busy} onClick={() => picker.current?.click()} style={iconButton}>
          {busy ? <LoaderCircle size={18} /> : photo ? <Pencil size={18} /> : <Camera size={20} />}
        </button>
        {photo && <button type="button" aria-label="Delete profile photo" title="Delete photo" disabled={busy} onClick={remove} style={iconButton}><Trash2 size={18} /></button>}
      </div>
    </div>
    <input ref={picker} aria-label="Profile photo file" type="file" accept="image/jpeg,image/png" disabled={busy} onChange={upload} hidden />
    {message && <p role="status" style={{ fontSize: 12, lineHeight: 1.4, marginTop: 8 }}>{message}</p>}
  </div>;
}
