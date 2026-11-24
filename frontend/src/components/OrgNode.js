import React, { useState } from 'react';
import { ChevronDown, ChevronRight, UserRound } from 'lucide-react';
import './OrgNode.css';

export default function OrgNode({node, depth=0}) {
  const [open,setOpen]=useState(true);
  const reports=node.direct_reports||[];
  const hasReports=reports.length>0;
  const issue=node.identity_status==='ambiguous'?'Employee identifier needs review':{
    unavailable:'Reporting link unavailable',ambiguous:'Manager reference needs review',
    cycle:'Reporting cycle needs review',depth_limit:'Reporting branch shown separately',
    none:'Reporting assignment awaits HR confirmation',
  }[node.reporting_status];
  const toggle=()=>hasReports&&setOpen(value=>!value);
  return <div className="org-person-branch" data-testid={'org-node-'+node.id}>
    <div className={'org-person-card'+(hasReports?' org-person-manager':'')}
      role={hasReports?'button':undefined} tabIndex={hasReports?0:undefined}
      aria-expanded={hasReports?open:undefined} onClick={toggle}
      onKeyDown={event=>{if(hasReports&&(event.key==='Enter'||event.key===' ')){event.preventDefault();toggle();}}}>
      <span className="org-person-avatar" aria-hidden="true"><UserRound size={18}/></span>
      <div className="org-person-info"><strong>{node.name||'Name unavailable'}</strong>
        <span>{node.role_title||'Title not recorded'}</span>
        {(node.department_label||node.department)&&<span className="org-person-department">{node.department_label||node.department}</span>}
        {issue&&<span role="status" className="org-person-issue">{issue}</span>}
      </div>
      {hasReports&&<span className="org-person-toggle"><span>{reports.length} direct {reports.length===1?'report':'reports'}</span>{open?<ChevronDown size={18} aria-hidden="true"/>:<ChevronRight size={18} aria-hidden="true"/>}</span>}
    </div>
    {hasReports&&open&&<div className={'org-person-reports'+(depth>=2?' org-person-deep':'')} role="group" aria-label={'Direct reports to '+(node.name||'manager')}>
      {reports.map(child=>React.createElement(OrgNode,{key:child.node_id||child.id,node:child,depth:depth+1}))}
    </div>}
  </div>;
}
