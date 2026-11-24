import React,{useMemo,useRef,useState} from 'react';
import {Expand,Focus,Minus,Plus,RotateCcw,Users} from 'lucide-react';
import {CARD_WIDTH,layoutOrgChart,reportingIssue,wrapOrgText} from '../utils/orgChartLayout';
import './EmployeeOrgChart.css';

const initials=name=>String(name||'?').trim().split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase();
const palette=['#edf3ff','#eef7f0','#fff2e8','#f3effb'];
const avatarFill=node=>palette[Array.from(node.department||'').reduce((sum,char)=>sum+char.charCodeAt(0),0)%palette.length];

export function OrgChartDrawing({graph,collapsed=new Set(),selected,onSelect=()=>{}}){
  return <svg xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Employee reporting organogram" viewBox={`0 0 ${graph.width} ${graph.height}`} className="employee-org-svg">
    <title>Solvit employee reporting organogram</title>
    <rect width={graph.width} height={graph.height} fill="#fbfcfe" rx="12"/>
    <g fill="none" stroke="#b4bfce" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      {graph.edges.map(edge=><path key={`${edge.from}:${edge.to}`} d={edge.d} data-from={edge.from} data-to={edge.to}/>)}
    </g>
    {graph.nodes.map(item=>{
      if(item.isBoard)return <g key={item.key} transform={`translate(${item.x},${item.y})`}><rect width="174" height="50" rx="12" fill="#232936"/><text x="87" y="30" textAnchor="middle" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#fff">Board of Directors</text></g>;
      const {node,x,y,key}=item,reports=node.direct_reports||[],issue=reportingIssue(node),dark=item.isRoot;
      const name=wrapOrgText(node.name||'Name unavailable',23),role=wrapOrgText(node.role_title||'Title not recorded',32,item.height>90?2:1);
      const reportCount=node.direct_report_count??reports.length;
      const label=`${node.name||'Employee'}, ${node.role_title||'Title not recorded'}${node.department_label||node.department?`, ${node.department_label||node.department}`:''}${reportCount?`, ${reportCount} direct reports`:''}${issue?`, ${issue}`:''}`;
      return <g key={key} transform={`translate(${x},${y})`} className="employee-org-person" role="button" tabIndex={0} aria-label={label} aria-expanded={reports.length?!collapsed.has(key):undefined} data-testid={`org-node-${node.id}`}
        onClick={()=>onSelect(item)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(item);}}}>
        <title>{label}</title>
        <rect className="employee-org-card" width={CARD_WIDTH} height={item.height} rx="12" fill={dark?'#232936':'#fff'} stroke={selected===key?'#d92336':dark?'#232936':'#dce2eb'} strokeWidth={selected===key?2.5:1}/>
        {!dark&&reports.length>0&&<path d={`M12,1 H${CARD_WIDTH-12}`} stroke="#d92336" strokeWidth="3" strokeLinecap="round"/>}
        <circle cx="29" cy="30" r="15" fill={dark?'#d92336':avatarFill(node)}/>
        <text x="29" y="34" textAnchor="middle" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill={dark?'#fff':'#475569'}>{initials(node.name)}</text>
        <text x="52" y={name.length>1?25:32} fontFamily="Arial,sans-serif" fontSize="12" fontWeight="700" fill={dark?'#fff':'#202936'}>{name.map((line,i)=><tspan key={i} x="52" dy={i?15:0}>{line}</tspan>)}</text>
        <text x="14" y="65" fontFamily="Arial,sans-serif" fontSize="10.5" fill={dark?'#d3d9e4':'#5b677b'}>{role.map((line,i)=><tspan key={i} x="14" dy={i?14:0}>{line}</tspan>)}</text>
        {item.height>90&&<text x="14" y="103" fontFamily="Arial,sans-serif" fontSize="9" fill={dark?'#b6c1d2':'#7b8798'}>{wrapOrgText(node.department_label||node.department||'',reports.length?24:32,1)[0]}</text>}
        {issue&&<circle cx={CARD_WIDTH-10} cy={item.height-12} r="4" fill="#c48721"/>}
        {reports.length>0&&!issue&&<g aria-hidden="true"><rect x={CARD_WIDTH-36} y="89" width="25" height="19" rx="6" fill={dark?'#424b5c':'#f1f4f8'}/><text x={CARD_WIDTH-23.5} y="102" textAnchor="middle" fontFamily="Arial,sans-serif" fontSize="10" fill={dark?'#fff':'#475569'}>{collapsed.has(key)?'+':'−'}{reportCount}</text></g>}
      </g>;
    })}
  </svg>;
}

