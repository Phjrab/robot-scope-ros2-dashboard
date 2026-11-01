import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createC1AssetCache} from '../../robot_dashboard/static/features/obstacle_scene/c1_assets.js';
const body=new TextEncoder().encode('{"points":[1,2,3]}'),hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const ref={id:'a'.repeat(24),revision:hash(body),role:'saved_reference_cloud',source:'map',usage:'DISPLAY_ONLY',bytes:body.length,media_type:'application/json'};
const wire=(refs=[ref],generation=1)=>({map_binding:{map_id:'x',revision:'y',generation},stream_epoch:'scene',sources:{assets:refs}});
function cache(options={}){return createC1AssetCache({fetchAsset:async()=>new Response(body,{headers:{'content-type':'application/json'}}),decode:bytes=>JSON.parse(new TextDecoder().decode(bytes)),digest:hash,...options});}
test('opaque bytes fetched, verified and decoded once per revision; source omission/reset/dispose clear cache',async()=>{
  const c=cache();for(let i=0;i<100;i++){const values=await c.resolve(wire());assert.deepEqual(values[0].value,{points:[1,2,3]});}
  assert.deepEqual(c.diagnostics(),{entries:1,downloads:1,decodes:1});await c.resolve(wire([]));assert.equal(c.diagnostics().entries,0);
  await c.resolve(wire());await c.resolve(wire([ref],2));assert.equal(c.diagnostics().downloads,3);c.dispose();assert.equal(c.diagnostics().entries,0);await assert.rejects(c.resolve(wire()),/DISPOSED/);
});
test('retired revision, auth denial, corrupt body and oversize body never decode or retry on every poll',async()=>{
  for(const [response,status] of [[()=>new Response('',{status:404}),'ASSET_HTTP_404'],[()=>new Response('',{status:401}),'ASSET_HTTP_401'],[()=>new Response('x'.repeat(body.length),{headers:{'content-type':'application/json'}}),'ASSET_HASH_MISMATCH'],[()=>new Response('x'.repeat(body.length+1),{headers:{'content-type':'application/json'}}),'ASSET_BYTE_LIMIT']]){
    const c=cache({fetchAsset:async()=>response()});for(let i=0;i<3;i++)assert.equal((await c.resolve(wire()))[0].status,status);assert.deepEqual(c.diagnostics(),{entries:1,downloads:1,decodes:0});
  }
});
test('only bounded opaque IDs and allowlisted roles/media are accepted; no URL or path resolution',async()=>{
  for(const bad of [{id:'https://other/x'},{bytes:2*1024*1024+1},{usage:'SAFETY'},{media_type:'text/html'},{role:'shell'}])await assert.rejects(cache().resolve(wire([{...ref,...bad}])),/REFERENCE_INVALID/);
  await assert.rejects(cache().resolve(wire(Array(9).fill(ref))),/COUNT_LIMIT/);
  await assert.rejects(cache().resolve(wire([ref,ref])),/DUPLICATE/);
});
test('map change during in-flight download cannot repopulate cache with the previous map',async()=>{
  let release;const c=cache({fetchAsset:()=>new Promise(r=>release=r)});const old=c.resolve(wire());await c.resolve(wire([],2));
  release(new Response(body,{headers:{'content-type':'application/json'}}));assert.deepEqual(await old,[]);assert.equal(c.diagnostics().entries,0);
});
test('invalid display profile is an explicit cached decoder failure',async()=>{
  const c=cache({decode:()=>{throw new Error('UNKNOWN_DISPLAY_PROFILE');}});assert.equal((await c.resolve(wire()))[0].status,'UNKNOWN_DISPLAY_PROFILE');assert.equal(c.diagnostics().decodes,0);
});
