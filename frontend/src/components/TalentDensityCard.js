import React from 'react';
import './TalentDensityCard.css';

const percent = value => value == null ? 'Awaiting data' : `${Number(value).toFixed(1)}%`;
export default function TalentDensityCard({ data }) {
  if (!data) return null;
  const components = data.components || {};
  const parts = [
    ['Stars & Core Contributors', 50, components.primary_stars_core_pct, 'Share of FTE staff in these 9-box placements'],
    ['Section B · 360° values', 30, components.secondary_values_avg_pct, 'Average Section B across FTE staff, converted to a percentage'],
    ['Company Alignment Survey', 20, components.alignment_survey_pct ?? components.tertiary_alignment_pct, 'Company Alignment score out of 100'],
  ];
  return <section className="talent-density-card" data-testid="talent-density-card" aria-label="Talent density policy breakdown">
    <header><div><p className="talent-density-eyebrow">Company dashboard</p><h2>Talent density</h2><p>Current policy · 50% placement + 30% values + 20% Alignment</p></div><div className="talent-density-total"><strong>{percent(data.score_pct)}</strong><span>Target {data.target_pct ?? 85}%</span></div></header>
    <div className="talent-density-parts">{parts.map(([title, weight, value, description], i) => <section key={title}><div className="talent-density-part-heading"><span>Part {i + 1}</span><strong>{weight}% weight</strong></div><h3>{title}</h3><div className="talent-density-part-value">{percent(value)}</div><p>{description}</p><p className="talent-density-contribution">Weighted contribution: {value == null ? 'Awaiting data' : `${(value * weight / 100).toFixed(2)} points`}</p></section>)}</div>
    <footer>Section B conversion: (3 − average Section B score) ÷ 2 × 100. A score of 1 maps to 100%; 3 maps to 0%.{data.score_pct == null && ' The company total remains unavailable until all required data is complete.'}</footer>
  </section>;
}
