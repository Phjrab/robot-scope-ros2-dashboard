import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const { goalPrecisionText } = createRequire(import.meta.url)('../robot_dashboard/static/navigation.js');

test('Nav2 success and zero remaining do not become zero pose error or confirmed stop', () => {
  const goal = {state:'succeeded',distance_remaining:0,goal_id:'one',precision_evidence:{
    goal_id:'one',current:{fresh:true,frame_id:'map',body_frame_id:'base_link',stamp_ns:'1234567890123456789',age_s:.03,error:{xy_m:.308926,yaw_rad:-.472324}},
    stop:{confirmed_now:false},precision:{satisfied_now:null}}};
  const text=goalPrecisionText(goal);
  assert.match(text,/SUCCEEDED/);assert.match(text,/0.309 m/);assert.match(text,/-27.06°/);
  assert.match(text,/정지 확인: 현재 미확인/);assert.match(text,/충족: 미확인/);
  assert.match(text,/1234567890123456789/);assert.match(text,/성공 원시 시각: 미제공/);
});
test('missing, late foreign evidence and stale current sample are labelled unknown',()=>{
  assert.match(goalPrecisionText({state:'succeeded',distance_remaining:0}),/미확인/);
  const g={state:'active',goal_id:'new',precision_evidence:{goal_id:'old',current:{error:{xy_m:0,yaw_rad:0}}}};
  assert.doesNotMatch(goalPrecisionText(g),/0.000 m/);
  g.goal_id='old';assert.match(goalPrecisionText(g),/현재 신선도 미충족/);
});

test('missing yaw remains unknown in radians and degrees', () => {
  const text = goalPrecisionText({state:'succeeded',goal_id:'g',precision_evidence:{goal_id:'g',current:{fresh:true,error:{xy_m:null,yaw_rad:null}}}});
  assert.match(text,/XY 미확인 m · yaw 미확인 rad \(미확인°\)/);
  assert.doesNotMatch(text,/0\.00°/);
});
