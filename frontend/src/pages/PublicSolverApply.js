import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import * as api from '../services/api';

const QUAL_OPTIONS = [
  'Certificate, Diploma, or Degree in Mechanical / Automotive Engineering',
  'Sound knowledge of vehicles and assets to be inspected',
  '1–2 years of experience in a similar role (preferred)',
  'Has worked as a vehicle inspector previously',
];

const CHANNELS = ['Facebook', 'Instagram', 'WhatsApp', 'Referral from a Solver', 'Job board', 'Other'];
const CV_ALLOWED = ['application/pdf', 'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
const CV_MAX_BYTES = 5 * 1024 * 1024;

export default function PublicSolverApply() {
  const { rid } = useParams();
  const [req, setReq] = useState(null);
  const [loading, setLoading] = useState(true);
  const [challenge, setChallenge] = useState(null);
  const [form, setForm] = useState({
    full_name: '', phone_number: '', email: '', county: '', town_area: '',
    has_driving_licence: null, qualifications: [], previous_inspector_company: '',
    has_smartphone: null, availability: null, commission_acknowledged: false, channel: '',
    challenge_answer: '',
    website_url: '', // honeypot — kept empty by humans
  });
  const [cvFile, setCvFile] = useState(null);
  const [cvError, setCvError] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    api.solverIntakePublic(rid).then(r => setReq(r.data)).finally(() => setLoading(false));
    api.solverIntakeChallenge(rid).then(r => setChallenge(r.data)).catch(() => {});
  }, [rid]);

  const refreshChallenge = () => {
    api.solverIntakeChallenge(rid).then(r => setChallenge(r.data)).catch(() => {});
  };

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const toggleQual = (q) => {
    setForm(p => {
      if (q === 'None of the above') {
        return { ...p, qualifications: p.qualifications.includes(q) ? [] : ['None of the above'] };
      }
      const has = p.qualifications.includes(q);
      const without_none = p.qualifications.filter(x => x !== 'None of the above');
      return { ...p, qualifications: has ? without_none.filter(x => x !== q) : [...without_none, q] };
    });
  };

  const noneSelected = form.qualifications.includes('None of the above');
  const inspectorExperienceSelected = form.qualifications.includes('Has worked as a vehicle inspector previously');

  const onCvChange = (e) => {
    setCvError('');
    const f = e.target.files?.[0];
    if (!f) { setCvFile(null); return; }
    if (!CV_ALLOWED.includes(f.type) && !/\.(pdf|docx?)$/i.test(f.name)) {
      setCvError('CV must be PDF, DOC, or DOCX.');
      e.target.value = '';
      return;
    }
    if (f.size > CV_MAX_BYTES) {
      setCvError('CV exceeds the 5MB limit.');
      e.target.value = '';
      return;
    }
    setCvFile(f);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.has_driving_licence === null || form.has_smartphone === null || !form.availability) {
      setError('Please answer all questions.');
      return;
    }
    if (!form.commission_acknowledged) {
      setError('Please acknowledge the commission-based terms to proceed.');
      return;
    }
    if (inspectorExperienceSelected && !form.previous_inspector_company.trim()) {
      setError('Please provide the company name for your previous inspector role.');
      return;
    }
    if (!challenge?.token || !form.challenge_answer) {
      setError('Please answer the security question.');
      return;
    }

    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('full_name', form.full_name);
      fd.append('phone_number', form.phone_number);
      fd.append('email', form.email);
      fd.append('county', form.county);
      fd.append('town_area', form.town_area);
      fd.append('has_driving_licence', String(form.has_driving_licence));
      fd.append('qualifications', JSON.stringify(form.qualifications));
      fd.append('previous_inspector_company', form.previous_inspector_company || '');
      fd.append('has_smartphone', String(form.has_smartphone));
      fd.append('availability', form.availability);
      fd.append('commission_acknowledged', String(form.commission_acknowledged));
      fd.append('channel', form.channel);
      fd.append('challenge_token', challenge.token);
      fd.append('challenge_answer', form.challenge_answer);
      fd.append('website_url', form.website_url); // honeypot
      if (cvFile) fd.append('cv', cvFile, cvFile.name);

      const r = await api.solverIntakeApply(rid, fd);
      setResult(r.data);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      const d = e.response?.data?.detail;
      let msg;
      if (typeof d === 'string') msg = d;
      else if (Array.isArray(d)) msg = d.map(x => (x?.msg || JSON.stringify(x))).join('; ');
      else if (d && typeof d === 'object') msg = d.msg || JSON.stringify(d);
      else msg = e.message || 'Submission failed. Please try again.';
      setError(msg);
      // If captcha expired/wrong, refresh it
      if (/challenge|expired|incorrect/i.test(msg)) refreshChallenge();
    } finally { setSubmitting(false); }
  };

  if (loading) return <CenteredFrame><p>Loading…</p></CenteredFrame>;
  if (!req || !req.found || req.status !== 'Open') {
    return (
      <CenteredFrame>
        <div data-testid="apply-closed" style={{ textAlign: 'center', padding: '40px 24px' }}>
          <h2 style={{ fontWeight: 900, color: '#191919' }}>Applications are currently closed</h2>
          <p style={{ color: '#525252', marginTop: '10px' }}>Thank you for your interest in Solvit.</p>
        </div>
      </CenteredFrame>
    );
  }

  if (result?.result === 'eligible') {
    return (
      <CenteredFrame>
        <div data-testid="apply-eligible" style={{ textAlign: 'center', padding: '40px 24px' }}>
          <div style={{ width: '64px', height: '64px', margin: '0 auto 16px', borderRadius: '50%', backgroundColor: '#DCFCE7', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '32px', color: '#16A34A', fontWeight: 900 }}>✓</div>
          <h2 style={{ fontWeight: 900, color: '#191919' }}>You're eligible</h2>
          <p style={{ color: '#525252', marginTop: '10px', maxWidth: '440px', marginInline: 'auto' }}>{result.message}</p>
          <p style={{ color: '#191919', marginTop: '20px', fontSize: '13px' }}>
            <strong>Next:</strong> {result.next_stage}. The Solvers Manager will be in touch shortly via the email and phone number you provided.
          </p>
        </div>
      </CenteredFrame>
    );
  }

  if (result?.result === 'ineligible') {
    return (
      <CenteredFrame>
        <div data-testid="apply-ineligible" style={{ padding: '36px 24px' }}>
          <h2 style={{ fontWeight: 900, color: '#191919', fontSize: '20px', marginTop: 0 }}>{result.headline}</h2>
          <ul style={{ color: '#525252', fontSize: '13px', lineHeight: 1.7, paddingLeft: '18px' }}>
            {(result.reasons || []).map((r, i) => <li key={'r-' + i}>{r}</li>)}
          </ul>
          <p style={{ color: '#525252', fontSize: '13px', marginTop: '16px' }}>{result.closing}</p>
        </div>
      </CenteredFrame>
    );
  }

  return (
    <CenteredFrame>
      <div style={{ padding: '32px 24px' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: '#FF353F', textTransform: 'uppercase', letterSpacing: '0.15em' }}>SOLVIT</div>
          <h1 style={{ fontWeight: 900, color: '#191919', fontSize: '24px', margin: '6px 0 4px' }}>Become a Solvit Solver — Apply Now</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: 0 }}>{req.title}</p>
        </div>

        <form onSubmit={submit} data-testid="apply-form">
          {/* Honeypot — visually hidden but present in the DOM. Bots auto-fill any
              text input named like a URL field; humans never see it. */}
          <div aria-hidden="true" style={{ position: 'absolute', left: '-9999px', top: 'auto', width: '1px', height: '1px', overflow: 'hidden' }}>
            <label>
              Website URL (leave blank)
              <input
                type="text"
                tabIndex={-1}
                autoComplete="off"
                name="website_url"
                value={form.website_url}
                onChange={e => set('website_url', e.target.value)}
              />
            </label>
          </div>

          <Field label="Full name *">
            <input data-testid="f-name" required value={form.full_name} onChange={e => set('full_name', e.target.value)} style={input} />
          </Field>
          <Field label="Phone number *">
            <input data-testid="f-phone" required type="tel" pattern="^(\+?254|0)?7\d{8}$" placeholder="07XXXXXXXX or +2547XXXXXXXX" value={form.phone_number} onChange={e => set('phone_number', e.target.value)} style={input} />
          </Field>
          <Field label="Email address *">
            <input data-testid="f-email" required type="email" value={form.email} onChange={e => set('email', e.target.value)} style={input} />
          </Field>

          <Field label="Working area — county *">
            <select data-testid="f-county" required value={form.county} onChange={e => set('county', e.target.value)} style={input}>
              <option value="">Select a county…</option>
              {req.counties.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Town / area within county *">
            <input data-testid="f-town" required placeholder="e.g. Westlands, Ruaka, Mombasa CBD" value={form.town_area} onChange={e => set('town_area', e.target.value)} style={input} />
          </Field>

          <Field label="Do you hold a valid Kenyan driving licence? *">
            <RadioGroup name="licence" value={form.has_driving_licence} options={[{label:'Yes',value:true},{label:'No',value:false}]} onChange={v => set('has_driving_licence', v)} testidPrefix="f-licence" />
          </Field>

          <Field label="Relevant qualifications and experience * (select all that apply)">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {QUAL_OPTIONS.map(q => (
                <label key={q} style={{ fontSize: '13px', display: 'flex', alignItems: 'flex-start', gap: '8px', opacity: noneSelected ? 0.4 : 1 }}>
                  <input
                    data-testid={`f-qual-${q.slice(0, 12).replace(/\W/g, '')}`}
                    type="checkbox"
                    disabled={noneSelected}
                    checked={form.qualifications.includes(q)}
                    onChange={() => toggleQual(q)}
                    style={{ marginTop: '3px' }}
                  />
                  {q}
                </label>
              ))}
              <label style={{ fontSize: '13px', display: 'flex', alignItems: 'flex-start', gap: '8px', borderTop: '1px solid rgba(25,25,25,0.08)', paddingTop: '8px' }}>
                <input
                  data-testid="f-qual-none"
                  type="checkbox"
                  checked={noneSelected}
                  onChange={() => toggleQual('None of the above')}
                  style={{ marginTop: '3px' }}
                />
                None of the above
              </label>
            </div>
          </Field>

          {inspectorExperienceSelected && (
            <Field label="Provide company name *">
              <input data-testid="f-inspector-company" required value={form.previous_inspector_company} onChange={e => set('previous_inspector_company', e.target.value)} style={input} />
            </Field>
          )}

          <Field label="Do you own a smartphone with a working camera? *">
            <RadioGroup name="smartphone" value={form.has_smartphone} options={[{label:'Yes',value:true},{label:'No',value:false}]} onChange={v => set('has_smartphone', v)} testidPrefix="f-smartphone" />
          </Field>

          <Field label="Are you available during standard operating hours (Mon–Sat, 8am–6pm)? *">
            <RadioGroup name="availability" value={form.availability} options={[{label:'Yes',value:'Yes'},{label:'Partial',value:'Partial'},{label:'No',value:'No'}]} onChange={v => set('availability', v)} testidPrefix="f-availability" />
          </Field>

          <Field label="CV / Résumé (optional)">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <input
                data-testid="f-cv"
                ref={fileRef}
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={onCvChange}
                style={{ fontSize: '12px' }}
              />
              <span style={{ fontSize: '11px', color: '#525252' }}>
                PDF, DOC, or DOCX · max 5MB · {cvFile ? `selected: ${cvFile.name}` : 'no file selected'}
              </span>
              {cvError && <span data-testid="cv-error" style={{ fontSize: '11px', color: '#991B1B' }}>{cvError}</span>}
            </div>
          </Field>

          <div style={{ marginBottom: '14px', padding: '14px', backgroundColor: '#FFF7ED', border: '1px solid #FED7AA' }}>
            <strong style={{ display: 'block', marginBottom: '6px', fontSize: '13px' }}>Commission-Based Role — please read carefully before proceeding.</strong>
            <p style={{ fontSize: '12px', color: '#525252', margin: 0 }}>
              This is a commission-based position. Your earnings are directly tied to the volume and quality of inspections you complete. The more jobs you take on, the more you earn — with no ceiling on your income.
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '10px', fontSize: '13px', fontWeight: 600 }}>
              <input data-testid="f-commission" type="checkbox" required checked={form.commission_acknowledged} onChange={e => set('commission_acknowledged', e.target.checked)} />
              I understand that this is a commission-based role and I am comfortable working on this basis.
            </label>
          </div>

          <Field label="How did you hear about Solvit? *">
            <select data-testid="f-channel" required value={form.channel} onChange={e => set('channel', e.target.value)} style={input}>
              <option value="">Select…</option>
              {CHANNELS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>

          {/* Security challenge */}
          <Field label={`Security check * — ${challenge?.question || 'Loading challenge…'}`}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                data-testid="f-captcha"
                required
                inputMode="numeric"
                pattern="[0-9]*"
                placeholder="Your answer"
                value={form.challenge_answer}
                onChange={e => set('challenge_answer', e.target.value.replace(/\D/g, ''))}
                style={{ ...input, maxWidth: '160px' }}
              />
              <button data-testid="f-captcha-refresh" type="button" onClick={refreshChallenge}
                style={{ padding: '8px 12px', border: '1px solid rgba(25,25,25,0.2)', background: '#fff', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', cursor: 'pointer' }}>
                New question
              </button>
            </div>
            <span style={{ fontSize: '11px', color: '#525252', marginTop: '4px', display: 'block' }}>
              This protects the form from automated submissions.
            </span>
          </Field>

          {error && <div data-testid="apply-error" style={{ padding: '10px 12px', backgroundColor: '#FEE2E2', color: '#991B1B', fontSize: '12px', marginBottom: '12px' }}>{error}</div>}

          <button data-testid="f-submit" type="submit" disabled={submitting} style={{ width: '100%', padding: '14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', fontSize: '14px', fontWeight: 800, letterSpacing: '0.05em', cursor: 'pointer', marginTop: '8px' }}>
            {submitting ? 'Submitting…' : 'Submit Application'}
          </button>
        </form>
      </div>
    </CenteredFrame>
  );
}

const input = { width: '100%', padding: '10px 12px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '13px', boxSizing: 'border-box' };

function CenteredFrame({ children }) {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F9FAFB', padding: '20px 12px' }}>
      <div style={{ maxWidth: '560px', margin: '0 auto', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: '14px' }}>
      <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252', marginBottom: '6px' }}>{label}</label>
      {children}
    </div>
  );
}

function RadioGroup({ name, value, options, onChange, testidPrefix }) {
  return (
    <div style={{ display: 'flex', gap: '14px' }}>
      {options.map(o => (
        <label key={String(o.value)} style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <input
            data-testid={`${testidPrefix}-${String(o.label).toLowerCase()}`}
            type="radio"
            name={name}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}
