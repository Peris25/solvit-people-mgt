import React, {useId} from 'react';
import './ActionFeedback.css';

// Prerequisites are explicit business copy supplied by the owning screen.
// Busy-only buttons retain their existing layout and loading labels.
export default function ActionButton({disabledReason,disabled,children,...props}){
  const id=useId();
  const reason=disabled&&disabledReason;
  const button=<button {...props} disabled={disabled} aria-describedby={[props['aria-describedby'],reason?id:null].filter(Boolean).join(' ')||undefined}>{children}</button>;
  return reason?<span className="action-feedback-control">{button}<span id={id} className="action-feedback-reason" aria-live="polite">{reason}</span></span>:button;
}
