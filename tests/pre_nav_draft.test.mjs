import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../robot_dashboard/static/features/navigation/pose_draft.js', import.meta.url), 'utf8');
const { preNavigationDraftBinding: bind } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const input = () => ({ available:true, selected:{ workflow:'staged_navigation_pair', generation:'g1', localization_3d:{map_id:'3d',revision:'3rev'}, navigation_2d:{map_id:'2d',revision:'2rev'} },
  pair:{valid:true,generation:'g1',localization_3d:{map_id:'3d',revision:'3rev'},navigation_2d:{map_id:'2d',revision:'2rev'}},
  mapMeta:{id:'2d',revision:'2rev'},mapData:{map_id:'2d',revision:'2rev'},selected2d:'2d',selected3d:'3d',
  maps:[{id:'2d',revision:'2rev',kind:'occupancy2d',format:'map-server-pgm'},{id:'3d',revision:'3rev',kind:'pointcloud3d'}],navigation:{pipeline:{state:'idle',job_id:null}} });
test('pre-navigation draft binds exact map, pair and runtime without accepting incomplete context', () => {
  const base=input(), key=bind(base); assert.ok(key);
  for (const change of [v=>v.available=false, v=>v.navigation.pipeline.state='running',v=>v.navigation.pipeline.job_id='job',
    v=>v.pair.generation='g2',v=>v.selected.generation='g2',v=>v.selected3d='other',v=>v.selected2d='other',
    v=>v.mapMeta.revision='old',v=>v.mapData.map_id='other',v=>v.maps[0].revision='other',v=>v.maps[1].revision='other',v=>v.pair.valid=false]) {
    const value=input();change(value);assert.equal(bind(value),null);
  }
  const changed=input();changed.navigation.operational_localization={runtime_instance_generation:'new'};assert.notEqual(bind(changed),key);
});
test('extracted draft controller and map helpers preserve invalidation and active map checks', async () => {
  const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  let value=input(), stored=bind(value), clears=0;
  const controller=module.createPreNavigationDraftController({inputs:()=>value,binding:()=>stored,clear:()=>{clears++;stored=null;}});
  assert.equal(controller.current(),stored);controller.invalidate();assert.equal(clears,0);
  value.navigation.pipeline.state='running';controller.invalidate();assert.equal(clears,1);controller.invalidate();assert.equal(clears,1);
  assert.equal(module.navigationActiveMapMatches(false,null,null,null,[]),true);
  const map={id:'2d',revision:'2rev'};
  assert.equal(module.navigationActiveMapMatches(true,map,map,map,[map]),true);
  assert.equal(module.navigationActiveMapMatches(true,map,map,{revision:'old'},[map]),false);
  assert.equal(module.navigationActiveMapMatches(true,map,map,map,[]),false);
  assert.deepEqual(module.navigationMapCandidatesFrom(value.maps).map(x=>x.id),['2d']);
  const point=module.navigationCanvasPointFrom({width:200,height:100,getBoundingClientRect:()=>({left:10,top:20,width:100,height:50})},{clientX:60,clientY:45});
  assert.deepEqual(point,{x:100,y:50});
});
test('transient absence suspends a draft while observed context changes discard it', async () => {
  const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  for (const changed of ['epoch', 'map', 'pair', 'runtime']) {
    const value=input();value.epoch=4;value.navigationAvailable=true;value.preparationAvailable=true;
    let stored=bind(value), clears=0, suspended=0;
    const controller=module.createPreNavigationDraftController({inputs:()=>value,binding:()=>stored,clear:()=>{clears++;stored=null;},suspend:()=>suspended++});
    controller.suspend(); assert.equal(suspended,1); assert.equal(clears,0);
    value.available=false;value.preparationAvailable=false;controller.invalidate();assert.equal(suspended,2);assert.equal(clears,0);
    if(changed==='epoch') value.epoch=5;
    if(changed==='map') value.selected3d='different';
    if(changed==='pair') {value.preparationAvailable=true;value.pair.localization_3d.revision='changed';}
    if(changed==='runtime') value.navigation.pipeline.job_id='new';
    controller.invalidate();assert.equal(clears,1,changed);
  }
});
test('operator input and historical reconfirmation remain bound to exact map and runtime', async () => {
  const module=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  const value=input();value.epoch=1;value.navigationAvailable=true;value.preparationAvailable=true;
  const pre=bind(value), staged={mode:'initial',x:1,y:2,yaw:.4,preBinding:pre};
  const ready=module.operatorDraftSnapshot({staged,pointer:null,toolBinding:null,currentBinding:pre,revision:4});
  assert.equal(ready.status,'ready');assert.deepEqual(ready.pose,{x:1,y:2,yaw:.4});
  assert.equal(module.operatorDraftSnapshot({staged:{...staged,stale:true},currentBinding:pre,revision:4}).status,'stale');
  assert.equal(module.operatorDraftSnapshot({staged,pointer:{},currentBinding:pre,revision:4}).status,'pending');
  value.navigation={pipeline:{state:'running',job_id:'job'},map:{id:'2d',revision:'2rev'},operational_localization:{fresh:true,bundle_generation:'g1',localization_map_id:'3d',localization_map_revision:'3rev',localization_generation:3,runtime_instance_generation:'runtime'}};
  const history={...staged,stale:true,historical:true};assert.ok(module.historicalRuntimeBinding(history,value));
  value.navigation.operational_localization.localization_map_revision='other';assert.equal(module.historicalRuntimeBinding(history,value),null);
});
