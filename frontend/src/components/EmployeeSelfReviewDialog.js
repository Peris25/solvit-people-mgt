import React, { useEffect, useRef } from 'react';
import PerformanceWorkflow from './PerformanceWorkflow';
import './PerformanceV3.css';

export default function EmployeeSelfReviewDialog({ review, onUpdated, onClose }) {
  const first = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    first.current?.focus();
    return () => previous?.focus?.();
  }, []);
  return <div className="performance-v3 pv-self-review-overlay"><section className="pv-self-review-dialog" role="dialog" aria-modal="true" aria-labelledby="employee-self-review-title" onKeyDown={event => {
    if (event.key === 'Escape') onClose();
    if (event.key === 'Tab') {
      const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]')];
      if (!controls.includes(document.activeElement) || document.activeElement === (event.shiftKey ? controls[0] : controls[controls.length - 1])) {
        event.preventDefault(); (event.shiftKey ? controls[controls.length - 1] : controls[0])?.focus();
      }
    }
  }}>
    <header className="pv-self-review-header"><div><h1 id="employee-self-review-title">{review.manager_led_probation?'Probation performance review':'Complete your self-review'}</h1><p>{review.employee_name} · {review.role_title}</p><p>{review.cycle_type?.replaceAll('_', ' ')} {review.cycle_year}{review.review_month ? ` · Month ${review.review_month}` : ''}</p></div><button ref={first} type="button" onClick={onClose}>Close</button></header>
    <div data-testid="review-view-modal"><PerformanceWorkflow key={review.id} review={review} onUpdated={onUpdated} /></div>
  </section></div>;
}
