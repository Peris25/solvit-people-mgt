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

export function layoutOrgChart(roots,collapsed=new Set()) {
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
