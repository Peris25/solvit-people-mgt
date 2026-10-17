import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import * as api from '../services/api';
const names={management:'Management meeting summary',probation_dates:'Recorded probation end dates',contract_dates:'Recorded contract end dates',employees:'Employees & hire cohorts',leave:'Leave requests',leave_balances:'Recorded leave balances',onboarding:'Onboarding progress',performance:'Performance review progress',training:'Training participation',benefits:'Benefits participation'};
const columns=['report_kind','date_basis','employee_name','department','role_title','work_email','employment_type','status','start_date','end_date','last_working_day','probation_end_date','contract_end_date','line_manager_name','working_days','leave_type','year','annual_remaining','sick_remaining','task_key','assigned_role','due_date','completed_at','cycle_type','cycle_year','overall_score','rating','training_name','proposed_start_date','proposed_end_date','due_on','completed_on','duration_days','scheme_title','cover_level','created_at','reviewed_at','count'];
const auditColumns=['timestamp','event','module','actor_name','source','target_reference'];
const empty={date_from:'',date_to:'',department:'',status:'',event_type:'',module:'',actor:''};
const button={minHeight:44,padding:'8px 14px',cursor:'pointer'};
const errorMessage=e=>typeof e.response?.data?.detail==='string'?e.response.data.detail:'Reporting is unavailable. Please retry.';
export default function Reporting(){
 const {user}=useAuth(); const identity=`${user?.id}:${user?.role}:${user?.employee_id}`;const current=useRef(identity);current.current=identity;const version=useRef(0);
 const [refresh,setRefresh]=useState(0);const [catalogue,setCatalogue]=useState(null);const [catalogueFor,setCatalogueFor]=useState('');const [tab,setTab]=useState('reports');const [kind,setKind]=useState('');
 const [draft,setDraft]=useState(empty);const [filters,setFilters]=useState(empty);const [offset,setOffset]=useState(0);const [data,setData]=useState(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;setCatalogueFor('');setCatalogue(null);setData(null);setError('');setDraft(empty);setFilters(empty);setOffset(0);
  api.getReportingCatalogue().then(response=>{if(!active||current.current!==identity)return;setCatalogue(response.data);setKind(response.data.reports[0]?.id||'');setTab(response.data.reports.length?'reports':'audit');setCatalogueFor(identity);}).catch(e=>{if(active&&current.current===identity){setError(errorMessage(e));setCatalogueFor(identity);}});
  return()=>{active=false;};
 },[identity,refresh]);
 const params=useCallback(()=>Object.fromEntries(Object.entries(filters).filter(([key,value])=>value&&(tab==='audit'?['date_from','date_to','event_type','module','actor'].includes(key):['date_from','date_to','department','status'].includes(key)))),[filters,tab]);
 const load=useCallback(async()=>{
  if(catalogueFor!==identity||!catalogue||(tab==='audit'?!catalogue.can_audit:!kind))return;
  const request=++version.current;setData(null);setError('');
  try{const response=await (tab==='audit'?api.getAdministrativeAudit({...params(),offset,limit:50}):api.getAdministrativeReport(kind,{...params(),offset,limit:50}));if(current.current===identity&&request===version.current)setData(response.data);}
  catch(e){if(current.current===identity&&request===version.current)setError(errorMessage(e));}
 },[catalogueFor,identity,catalogue,tab,kind,params,offset]);
 useEffect(()=>{load();},[load]);
 const download=async format=>{setBusy(true);setError('');try{const response=await api.exportAdministrativeReport(kind,format,params());if(current.current!==identity)return;const url=URL.createObjectURL(response.data);const anchor=document.createElement('a');anchor.href=url;anchor.download=`${kind}.${format}`;anchor.click();URL.revokeObjectURL(url);}catch(e){if(current.current===identity)setError(errorMessage(e));}finally{if(current.current===identity)setBusy(false);}};
 if(catalogueFor!==identity)return <p role="status">Loading reporting permissions...</p>;
 const allowed=catalogue&&(catalogue.reports.length||catalogue.can_audit);
 if(!allowed)return <div><h1>Reports & audit</h1>{error?<p role="alert">{error} <button style={button} onClick={()=>setRefresh(value=>value+1)}>Retry permissions</button></p>:<p>No administrative reports are authorized for this account.</p>}</div>;
 const fields=tab==='audit'?auditColumns:columns.filter(key=>data?.items?.some(row=>Object.prototype.hasOwnProperty.call(row,key)));
 return <div data-testid="reporting-page" style={{fontFamily:'Arial, Helvetica, sans-serif'}}><h1>Reports & audit</h1>
  <div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:16}}>{catalogue.reports.length>0&&<button style={button} onClick={()=>{setTab('reports');setOffset(0);}}>Operational reports</button>}{catalogue.can_audit&&<button style={button} onClick={()=>{setTab('audit');setOffset(0);}}>Administrative audit</button>}</div>
  {tab==='reports'&&<label>Report <select value={kind} onChange={e=>{setKind(e.target.value);setOffset(0);}}>{catalogue.reports.map(report=><option key={report.id} value={report.id}>{names[report.id]||report.id}{report.summary_only?' (aggregate)':''}</option>)}</select></label>}
  <form onSubmit={e=>{e.preventDefault();setFilters({...draft});setOffset(0);}} style={{display:'flex',flexWrap:'wrap',alignItems:'end',gap:12,margin:'16px 0'}}>
   {['date_from','date_to'].map(key=><label key={key} style={{display:'grid',gap:5}}>{key==='date_from'?'From date':'To date'}<input type="date" value={draft[key]} onChange={e=>setDraft(previous=>({...previous,[key]:e.target.value}))}/></label>)}
   {(tab==='reports'?['department','status']:['event_type','module']).map(key=><label key={key} style={{display:'grid',gap:5}}>{key.replaceAll('_',' ')}<input value={draft[key]} onChange={e=>setDraft(previous=>({...previous,[key]:e.target.value}))} list={key==='department'?'report-departments':undefined}/></label>)}
   <datalist id="report-departments">{(data?.departments||[]).map(value=><option key={value} value={value}/>)}</datalist>
   {tab==='audit'&&<label style={{display:'grid',gap:5}}>Authorized actor<select value={draft.actor} onChange={e=>setDraft(previous=>({...previous,actor:e.target.value}))}><option value="">All authorized actors</option>{draft.actor&&!(data?.actors||[]).some(actor=>actor.id===draft.actor)&&<option value={draft.actor}>Selected historical actor</option>}{(data?.actors||[]).map(actor=><option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label>}
   <button style={button}>Apply filters</button><button type="button" style={button} onClick={()=>{setDraft(empty);setFilters(empty);setOffset(0);}}>Clear filters</button>
  </form>
  {error&&<p role="alert">{error} <button style={button} onClick={load}>Retry</button></p>}
  {tab==='reports'&&<div style={{display:'flex',gap:8}}><button style={button} disabled={busy||!data} onClick={()=>download('xlsx')}>Download Excel</button><button style={button} disabled={busy||!data} onClick={()=>download('csv')}>Download CSV</button></div>}
  {!data&&!error?<p role="status">Loading authorized records...</p>:data&&<><p>{data.total} authorized records{data.summary_only?' / aggregate view':''}. {data.scope&&`Scope: ${data.scope.replaceAll('_',' ')}.`} {data.date_basis&&`Date filter uses ${data.date_basis.replaceAll('_',' ')}.`}</p><p>{data.notice}</p>{data.missing_dates>0&&<p>{data.missing_dates} authorized records have no usable historical date.</p>}{data.unresolved_records>0&&<p>{data.unresolved_records} records need employee identity reconciliation.</p>}
   {data.items.length===0?<p>No authorized records match these filters.</p>:<div style={{overflowX:'auto',background:'#fff'}}><table style={{borderCollapse:'collapse',width:'100%',fontSize:13}}><thead><tr>{fields.map(key=><th key={key} style={{textAlign:'left',padding:12,borderBottom:'2px solid #FF353F'}}>{key.replaceAll('_',' ')}</th>)}</tr></thead><tbody>{data.items.map((row,index)=><tr key={row.id||row.record_id||`${offset}:${index}`}>{fields.map(key=><td key={key} style={{padding:12,borderBottom:'1px solid #ddd'}}>{typeof row[key]==='string'||typeof row[key]==='number'?row[key]:'Not recorded'}</td>)}</tr>)}</tbody></table></div>}
   <div style={{display:'flex',gap:8,marginTop:16}}><button style={button} disabled={!offset} onClick={()=>setOffset(value=>Math.max(0,value-50))}>Previous</button><button style={button} disabled={offset+50>=data.total} onClick={()=>setOffset(value=>value+50)}>Next</button></div>
  </>}
 </div>;
}
