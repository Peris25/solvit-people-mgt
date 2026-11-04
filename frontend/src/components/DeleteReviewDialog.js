import React,{useEffect,useRef,useState} from 'react';
import {deleteDraftReviews} from '../services/performanceDeletion';
import LeaveActionButton from './LeaveActionButton';
export default function DeleteReviewDialog({reviews,onClose,onDeleted}) {
 const first=useRef(null);
 useEffect(()=>{const previous=document.activeElement;first.current?.focus();return()=>previous?.focus?.();},[]);
 const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 return <div role="dialog" aria-modal="true" aria-labelledby="delete-review-title" onKeyDown={e=>{if(e.key==='Escape'&&!busy)onClose();if(e.key==='Tab'){const elements=[...e.currentTarget.querySelectorAll('button:not(:disabled),textarea,input')];if(document.activeElement===(e.shiftKey?elements[0]:elements[elements.length-1])){e.preventDefault();(e.shiftKey?elements[elements.length-1]:elements[0])?.focus();}}}} style={{position:'fixed',inset:0,background:'#0f172a80',display:'flex',alignItems:'center',justifyContent:'center',padding:16,zIndex:120}}>
  <form style={{background:'#fff',borderRadius:18,padding:24,width:'100%',maxWidth:580,maxHeight:'90vh',overflowY:'auto'}} onSubmit={async e=>{e.preventDefault();if(!confirmed||reason.trim().length<10)return;setBusy(true);setError('');try{const result=await deleteDraftReviews(reviews.map(r=>({id:r.id,version:r.delete_version})),reason.trim());if(!Array.isArray(result?.data?.deleted)||result.data.deleted.length!==reviews.length)throw new Error('Deletion could not be confirmed. Refresh before retrying.');await onDeleted();}catch(e){setError(typeof e.response?.data?.detail==='string'?e.response.data.detail:e.message||'Reviews could not be deleted.');}finally{setBusy(false);}}}>
   <h2 id="delete-review-title">Delete {reviews.length===1?'draft review':`${reviews.length} draft reviews`}?</h2>
   <p>These unsubmitted reviews and their linked portal notifications and tasks will be removed. Other reviews and employee records are unaffected.</p>
   <ul>{reviews.map(r=><li key={r.id}>{r.employee_name||'Employee'} - {r.cycle_type?.replaceAll('_',' ')} {r.cycle_year}{r.review_month?` / Month ${r.review_month}`:''}</li>)}</ul>
   {error&&<p role="alert" style={{color:'#b91c1c'}}>{error}</p>}
   <label style={{display:'grid',gap:8}}>Reason<textarea ref={first} aria-label="Review deletion reason" required minLength={10} maxLength={1500} value={reason} onChange={e=>setReason(e.target.value)} style={{padding:12,border:'1px solid #cbd5e1',borderRadius:8}}/></label>
   <label style={{display:'block',margin:'16px 0'}}><input type="checkbox" required checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I confirm deletion of the reviews listed above and their related portal alerts.</label>
   <div style={{display:'flex',gap:12,justifyContent:'flex-end'}}><LeaveActionButton disabled={busy} onClick={onClose}>Cancel</LeaveActionButton><LeaveActionButton type="submit" variant="danger" disabled={busy||!confirmed||reason.trim().length<10}>{busy?'Deleting...':'Delete reviews'}</LeaveActionButton></div>
  </form>
 </div>;
}
