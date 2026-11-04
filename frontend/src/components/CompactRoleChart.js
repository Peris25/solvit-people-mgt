import React from 'react';

const red = '#ff303f';
function Box({ x, y, width, height, lines, fontSize=15 }) {
  return <g><rect x={x} y={y} width={width} height={height} rx={6} fill={red}/><text x={x+width/2} y={y+height/2-(lines.length-1)*fontSize*0.58} fill="white" fontFamily="Arial, Helvetica, sans-serif" fontSize={fontSize} fontWeight="700" textAnchor="middle" dominantBaseline="middle">{lines.map((line,i)=><tspan key={line+i} x={x+width/2} dy={i?fontSize*1.16:0}>{line}</tspan>)}</text></g>;
}
function Line({ x1,y1,x2,y2,dot=false }) { return <g><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#262626" strokeWidth={1}/>{dot&&<circle cx={x2} cy={y2} r={1.7} fill="#262626"/>}</g>; }

export default function CompactRoleChart() {
  return <figure style={{margin:0,background:'#fff',border:'1px solid #e5e7eb',borderRadius:14,overflow:'hidden'}}>
    <svg role="img" aria-labelledby="solvit-role-chart-title solvit-role-chart-description" viewBox="0 0 1024 720" style={{display:'block',width:'100%',height:'auto',maxHeight:'70vh'}}>
      <title id="solvit-role-chart-title">Solvit organisational chart</title>
      <desc id="solvit-role-chart-description">Board of Directors above Managing Director; Executive Director linked laterally. Six branches: Finance and Operations Manager to Account Management Team; Technical Services and Growth Manager to Motor Valuation Team; Growth Captain to Sales Team; Operations Coordinator to Solvers; Human Resource and Administration Manager; IT Lead to IT Support. This is the documented role structure, not an assignment of individual employees.</desc>
      <rect width="1024" height="720" fill="white"/>
      <image href="/solvit-logo.png" x="12" y="20" width="218" height="78" preserveAspectRatio="xMinYMid meet"/>
      <text x="782" y="40" fontFamily="Arial, Helvetica, sans-serif" fontSize="18" fontWeight="700" letterSpacing="2" textAnchor="middle">SOLVIT ORGANIZATIONAL CHART</text>
      <Box x={385} y={80} width={188} height={80} lines={['BOARD OF','DIRECTORS']} fontSize={19}/>
      <Line x1={479} y1={160} x2={479} y2={216} dot/>
      <Box x={347} y={234} width={170} height={75} lines={['MANAGING','DIRECTOR']} fontSize={18}/>
      <Box x={636} y={238} width={170} height={75} lines={['EXECUTIVE','DIRECTOR']} fontSize={18}/>
      <Line x1={523} y1={276} x2={622} y2={276} dot/><Line x1={626} y1={289} x2={529} y2={289} dot/>
      <Line x1={432} y1={309} x2={432} y2={385}/><Line x1={95} y1={385} x2={925} y2={385}/>
      {[95,251,412,573,749,925].map(x=><Line key={x} x1={x} y1={385} x2={x} y2={440} dot/>)}
      <Box x={22} y={455} width={146} height={74} fontSize={14} lines={['FINANCE &','OPERATIONS','MANAGER']}/>
      <Box x={184} y={455} width={134} height={96} fontSize={14} lines={['TECHNICAL','SERVICES &','GROWTH','MANAGER']}/>
      <Box x={345} y={455} width={134} height={58} fontSize={14} lines={['GROWTH','CAPTAIN']}/>
      <Box x={506} y={455} width={134} height={58} fontSize={14} lines={['OPERATIONS','COORDINATOR']}/>
      <Box x={682} y={455} width={134} height={96} fontSize={14} lines={['HUMAN','RESOURCE &','ADMINISTRATION','MANAGER']}/>
      <Box x={858} y={464} width={134} height={40} fontSize={15} lines={['IT Lead']}/>
      <Line x1={95} y1={529} x2={95} y2={590} dot/><Line x1={251} y1={551} x2={251} y2={572} dot/>
      <Line x1={412} y1={513} x2={412} y2={590} dot/><Line x1={573} y1={513} x2={573} y2={582} dot/>
      <Line x1={925} y1={504} x2={925} y2={558} dot/>
      <Box x={28} y={607} width={134} height={76} fontSize={14} lines={['ACCOUNT','MANAGEMENT','TEAM']}/>
      <Box x={184} y={582} width={134} height={58} fontSize={14} lines={['MOTOR','VALUATION TEAM']}/>
      <Box x={345} y={606} width={134} height={40} fontSize={14} lines={['SALES TEAM']}/>
      <Box x={506} y={597} width={134} height={40} fontSize={14} lines={['SOLVERS']}/>
      <Box x={858} y={575} width={134} height={40} fontSize={14} lines={['IT SUPPORT']}/>
    </svg>
    <figcaption style={{padding:'10px 18px',fontSize:12,color:'#64748b',borderTop:'1px solid #f1f5f9'}}>Role structure from the Solvit Team Directory. Saved employee reporting relationships are available below.</figcaption>
  </figure>;
}
