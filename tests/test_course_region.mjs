import test from 'node:test';
import assert from 'node:assert/strict';
import {CourseDraft,coursePolygon,proposeCourse} from '../robot_dashboard/static/features/maps/course_region.js';
import {MapSeedDraft} from '../robot_dashboard/static/features/maps/map_seed.js';
const map={id:'a'.repeat(24),revision:'b'.repeat(64),frame:'map'};
const polygon=[[-2,-3],[2,-3],[2,3],[-2,3]];
const value={map_id:map.id,map_revision:map.revision,map_frame:map.frame,polygon,outside_weight:.25,confirmed:true,units:'m'};
test('course revisions fence late load/save, name-only changes preserve and geometry changes invalidate',()=>{
  const d=new CourseDraft();d.setMap(map);const loading=d.revision;d.edit(polygon);assert.equal(d.accepts(loading),false);
  assert.equal(d.active,null);assert.equal(d.pending,true);d.use(value);assert.equal(d.active.outside_weight,.25);
  const saved=d.revision;assert.equal(d.setMap({...map,name:'renamed'}),false);assert.equal(d.revision,saved);
  d.edit(polygon,.5);assert.equal(d.active,null);assert.equal(d.accepts(saved),false);
  d.setMap({...map,revision:'c'.repeat(64)});assert.throws(()=>d.use(value));assert.equal(d.active,null);assert.equal(d.pending,false);
});
test('existing editor validation rejects intersecting and degenerate boundaries; suggestion is bounded geometry',()=>{
  assert.throws(()=>coursePolygon([[0,0],[1,1],[0,1],[1,0]]));assert.throws(()=>coursePolygon([[0,0],[1,0],[2,0]]));
  assert.throws(()=>coursePolygon([[NaN,0],[1,0],[1,1]]));
  const points=[];for(let x=-10;x<=10;x++)for(let y=-20;y<=20;y++)points.push(x,y,10);
  const p=proposeCourse(points);assert.equal(p.length,4);assert.ok(p[0][0]>-10&&p[2][0]<10);assert.ok(p[0][1]>-20&&p[2][1]<20);
  assert.throws(()=>proposeCourse([]));
});
test('confirmed course flows into seed request as immutable map coordinates and clears on map change',()=>{
  const d=new MapSeedDraft();d.setMap(map);d.edit({x:0,y:0,z:2,roll:0,pitch:0,yaw:90});d.course=structuredClone(value);
  const obs={observer_id:'d'.repeat(32),publisher_epoch:'c'.repeat(32)};
  const inputs={mode:'native_publisher',cloud:{topic:'/cloud_registered',pipeline_stage:'registered',frame_id:'camera_init',observation:obs},pose:{topic:'/Odometry',frame_id:'camera_init',child_frame_id:'body',observation:obs}};
  const request=d.request(inputs);assert.deepEqual(request.course_region,value);request.course_region.polygon[0][0]=100;
  assert.equal(d.course.polygon[0][0],-2);d.setMap({...map,frame:'other'});assert.equal(d.course,null);
});
