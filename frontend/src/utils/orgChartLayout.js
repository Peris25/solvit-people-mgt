// A compact org chart: top-level teams are side by side; siblings within
// each team share a reporting rail. Stacking cards never creates fake edges.
export const CARD_WIDTH=204;
export const CARD_HEIGHT=116;
export const orgCardHeight=node=>node.direct_reports?.length?CARD_HEIGHT:80;
const INDENT=20, GAP=20, STACK_GAP=14, CHILD_GAP=24, ROOT_GAP=62, PAD=28;
export const orgKey=(node,path)=>node.node_id||`${path}:${node.id||'person'}`;

export function wrapOrgText(value,limit,lines=2) {
  const words=String(value||'').split(/\s+/).filter(Boolean),out=[];
  let line='';
  for(const word of words){
    if(line&&`${line} ${word}`.length>limit){out.push(line);line=word;}else line=line?`${line} ${word}`:word;
  }
  if(line)out.push(line);
  const result=out.slice(0,lines).map(text=>text.length>limit?text.slice(0,limit-1)+'…':text);
  if(out.length>lines)result[lines-1]=result[lines-1].slice(0,limit-1)+'…';
  return result;
}

export function reportingIssue(node){
  return node.identity_status==='ambiguous'?'Employee identifier needs review':{
    unavailable:'Reporting link unavailable',ambiguous:'Manager reference needs review',
    cycle:'Reporting cycle needs review',depth_limit:'Reporting branch shown separately',
    none:'Reporting assignment awaits HR confirmation',
  }[node.reporting_status];
}

function layoutBasicOrgChart(roots,collapsed=new Set()) {
  const nodes=[],edges=[];
  const children=(node,path)=>collapsed.has(orgKey(node,path))?[]:node.direct_reports||[];
  function measure(node,path){
    const reports=children(node,path).map((child,i)=>measure(child,`${path}.${i}`));
    return {width:Math.max(CARD_WIDTH,...reports.map(child=>child.width+INDENT)),height:orgCardHeight(node)+(reports.length?CHILD_GAP+reports.reduce((sum,child)=>sum+child.height,0)+STACK_GAP*(reports.length-1):0)};
  }
  const groups=roots.map((root,i)=>{
    const path=String(i),reports=children(root,path).map((node,j)=>({node,path:`${path}.${j}`,size:measure(node,`${path}.${j}`)}));
    const board=root.reporting_status==='resolved'&&!root.line_manager_id&&root.line_manager_name==='Board of Directors';
    return {root,path,reports,board,width:Math.max(CARD_WIDTH,reports.reduce((sum,child)=>sum+child.size.width,0)+GAP*Math.max(0,reports.length-1)),height:(board?88:0)+CARD_HEIGHT+(reports.length?ROOT_GAP+Math.max(...reports.map(child=>child.size.height)):0)};
  });
  const width=Math.max(CARD_WIDTH,...groups.map(group=>group.width))+2*PAD;
  function branch(node,x,y,path,parentKey){
    const key=orgKey(node,path),height=orgCardHeight(node);nodes.push({key,node,x,y,path,parentKey,height});
    let childY=y+height+CHILD_GAP;
    children(node,path).forEach((child,i)=>{
      const childPath=`${path}.${i}`,childKey=orgKey(child,childPath),childX=x+INDENT;
      edges.push({from:key,to:childKey,d:`M${x+CARD_WIDTH/2},${y+height} V${y+height+10} H${x+7} V${childY+orgCardHeight(child)/2} H${childX}`});
      branch(child,childX,childY,childPath,key);
      childY+=measure(child,childPath).height+STACK_GAP;
    });
  }
  let top=PAD;
  groups.forEach(group=>{
    const rootX=(width-CARD_WIDTH)/2,rootY=top+(group.board?88:0),key=orgKey(group.root,group.path);
    if(group.board){
      nodes.push({key:`board:${key}`,isBoard:true,x:(width-174)/2,y:top});
      edges.push({from:`board:${key}`,to:key,d:`M${width/2},${top+50} V${rootY}`});
    }
    nodes.push({key,node:group.root,x:rootX,y:rootY,path:group.path,isRoot:true,height:CARD_HEIGHT});
    let x=(width-group.width)/2;
    group.reports.forEach(child=>{
      const childY=rootY+CARD_HEIGHT+ROOT_GAP;
      edges.push({from:key,to:orgKey(child.node,child.path),d:`M${width/2},${rootY+CARD_HEIGHT} V${rootY+CARD_HEIGHT+30} H${x+CARD_WIDTH/2} V${childY}`});
      branch(child.node,x,childY,child.path,key);
      x+=child.size.width+GAP;
    });
    top+=group.height+48;
  });
  return {nodes,edges,width,height:Math.max(220,top-48+PAD)};
}

