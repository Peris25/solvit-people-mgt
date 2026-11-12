import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as api from '../services/api';
import LeaveActionButton from './LeaveActionButton';

const keys = ['role_id','name','scope','goals','group_weights','notes','approval_reference','source_reference'];
const editable = row => Object.fromEntries(keys.map(key => [key, row[key]]));
const copy = row => JSON.parse(JSON.stringify(row));
const control = { width: '100%', minHeight: 44, padding: 10, border: '1px solid #cbd5e1', borderRadius: 8, boxSizing: 'border-box', font: 'inherit' };
const field = { display: 'grid', gap: 5 };
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 12 };
const errorText = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e.message || 'Unable to save. Your edits are still here.';

export default function RoleKpiLibrary() {
  const [roles,setRoles] = useState([]), [selected,setSelected] = useState(''), [saved,setSaved] = useState(null), [values,setValues] = useState(null);
  const [conflict,setConflict] = useState(false);
  const [loading,setLoading] = useState(true), [busy,setBusy] = useState(false), [error,setError] = useState(''), [message,setMessage] = useState(''), [reason,setReason] = useState('');
  const live = useRef(true), saving = useRef(false);
  const dirty = values && JSON.stringify(values) !== JSON.stringify(saved && editable(saved));
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await api.getRoleKpiLibrary();
      if (!Array.isArray(response.data?.roles)) throw new Error('Unable to load the role KPI library.');
      if (live.current) { const list=response.data.roles; setRoles(list); setSelected(list[0]?.role_id || ''); setSaved(list[0] || null); setValues(list[0] ? copy(editable(list[0])) : null); }
    } catch(e) { if(live.current) setError(errorText(e)); }
    finally { if(live.current) setLoading(false); }
  },[]);
  useEffect(() => { live.current=true; load(); return () => {live.current=false;}; },[load]);
  const save = useCallback(async action => {
    if (!values || saving.current) return false;
    saving.current=true; setBusy(true); setError(''); setMessage(action==='publish'?'Publishing...':'Saving draft...');
    try {
      const response=await api.saveRoleKpis(selected,{entry:copy(values),action,expected_version:saved?.version || null,reason});
      if(!response.data?.version || response.data.role_id!==selected) throw new Error('Save could not be confirmed. Your edits are still here.');
      if(live.current) {setSaved(response.data);setValues(current=>JSON.stringify(current)===JSON.stringify(values)?copy(editable(response.data)):current);setRoles(list=>list.map(row=>row.role_id===selected?response.data:row));setMessage(action==='publish'?'Published with approval.':'Draft saved. You can return to it next time you sign in.');}
      return true;
    } catch(e) {if(live.current){if(e.response?.status===409)setConflict(true);setError(errorText(e));setMessage('Not saved. Your typed changes are still here.');}return false;}
    finally {saving.current=false;if(live.current)setBusy(false);}
  },[values,selected,saved,reason]);
  useEffect(() => {
    if(!dirty || busy || error || conflict) return;
    const timer=setTimeout(()=>save('draft'),1200);
    return ()=>clearTimeout(timer);
  },[dirty,busy,error,conflict,save]);
  useEffect(()=>{
    const warn=event=>{if(dirty || saving.current){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[dirty]);
  const change=(key,value)=>{setError('');setValues(v=>({...v,[key]:value}));setMessage('Unsaved changes');};
  const goalChange=(index,key,value)=>{setError('');setValues(v=>({...v,goals:v.goals.map((g,i)=>i===index?{...g,[key]:value}:g)}));setMessage('Unsaved changes');};
  const choose=async event=>{
    const id=event.target.value;
    if(saving.current)return;
    if(dirty && !await save('draft'))return;
    const row=roles.find(r=>r.role_id===id);
    if(row){setSelected(id);setSaved(row);setValues(copy(editable(row)));setReason('');setMessage('');setError('');}
  };
  const discardAndReload=async()=>{
    setBusy(true);
    try {
      const response=await api.getRoleKpiLibrary();
      const row=response.data?.roles?.find(r=>r.role_id===selected);
      if(!row)throw new Error('Unable to reload this role. Your edits are still here.');
      if(live.current){setRoles(response.data.roles);setSaved(row);setValues(copy(editable(row)));setConflict(false);setReason('');setError('');setMessage('Latest saved version loaded.');}
    }catch(e){if(live.current)setError(errorText(e));}
    finally{if(live.current)setBusy(false);}
  };
  const newRole=async()=>{
    if(saving.current || (dirty && !await save('draft')))return;
    const id='role-'+crypto.randomUUID();
    const row={role_id:id,name:'New role',scope:'Unconfirmed',goals:[],group_weights:{},notes:'',approval_reference:'',source_reference:'HR-created role template',status:'Draft',version:null,issues:[],has_published_version:false};
    setRoles(list=>[...list,row]);setSelected(id);setSaved(row);setValues(copy(editable(row)));setReason('');setMessage('Enter the role name and KPIs, then save the draft.');setError('');
  };
  if(loading)return <section><h2>Role KPI library</h2><p role="status">Loading role KPIs...</p></section>;
  if(!values)return <section><h2>Role KPI library</h2><p role="alert">{error || 'No role templates available.'}</p><LeaveActionButton onClick={load}>Retry</LeaveActionButton></section>;
  const sum=rows=>rows.reduce((total,g)=>total+Number(g.weight||0),0);
  return <section data-testid="role-kpi-library" style={{background:'#fff',padding:20,borderRadius:12,marginBottom:20}}>
    <h2 style={{marginTop:0}}>Role KPI library</h2>
    <p>Choose a role, edit its KPIs and save. Drafts can be incomplete. Publishing requires confirmed targets, weights and an approval reference.</p>
    <div style={{...grid,alignItems:'end'}}><label style={field}>Role<select aria-label="KPI role" style={control} value={selected} disabled={busy} onChange={choose}>{roles.map(row=><option key={row.role_id} value={row.role_id}>{row.name} - {row.status}</option>)}</select></label><LeaveActionButton disabled={busy} onClick={newRole}>Add role</LeaveActionButton></div>
    <p><strong>{saved?.status || 'Draft'}</strong>{saved?.updated_at ? ' - Last saved '+new Date(saved.updated_at).toLocaleString() : ' - Reference draft, not yet saved'}</p>
    <p role="note">This library prepares the approved KPIs for the V3 review process. Publishing here does not change existing employee reviews or scores.</p>
    {error && <p role="alert">{error}</p>}
    {conflict && <div role="alert"><p>Another HR user saved this role. Your edits have been kept on screen. Review them before discarding and loading the latest saved version.</p><LeaveActionButton disabled={busy} onClick={discardAndReload}>Discard my edits and load latest</LeaveActionButton></div>}
    {saved?.has_published_version && <p>Changes to approved KPIs need a change reason before they can be saved.</p>}
    {message && <p role="status">{dirty && (message.startsWith('Draft saved') || message.startsWith('Published with')) ? 'Newer edits are not saved yet.' : message}</p>}
    <form noValidate onSubmit={event=>{event.preventDefault();save('draft');}}>
      <div style={grid}>
        <label style={field}>Role name<input aria-label="Role name" style={control} maxLength={250} value={values.name} onChange={e=>change('name',e.target.value)} /></label>
        <label style={field}>Use for<select style={control} aria-label="KPI review scope" value={values.scope} onChange={e=>change('scope',e.target.value)}>{['Annual','Probation','Board','Reference','Unconfirmed'].map(scope=><option key={scope}>{scope}</option>)}</select></label>
      </div>
      <label style={{...field,marginTop:12}}>Notes and items to confirm<textarea aria-label="Role notes" style={control} maxLength={1500} value={values.notes} onChange={e=>change('notes',e.target.value)} /></label>
      {!!Object.keys(values.group_weights).length && <div><h3>Weight between KPI groups</h3><p>Each group's own KPIs must total 100%. Set the overall split between the groups below.</p><div style={grid}>{Object.entries(values.group_weights).map(([name,value])=><label key={name} style={field}>{name} (%)<input aria-label={`${name} group weight`} style={control} type="number" min="0" max="100" step="0.01" value={value??''} onChange={e=>change('group_weights',{...values.group_weights,[name]:e.target.value===''?null:Number(e.target.value)})} /></label>)}</div></div>}
      <h3>KPIs ({values.goals.length})</h3>
      <p>{Object.keys(values.group_weights).length?Object.keys(values.group_weights).map(group=>`${group}: ${sum(values.goals.filter(g=>g.group===group)).toFixed(2)}%`).join(' | '):`Total KPI weight: ${sum(values.goals).toFixed(2)}%`}</p>
      {values.goals.map((goal,index)=><details key={goal.id} open={index===0 || !goal.objective ? true : undefined} style={{border:'1px solid #e2e8f0',borderRadius:10,padding:14,marginBottom:14}}>
        <summary style={{cursor:'pointer',fontWeight:700,minHeight:32}}>KPI {index+1} - {goal.objective || 'New KPI'} ({goal.weight ?? 'Unconfirmed'}%)</summary>
        <fieldset style={{border:0,padding:'14px 0 0',margin:0}}><legend style={{position:'absolute',width:1,height:1,overflow:'hidden'}}>Edit KPI {index+1}</legend>
        <div style={grid}>
          {[['objective','KPI / objective'],['metric','How it is measured'],['target','Target description'],['unit','Unit'],['data_source','Data source'],['owner','Owner / role']].map(([key,label])=><label key={key} style={field}>{label}<input aria-label={`${label} ${index+1}`} style={control} value={goal[key]} maxLength={['metric','target'].includes(key)?1500:500} onChange={e=>goalChange(index,key,e.target.value)} /></label>)}
          <label style={field}>Scoring method<select aria-label={`Scoring method ${index+1}`} style={control} value={goal.direction} onChange={e=>goalChange(index,'direction',e.target.value)}>{[['Unconfirmed','Needs confirmation'],['Higher','Higher is better'],['Lower','Lower is better'],['Binary','Done / not done'],['Rated','Manager rating 1-3']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
          <label style={field}>Numeric target<input aria-label={`Numeric target ${index+1}`} style={control} type="number" min="0" step="any" value={goal.target_value??''} onChange={e=>goalChange(index,'target_value',e.target.value===''?null:Number(e.target.value))} /></label>
          <label style={field}>Weight (%)<input aria-label={`KPI weight ${index+1}`} style={control} type="number" min="0" max="100" step="0.01" value={goal.weight??''} onChange={e=>goalChange(index,'weight',e.target.value===''?null:Number(e.target.value))} /></label>
          {!!Object.keys(values.group_weights).length && <label style={field}>Group<select aria-label={`KPI group ${index+1}`} style={control} value={goal.group} onChange={e=>goalChange(index,'group',e.target.value)}><option value="">Choose group</option>{Object.keys(values.group_weights).map(group=><option key={group}>{group}</option>)}</select></label>}
        </div>
        <label style={{...field,marginTop:10}}>KPI notes<textarea aria-label={`KPI notes ${index+1}`} style={control} maxLength={1500} value={goal.notes} onChange={e=>goalChange(index,'notes',e.target.value)} /></label>
        <LeaveActionButton disabled={busy} onClick={()=>change('goals',values.goals.filter((_,i)=>i!==index))}>Remove KPI {index+1}</LeaveActionButton>
      </fieldset></details>)}
      <LeaveActionButton disabled={busy || values.goals.length>=100} onClick={()=>change('goals',[...values.goals,{id:crypto.randomUUID(),objective:'',metric:'',target:'',target_value:null,weight:null,direction:'Unconfirmed',unit:'',data_source:'',owner:values.name,group:'',notes:''}])}>Add KPI</LeaveActionButton>
      <div style={{...grid,marginTop:16}}>
        <label style={field}>MD / line-manager approval reference<input aria-label="KPI approval reference" style={control} maxLength={1500} value={values.approval_reference} onChange={e=>change('approval_reference',e.target.value)} /></label>
        <label style={field}>Reason for changes to an approved role<textarea aria-label="KPI change reason" style={control} maxLength={1500} value={reason} onChange={e=>{setReason(e.target.value);setError('');}} /></label>
      </div>
      {saved?.issues?.length>0 && <details style={{marginTop:14}}><summary>What needs completing before publishing ({saved.issues.length})</summary><ul>{saved.issues.map((issue,i)=><li key={i}>{issue}</li>)}</ul></details>}
      <div style={{display:'flex',gap:10,flexWrap:'wrap',marginTop:18}}>
        <LeaveActionButton type="submit" variant="primary" disabled={busy || conflict}>Save draft</LeaveActionButton>
        <LeaveActionButton disabled={busy || conflict} onClick={()=>save('publish')}>Publish approved KPIs</LeaveActionButton>
      </div>
      <p style={{fontSize:12}}>Changes auto-save as a draft after you stop typing. Wait for the saved message before leaving. Source: {values.source_reference}</p>
    </form>
  </section>;
}
