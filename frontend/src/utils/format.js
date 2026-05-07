/**
 * Kenya-specific formatting helpers.
 * - KES currency (en-KE locale, no decimals on integer amounts)
 * - EAT (Africa/Nairobi) timestamps in DD/MM/YYYY · HH:mm format
 */

const KES_FORMATTER = new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 0,
});

const KES_FORMATTER_DECIMAL = new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format a number/string as KES amount. Returns '—' for null/undefined/empty. */
export function fmtKES(amount, opts = {}) {
  if (amount === null || amount === undefined || amount === '') return '—';
  const n = typeof amount === 'string' ? Number(amount) : amount;
  if (Number.isNaN(n)) return '—';
  const formatter = opts.decimals ? KES_FORMATTER_DECIMAL : KES_FORMATTER;
  return formatter.format(n);
}

/** Format an ISO datetime in EAT (Africa/Nairobi) — DD/MM/YYYY · HH:mm */
export function fmtEAT(iso, opts = { withTime: true }) {
  if (!iso) return '—';
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return '—';
  const datePart = d.toLocaleDateString('en-GB', { timeZone: 'Africa/Nairobi', day: '2-digit', month: '2-digit', year: 'numeric' });
  if (!opts.withTime) return datePart;
  const timePart = d.toLocaleTimeString('en-GB', { timeZone: 'Africa/Nairobi', hour: '2-digit', minute: '2-digit', hour12: false });
  return `${datePart} · ${timePart} EAT`;
}

/** Format an ISO date as DD/MM/YYYY in EAT (no time). */
export function fmtDateEAT(iso) {
  return fmtEAT(iso, { withTime: false });
}

/** Quick re-export of the KES symbol for places where a string is needed inline. */
export const KES_SYMBOL = 'KES';
