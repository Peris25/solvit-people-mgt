import React from 'react';
import './LeaveActionButton.css';

export default function LeaveActionButton({ children, icon: Icon, variant = 'secondary', className = '', type = 'button', ...props }) {
  return <button {...props} type={type} className={`leave-action leave-action--${variant} ${className}`}>
    {Icon && <Icon size={16} aria-hidden="true" />}
    <span>{children}</span>
  </button>;
}
