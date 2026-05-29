import React from 'react';
import { X } from 'lucide-react';
import * as api from '../services/api';

/**
 * Renders a full-detail modal for either an eligible candidate or an ineligible
 * applicant. The shape differs slightly between the two collections, so we
 * accept a `mode` prop that decides which fields to surface.
 */
const REASON_LABELS = {
  licence: 'Driving Licence',
  qualifications: 'Qualifications / Experience',
  smartphone: 'Smartphone with camera',
  availability: 'Standard-hours availability',
  commission: 'Commission acknowledgement',
};

export default function ApplicantDetailModal({ open, onClose, data, mode, loading }) {
  if (!open) return null;
  const isEligible = mode === 'eligible';

  return (
    <div
      data-testid="detail-modal-backdrop"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        zIndex: 100, padding: '40px 20px', overflowY: 'auto'
      }}
    >
      <div
        data-testid="detail-modal"
        onClick={e => e.stopPropagation()}
        style={{
          backgroundColor: '#fff', width: '100%', maxWidth: '640px',
          border: '1px solid rgba(25,25,25,0.12)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
          fontFamily: 'Nunito Sans, sans-serif'
        }}
      >
        <header style={{ padding: '18px 22px', borderBottom: '1px solid rgba(25,25,25,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: isEligible ? '#16A34A' : '#991B1B' }}>
              {isEligible ? 'Eligible · Stage 1 passed' : 'Ineligible · Stopped at Stage 1'}
            </div>
            <h2 style={{ margin: '4px 0 0', fontSize: '20px', fontWeight: 900, letterSpacing: '-0.03em', color: '#191919' }}>
              {loading ? 'Loading…' : (data?.full_name || '—')}
            </h2>
            <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px', fontFamily: 'monospace' }}>{data?.requisition_code}</div>
          </div>
          <button data-testid="detail-close" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: '#525252' }}>
            <X size={20} />
          </button>
        </header>

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>Loading details…</div>
        ) : !data ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#9CA3AF', fontSize: '13px' }}>Record not found.</div>
        ) : (
          <div style={{ padding: '20px 22px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 22px' }}>
            <Field label="Phone">{data.phone_number || '—'}</Field>
            <Field label="Email">{data.email || '—'}</Field>
            <Field label="County">{data.county || '—'}</Field>
            <Field label="Town / Area">{data.town_area || '—'}</Field>
            <Field label="Channel">{isEligible ? data.source : data.channel}</Field>
            <Field label="Submitted">
              {(() => {
                const ts = isEligible ? data.created_at : data.submitted_at;
                return ts ? new Date(ts).toLocaleString('en-KE') : '—';
              })()}
            </Field>

            {isEligible && (
              <>
                <Field label="Current Stage" span={2}>{data.current_stage || '—'}</Field>
                <Field label="Stage Status">{data.current_stage_status || '—'}</Field>
                <Field label="Position">{data.position_applied || '—'}</Field>
              </>
            )}

            <Field label="Driving Licence">{data.has_driving_licence === false ? 'No' : data.has_driving_licence === true ? 'Yes' : '—'}</Field>
            <Field label="Smartphone w/ camera">{data.has_smartphone === false ? 'No' : data.has_smartphone === true ? 'Yes' : '—'}</Field>
            <Field label="Availability">{data.availability || '—'}</Field>
            <Field label="Commission Acknowledged">{data.commission_acknowledged ? 'Yes' : 'No'}</Field>

            <Field label="Qualifications" span={2}>
              {(data.qualifications && data.qualifications.length)
                ? (<ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: '#191919' }}>
                     {data.qualifications.map((q, i) => <li key={'q-' + i}>{q}</li>)}
                   </ul>)
                : '—'}
            </Field>

            {data.previous_inspector_company && (
              <Field label="Previous Inspector Company" span={2}>{data.previous_inspector_company}</Field>
            )}

            {data.cv_path && (
              <Field label="CV / Résumé" span={2}>
                <a
                  data-testid="cv-download"
                  href={isEligible ? api.eligibleCvUrl(data.id) : api.ineligibleCvUrl(data.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: 'inline-block', padding: '6px 12px', backgroundColor: '#191919', color: '#fff', textDecoration: 'none', fontSize: '12px', fontWeight: 700 }}
                >
                  Download {data.cv_filename || 'CV'}
                </a>
              </Field>
            )}

            {!isEligible && (data.failed_criteria || []).length > 0 && (
              <Field label="Failed Criteria" span={2}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {data.failed_criteria.map(k => (
                    <span key={k} style={{ padding: '3px 9px', fontSize: '11px', fontWeight: 700, backgroundColor: '#FEE2E2', color: '#991B1B' }}>
                      {REASON_LABELS[k] || k}
                    </span>
                  ))}
                </div>
              </Field>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children, span = 1 }) {
  return (
    <div style={{ gridColumn: span === 2 ? '1 / span 2' : 'auto' }}>
      <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '13px', color: '#191919', wordBreak: 'break-word' }}>{children}</div>
    </div>
  );
}