// Display ranks are separate from reporting edges: a manager can occupy the
// management row and still report to another manager in that row.
function leadershipLayout(roots,collapsed){
  const role=node=>String(node.role_title||'').toLowerCase().replace(/[^a-z]/g,'');
  const managing=roots.filter(node=>role(node)==='managingdirector'&&node.identity_status!=='ambiguous');
  if(managing.length!==1)return null;
  const md=managing[0],all=[];
  const scan=(records,path='')=>records.forEach((node,i)=>{const keyPath=path?`${path}.${i}`:String(i);all.push({node,path:keyPath});scan(node.direct_reports||[],keyPath);});
  scan(roots);
  const directors=all.filter(item=>role(item.node)==='executivedirector'&&item.node.identity_status!=='ambiguous');
  const ed=directors.length===1?directors[0]:null;
  const mdPath=String(roots.indexOf(md));
  const leaders=[{node:md,path:mdPath,key:orgKey(md,mdPath)}];
  if(ed)leaders.push({...ed,key:orgKey(ed.node,ed.path),peer:true});
  const entries=[];
  function visit(parent){
    if(collapsed.has(parent.key))return;
    (parent.node.direct_reports||[]).forEach((node,i)=>{
      if(ed&&node===ed.node)return;
      const path=`${parent.path}.${i}`,entry={node,path,key:orgKey(node,path),parentKey:parent.key};
      entries.push(entry);visit(entry);
    });
  }
  leaders.forEach(visit);
  const leaderKeys=new Set(leaders.map(item=>item.key));
  const managers=entries.filter(item=>leaderKeys.has(item.parentKey)||item.node.direct_reports?.length);
  const managerKeys=new Set(managers.map(item=>item.key));
  const leaves=entries.filter(item=>!managerKeys.has(item.key));
  const columns=managers.map(item=>({...item,reports:leaves.filter(child=>child.parentKey===item.key)}));
  const contentWidth=Math.max(leaders.length*CARD_WIDTH+(leaders.length-1)*GAP,columns.reduce((sum,item)=>sum+CARD_WIDTH+(item.reports.length?INDENT:0),0)+GAP*Math.max(0,columns.length-1));
  const width=contentWidth+2*PAD,nodes=[],edges=[];
  const boardLeaders=leaders.filter(item=>item.node.reporting_status==='resolved'&&!item.node.line_manager_id&&item.node.line_manager_name==='Board of Directors');
  const leaderY=PAD+(boardLeaders.length?88:0);
  const leaderStart=(width-(leaders.length*CARD_WIDTH+(leaders.length-1)*GAP))/2;
  const positions=new Map();
  leaders.forEach((item,i)=>{
    const displayed=item.peer?{...item.node,chart_relationship:'Executive peer of the Managing Director'}:{...item.node,direct_report_count:(item.node.direct_report_count??item.node.direct_reports?.length??0)-(ed&&item.node.direct_reports?.includes(ed.node)?1:0)};
    const placed={...item,node:displayed,x:leaderStart+i*(CARD_WIDTH+GAP),y:leaderY,isRoot:true,height:CARD_HEIGHT};
    nodes.push(placed);positions.set(item.key,placed);
  });
  if(boardLeaders.length){
    const boardKey=`board:${leaders[0].key}`;
    nodes.push({key:boardKey,isBoard:true,x:(width-174)/2,y:PAD});
    boardLeaders.forEach(item=>{const target=positions.get(item.key);edges.push({from:boardKey,to:item.key,d:`M${width/2},${PAD+50} V${PAD+68} H${target.x+CARD_WIDTH/2} V${leaderY}`});});
  }
  if(ed){
    const left=positions.get(leaders[0].key),right=positions.get(leaders[1].key);
    edges.push({from:left.key,to:right.key,kind:'peer',d:`M${left.x+CARD_WIDTH},${leaderY+CARD_HEIGHT/2} H${right.x}`});
  }
  const managerialLinks=managers.filter(item=>managerKeys.has(item.parentKey));
  const managerY=leaderY+CARD_HEIGHT+ROOT_GAP+managerialLinks.length*8;
  let x=(width-contentWidth)/2,bottom=leaderY+CARD_HEIGHT;
  columns.forEach(item=>{
    const placed={...item,x,y:managerY,height:CARD_HEIGHT};nodes.push(placed);positions.set(item.key,placed);
    item.reports.forEach((child,i)=>{
      const childY=managerY+CARD_HEIGHT+CHILD_GAP+i*(80+STACK_GAP),childX=x+INDENT;
      nodes.push({...child,x:childX,y:childY,height:80});
      edges.push({from:item.key,to:child.key,d:`M${x+CARD_WIDTH/2},${managerY+CARD_HEIGHT} V${managerY+CARD_HEIGHT+10} H${x+7} V${childY+40} H${childX}`});
      bottom=Math.max(bottom,childY+80);
    });
    bottom=Math.max(bottom,managerY+CARD_HEIGHT);
    x+=CARD_WIDTH+(item.reports.length?INDENT:0)+GAP;
  });
  let lane=0;
  managers.forEach(item=>{
    const from=positions.get(item.parentKey),to=positions.get(item.key);
    if(managerKeys.has(item.parentKey)){
      const gutter=from.x+CARD_WIDTH+7,rail=managerY-18-(lane++)*8;
      edges.push({from:from.key,to:to.key,kind:'manager',d:`M${from.x+CARD_WIDTH},${managerY+CARD_HEIGHT/2} H${gutter} V${rail} H${to.x+CARD_WIDTH/2} V${managerY}`});
    }else edges.push({from:from.key,to:to.key,d:`M${from.x+CARD_WIDTH/2},${leaderY+CARD_HEIGHT} V${leaderY+CARD_HEIGHT+26+leaders.findIndex(item=>item.key===from.key)*14} H${to.x+CARD_WIDTH/2} V${managerY}`});
  });
  const withoutPeer=node=>({...node,direct_reports:(node.direct_reports||[]).filter(child=>child!==ed?.node).map(withoutPeer)});
  const remaining=roots.filter(root=>root!==md&&root!==ed?.node).map(withoutPeer);
  let height=bottom+PAD;
  if(remaining.length){
    const extra=layoutBasicOrgChart(remaining,collapsed),combinedWidth=Math.max(width,extra.width);
    const shift=(combinedWidth-width)/2,extraShift=(combinedWidth-extra.width)/2;
    nodes.forEach(item=>{item.x+=shift;});
    edges.forEach(edge=>{edge.transform=`translate(${shift},0)`;});
    nodes.push(...extra.nodes.map(item=>({...item,x:item.x+extraShift,y:item.y+height+20})));
    edges.push(...extra.edges.map(edge=>({...edge,transform:`translate(${extraShift},${height+20})`})));
    return {nodes,edges,width:combinedWidth,height:height+20+extra.height};
  }
  return {nodes,edges,width,height};
}

export function layoutOrgChart(roots,collapsed=new Set()){
  return leadershipLayout(roots,collapsed)||layoutBasicOrgChart(roots,collapsed);
}
