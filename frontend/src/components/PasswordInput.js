import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export default function PasswordInput({ type = 'password', style = {}, ...props }) {
  const [visible, setVisible] = useState(false);
  if (type !== 'password') return <input {...props} type={type} style={style} />;
  const { margin, marginTop, marginBottom, marginLeft, marginRight, ...inputStyle } = style;
  return <span style={{ display: 'block', position: 'relative', margin, marginTop, marginBottom, marginLeft, marginRight }}>
    <input {...props} type={visible ? 'text' : 'password'} style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', paddingRight: '48px' }} />
    <button type="button" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}
      disabled={props.disabled} onClick={() => setVisible(current => !current)}
      style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '44px', border: 0, background: 'transparent', color: '#525252', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: props.disabled ? 'default' : 'pointer' }}>
      {visible ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
    </button>
  </span>;
}
