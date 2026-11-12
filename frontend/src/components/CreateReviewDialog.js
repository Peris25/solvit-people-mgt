import React, { useEffect, useRef, useState } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

const control = { width:'100%', padding:'11px 12px', minHeight:44, border:'1px solid #cbd5e1', borderRadius:9, font:'inherit', boxSizing:'border-box', background:'#fff' };
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone:'Africa/Nairobi', year:'numeric',month:'2-digit',day:'2-digit' }).format(new Date());
const state = employee => String(employee.lifecycle_state || employee.status || '').toLowerCase().replace(/[^a-z]/g,'');
export default function CreateReviewDialog({ employees, onClose, onCreated, probationOnly = false }) {
  const [values,setValues] = useState({ employee_id:'', cycle_type:probationOnly ? 'Probation' : 'Year_End', starts_on:today(), self_due_on:'', manager_due_on:'', review_due_on:'', review_month:1, policy:'', policy_confirmed:false });
  const [error,setError] = useState(''); const [busy,setBusy] = useState(false); const first=useRef(null);
  const probation = values.cycle_type === 'Probation';
  const eligible = employees.filter(e => probation ? ['onboarding','probation'].includes(state(e)) || e.onboarding_recorded_status === 'In_Progress' : ['active','onboarding','probation','onleave','pip'].includes(state(e)));
  const change = (key,value) => setValues(v=>({...v,[key]:value}));
  useEffect(()=>{ const previous=document.activeElement; first.current?.focus(); return ()=>previous?.focus?.(); },[]);
  const submit = async e => { e.preventDefault(); setError(''); setBusy(true); try {
    const { review_month, policy, policy_confirmed, ...base }=values;
    const payload={...base,cycle_year:Number(values.starts_on.slice(0,4)),...(probation ? {review_month:Number(review_month)} : {policy,policy_confirmed})};
    const result=await api.createReview(payload);
    if(!result?.data?.id) throw new Error('Review creation could not be confirmed. Refresh before retrying.');
    await onCreated(result.data);
  }catch(e){ setError(typeof e.response?.data?.detail==='string'?e.response.data.detail:e.message || 'Unable to create review.'); }finally{setBusy(false);} };
  return <div role="dialog" aria-modal="true" aria-labelledby="create-review-title" onKeyDown={e=>{if(e.key==='Escape'&&!busy)onClose(); if(e.key==='Tab'){const items=[...e.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')];const edge=e.shiftKey?items[0]:items[items.length-1];if(document.activeElement===edge){e.preventDefault();(e.shiftKey?items[items.length-1]:items[0])?.focus();}}}} style={{position:'fixed',inset:0,background:'#0f172a80',zIndex:110,display:'flex',alignItems:'center',justifyContent:'center',padding:16}}>
    <form onSubmit={submit} style={{width:'100%',maxWidth:700,maxHeight:'92vh',overflowY:'auto',background:'#fff',borderRadius:20,padding:24,boxShadow:'0 20px 60px #0003',boxSizing:'border-box'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><h2 id="create-review-title">Create employee review</h2><button type="button" aria-label="Close create review" disabled={busy} onClick={onClose} style={{...control,width:64}}>Close</button></div>
      <p>Select the employee, review type and deadlines. Creating sends the review to the employee.</p>
      {error&&<p role="alert" style={{padding:12,background:'#fff1f2',color:'#9f1239',borderRadius:8}}>{error}</p>}
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:16}}>
        <label>Review type<select ref={first} style={control} aria-label="Review type" value={values.cycle_type} onChange={e=>setValues(v=>({...v,cycle_type:e.target.value,employee_id:'',policy_confirmed:false}))}>{!probationOnly && <><option value="Year_End">Year-end review</option><option value="Mid_Year">Mid-year review</option></>}<option value="Probation">Probation Review</option></select></label>
        <label>Employee<select style={control} aria-label="Review employee" required value={values.employee_id} onChange={e=>change('employee_id',e.target.value)}><option value="">Select employee</option>{eligible.map(e=><option key={e.id} value={e.id}>{e.full_name} - {e.role_title}</option>)}</select></label>
        {probation&&<label>Probation review month<select aria-label="Probation review month" style={control} value={values.review_month} onChange={e=>change('review_month',Number(e.target.value))}><option value={1}>Month 1</option><option value={2}>Month 2</option><option value={3}>Month 3 (final)</option></select></label>}
        {[['starts_on','Review start'],['self_due_on','Employee submission deadline'],['manager_due_on','Manager submission deadline'],['review_due_on','HR completion deadline']].map(([key,label])=><label key={key}>{label}<input style={control} aria-label={label} required type="date" min={key==='starts_on'?undefined:values.starts_on||today()} value={values[key]} onChange={e=>change(key,e.target.value)} /></label>)}
      </div>
      {probation ? <p style={{padding:12,background:'#f1f5f9',borderRadius:9}}>For employees still in onboarding or probation. Uses qualitative probation ratings; no weighted annual score or automatic employment-status change.</p> : <div style={{marginTop:18,padding:16,background:'#f8fafc',borderRadius:12}}>
        <label>Scoring policy<select style={control} aria-label="Review scoring policy" required value={values.policy} onChange={e=>setValues(v=>({...v,policy:e.target.value,policy_confirmed:false}))}><option value="">Select HR-approved policy</option><option value="handbook_frd">Handbook / FRD - 50 / 30 / 20, Client Feedback</option><option value="developer_brief">Developer Brief - 60 / 25 / 15, Alignment</option></select></label>
        <p>The source documents use different weights. Confirm the policy HR approves for this review. Deadlines must fit within four weeks.</p>
        <label><input type="checkbox" required checked={values.policy_confirmed} onChange={e=>change('policy_confirmed',e.target.checked)} /> I approve the selected scoring policy for this review.</label>
      </div>}
      {probation&&!eligible.length&&<p role="status">No employees currently recorded in onboarding or probation. HR must verify their status before creating a probation review.</p>}
      <div style={{display:'flex',gap:12,justifyContent:'flex-end',marginTop:24}}><LeaveActionButton disabled={busy} onClick={onClose}>Cancel</LeaveActionButton><LeaveActionButton type="submit" variant="primary" disabled={busy||!eligible.length}>{busy?'Creating...':'Create Review'}</LeaveActionButton></div>
    </form>
  </div>;
}
