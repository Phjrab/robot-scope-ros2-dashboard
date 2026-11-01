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
