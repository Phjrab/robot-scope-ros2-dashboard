import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../robot_dashboard/static/features/offline_slam/dashboard.js',import.meta.url),'utf8');
const {actions,projectPoint,sharedBounds}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('only completed, unsaved results can be saved; active work can be cancelled',()=>{
  assert.equal(actions({state:'RUNNING'}).save,false);
  assert.equal(actions({state:'NO_LOOP'}).save,false);
  assert.equal(actions({state:'SUCCEEDED'}).save,true);
  assert.equal(actions({state:'SUCCEEDED',saved:true,revision:'revision'}).run,false);
  assert.equal(actions({state:'RUNNING'}).cancel,true);
});
test('before and after share bounds including height and both trajectories',()=>{
  const bounds=sharedBounds({before:[[0,0,0]],after:[[10,20,30]],path_before:[[-5,0,0]],path_after:[]},'xz');
  assert.deepEqual(bounds,{minX:-5,maxX:10,minY:0,maxY:30});
  assert.deepEqual(projectPoint([1,2,3],'xy'),[1,2]);
});
