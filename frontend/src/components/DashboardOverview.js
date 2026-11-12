import React from 'react';
import { ArrowRight, CheckCircle2, ClipboardList } from 'lucide-react';
import './DashboardOverview.css';

export function DashboardMetric({ label, value, sub, onClick, testId, Icon, unit }) {
  const Element = onClick ? 'button' : 'div';
  return <Element type={onClick ? 'button' : undefined} className="dashboard-metric" data-testid={testId} onClick={onClick}>
    <span className="dashboard-metric-label">{Icon && <Icon size={17} aria-hidden="true" />}{label}</span>
    <span className="dashboard-metric-value">{value ?? '—'}{unit && value != null && <small>{unit}</small>}</span>
    {sub && <span className="dashboard-metric-sub">{sub}</span>}
    {onClick && <ArrowRight className="dashboard-metric-arrow" size={17} aria-hidden="true" />}
  </Element>;
}

export function DashboardAttention({ items, description = 'Your next actions, in one place.' }) {
  const pending = items.filter(item => item.count == null || item.count > 0);
  return <section className="dashboard-attention" aria-label="Needs attention">
    <header className="dashboard-section-heading"><div><h2>Needs attention</h2><p>{description}</p></div><span className="dashboard-section-symbol"><ClipboardList size={19} aria-hidden="true" /></span></header>
    {pending.length ? <div className="dashboard-attention-list">{pending.map(item => {
      const available = item.count != null;
      const Element = available && item.onClick ? 'button' : 'div';
      const Icon = item.Icon || ClipboardList;
      return <Element type={Element === 'button' ? 'button' : undefined} key={item.key} className={`dashboard-attention-row${item.urgent ? ' is-urgent' : ''}`} onClick={available ? item.onClick : undefined}>
        <span className="dashboard-action-icon"><Icon size={19} aria-hidden="true" /></span>
        <span className="dashboard-action-copy"><strong>{item.label}</strong><span>{available ? item.detail : 'Information unavailable. Please refresh to retry.'}</span></span>
        <span className="dashboard-action-count">{available ? item.count : '—'}</span>
        {Element === 'button' && <ArrowRight size={17} className="dashboard-action-arrow" aria-hidden="true" />}
      </Element>;
    })}</div> : <div className="dashboard-empty"><CheckCircle2 size={24} aria-hidden="true" /><div><strong>You’re up to date</strong><p>No pending actions in this overview.</p></div></div>}
  </section>;
}
