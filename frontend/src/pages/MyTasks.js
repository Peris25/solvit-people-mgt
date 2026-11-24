import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import useMyTaskQueue from '../hooks/useMyTaskQueue';

const KIND={assigned:'Assigned task',form:'Form sign-off',review:'Performance review',peer:'Peer review',alignment:'Alignment Survey',onboarding:'Checklist',leave:'Leave approval',learning:'Learning'};
export default function MyTasks() {
  const navigate=useNavigate();
  const {data,loading,error,reload}=useMyTaskQueue();
  const [busy,setBusy]=useState(''),[actionError,setActionError]=useState('');
  const tasks=data?.items||[];
  const complete=async task=>{
    setBusy(task.id);setActionError('');
    try{const result=await api.updateTask(task.reference,{status:'Completed'});if(result?.data?.status!=='Completed')throw new Error('Unconfirmed');reload();}
    catch(error){setActionError('Completion could not be confirmed. Refresh the list before retrying.');}finally{setBusy('');}
  };
  return <div data-testid="my-tasks-page" style={{fontFamily:'Arial, Helvetica, sans-serif'}}>
    <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:16,marginBottom:24}}><div><h1 style={{fontSize:32,margin:0}}>My Tasks</h1><p>Your assigned work, approvals and reviews in one place.</p></div><button type="button" disabled={loading} onClick={reload} style={{minHeight:44,padding:'8px 16px'}}>Refresh tasks</button></header>
    {(error||actionError)&&<div role="alert"><p>{error||actionError}</p><button type="button" onClick={reload}>Retry tasks</button></div>}
    {!!data?.errors?.length&&<div role="alert"><p>Some task types could not load: {data.errors.join(', ')}. The list below may be incomplete.</p><button type="button" onClick={reload}>Retry tasks</button></div>}
    {loading&&<div role="status" style={{padding:24}}>Loading your assigned tasks…</div>}
    {!loading&&data&&<><p role="status">{tasks.length} {data.errors.length?'available tasks':'open tasks'}{data.errors.length?' · Some task types are unavailable':''}</p>
      {tasks.length===0&&!data.errors.length?<div style={{background:'#fff',padding:32,border:'1px solid #e2e8f0',borderRadius:12}}>No open tasks assigned to you.</div>:tasks.length>0&&<div style={{background:'#fff',border:'1px solid #e2e8f0',borderRadius:12,overflowX:'auto'}}><table style={{width:'100%',borderCollapse:'collapse',textAlign:'left'}}><thead><tr>{['Task','Type','Employee / subject','Due','Status','Action'].map(title=><th key={title} scope="col" style={{padding:14,borderBottom:'1px solid #e2e8f0'}}>{title}</th>)}</tr></thead><tbody>{tasks.map(task=><tr key={task.id} data-testid={`mytask-${task.id}`}>
        <th scope="row" style={{padding:14,borderBottom:'1px solid #e2e8f0',minWidth:220}}>{task.title}{task.description&&<p style={{fontWeight:400,fontSize:12}}>{task.description}</p>}</th><td style={{padding:14}}>{KIND[task.kind]||task.kind}</td><td style={{padding:14}}>{task.subject||'—'}</td><td style={{padding:14,whiteSpace:'nowrap'}}>{task.due_date?new Date(task.due_date).toLocaleDateString('en-GB'):'No date set'}</td><td style={{padding:14}}>{task.status?.replaceAll('_',' ')||'Pending'}</td><td style={{padding:14,whiteSpace:'nowrap'}}>{task.path&&<button type="button" disabled={!!busy} onClick={()=>navigate(task.path)} style={{minHeight:44,padding:'8px 16px'}}>Open task</button>}{task.can_complete&&<button type="button" disabled={!!busy} onClick={()=>complete(task)} style={{minHeight:44,padding:'8px 16px',marginLeft:8}}>{busy===task.id?'Saving…':'Mark complete'}</button>}{!task.path&&!task.can_complete&&<span>Read only</span>}</td>
      </tr>)}</tbody></table></div>}</>}
  </div>;
}