export default function EmployeeOrgChart({roots,sourceRoots=roots,onWholeCompany=()=>{}}){
  const [collapsed,setCollapsed]=useState(new Set()),[selected,setSelected]=useState(null),[focus,setFocus]=useState(null),[zoom,setZoom]=useState(1);
  const panel=useRef(null);
  const graph=useMemo(()=>layoutOrgChart(focus?[focus]:roots,collapsed),[roots,collapsed,focus]);
  const select=item=>{
    setSelected(item);
    if(item.node.direct_reports?.length)setCollapsed(previous=>{const next=new Set(previous);if(next.has(item.key))next.delete(item.key);else next.add(item.key);return next;});
  };
  const reset=()=>{setFocus(null);setSelected(null);setCollapsed(new Set());setZoom(1);onWholeCompany();};
  const fullTeam=node=>{
    const matches=[];
    const visit=records=>records.forEach(record=>{if(node.node_id?record.node_id===node.node_id:record.id===node.id)matches.push(record);visit(record.direct_reports||[]);});
    visit(sourceRoots);return matches.length===1?matches[0]:node;
  };
  return <section className="employee-org-panel" ref={panel} aria-label="Interactive employee organogram">
    <div className="employee-org-toolbar"><div><span className="employee-org-eyebrow">SOLVIT PEOPLE</span><h2>{focus?`${focus.name}'s team`:'Employee organogram'}</h2><p>Click a manager to expand or collapse their team.</p></div>
      <div className="employee-org-controls">
        <button type="button" onClick={reset}><RotateCcw size={15} aria-hidden="true"/>Whole company</button>
        <div className="employee-org-zoom"><button type="button" aria-label="Zoom out" disabled={zoom<=1} onClick={()=>setZoom(value=>Math.max(1,value-.25))}><Minus size={16}/></button><button type="button" onClick={()=>setZoom(1)}>Fit chart</button><button type="button" aria-label="Zoom in" disabled={zoom>=2} onClick={()=>setZoom(value=>Math.min(2,value+.25))}><Plus size={16}/></button></div>
        <button type="button" aria-label="Open chart fullscreen" onClick={()=>{const request=panel.current?.requestFullscreen?.();request?.catch(()=>{});}}><Expand size={16} aria-hidden="true"/></button>
      </div>
    </div>
    <div className="employee-org-canvas" style={{overflowX:zoom>1?'auto':'hidden'}}><div style={{width:`${zoom*100}%`,maxWidth:graph.width*zoom,margin:'0 auto'}}><OrgChartDrawing graph={graph} collapsed={collapsed} selected={selected?.key} onSelect={select}/></div></div>
    {selected&&<div className="employee-org-selection" aria-live="polite"><div><strong>{selected.node.name}</strong><span>{selected.node.role_title}</span><span>{selected.node.department_label||selected.node.department}</span><span>{selected.node.line_manager_name?`Reports to ${selected.node.line_manager_name}`:'Reporting root'}{selected.node.direct_reports?.length?` · ${selected.node.direct_report_count??selected.node.direct_reports.length} direct reports`:''}</span>{reportingIssue(selected.node)&&<span className="employee-org-warning">{reportingIssue(selected.node)}</span>}</div>{selected.node.direct_reports?.length>0&&<button type="button" onClick={()=>{setFocus(fullTeam(selected.node));setCollapsed(new Set());setSelected(null);setZoom(1);}}><Focus size={16} aria-hidden="true"/>Focus on this team</button>}</div>}
    <div className="employee-org-footnote"><Users size={14} aria-hidden="true"/><span>Connected lines show saved reporting relationships. Select a person to read their full details.</span></div>
  </section>;
}
