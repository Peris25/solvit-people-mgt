import React from 'react';
import ActionButton from './ActionButton';
import './LeaveActionButton.css';

export default function LeaveActionButton({ children, icon: Icon, variant = 'secondary', className = '', type = 'button', ...props }) {
  return <ActionButton {...props} type={type} className={`leave-action leave-action--${variant} ${className}`}>
    {Icon && <Icon size={16} aria-hidden="true" />}
    <span>{children}</span>
  </ActionButton>;
}
