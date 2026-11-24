import {layoutOrgChart,CARD_WIDTH} from './orgChartLayout';

test('every reporting edge follows its actual parent even when siblings stack',()=>{
 const roots=[{id:'md',node_id:'md',direct_reports:[{id:'manager',node_id:'manager',direct_reports:[{id:'a',node_id:'a'},{id:'b',node_id:'b'}]},{id:'other',node_id:'other',direct_reports:[{id:'c',node_id:'c'}]}]}];
 const graph=layoutOrgChart(roots);
 expect(graph.edges.map(edge=>`${edge.from}->${edge.to}`).sort()).toEqual(['md->manager','md->other','manager->a','manager->b','other->c'].sort());
 for(const node of graph.nodes){expect(node.x).toBeGreaterThanOrEqual(0);expect(node.x+CARD_WIDTH).toBeLessThanOrEqual(graph.width);expect(node.y+node.height).toBeLessThanOrEqual(graph.height);}
 for(let i=0;i<graph.nodes.length;i++)for(let j=i+1;j<graph.nodes.length;j++){
  const a=graph.nodes[i],b=graph.nodes[j];
  expect(a.x+CARD_WIDTH<=b.x||b.x+CARD_WIDTH<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y).toBe(true);
 }
});

test('board reporting is drawn only for an explicitly resolved board relationship',()=>{
 const graph=layoutOrgChart([{id:'md',node_id:'md',name:'MD',line_manager_name:'Board of Directors',reporting_status:'resolved'},{id:'unresolved',node_id:'unresolved',reporting_status:'unavailable'}]);
 expect(graph.nodes.filter(node=>node.isBoard)).toHaveLength(1);
 expect(graph.edges.map(edge=>edge.to)).toEqual(['md']);
});

test('collapsed teams do not hide unrelated branches or change their parentage',()=>{
 const graph=layoutOrgChart([{id:'md',node_id:'md',direct_reports:[{id:'manager',node_id:'manager',direct_reports:[{id:'a',node_id:'a'}]},{id:'b',node_id:'b'}]}],new Set(['manager']));
 expect(graph.nodes.map(item=>item.key)).toEqual(['md','manager','b']);
 expect(graph.edges.map(edge=>edge.to)).toEqual(['manager','b']);
});
