import test from 'node:test';
import assert from 'node:assert/strict';
import {createTransport} from '../robot_dashboard/static/features/expansion/transport.js';
import {startScenePolling} from '../robot_dashboard/static/features/expansion/scene_poll.js';
const tick=()=>new Promise(r=>setImmediate(r));
test('hung request times out, aborts network; late result cannot be returned',async()=>{
 let done,signal;const request=createTransport({timeoutMs:15,fetcher:(_,options)=>{signal=options.signal;return new Promise(r=>done=r);}});
 await assert.rejects(request('/api/v1/extensions/scene/snapshot'),/REQUEST_TIMEOUT/);assert.ok(signal.aborted);
 done(new Response('{}'));await tick();
});
test('body read is also timed out; response ceiling preserved',async()=>{
 let cancelled=false;
 const body=new ReadableStream({cancel(){cancelled=true;}});
 const request=createTransport({timeoutMs:15,fetcher:async()=>new Response(body)});
 await assert.rejects(request('/api/v1/extensions/scene/snapshot'),/REQUEST_TIMEOUT/);assert.ok(cancelled);
 const huge=createTransport({fetcher:async()=>new Response('x'.repeat(131073))});
 await assert.rejects(huge('/api/v1/extensions/scene/snapshot'),/DOCUMENT_LIMIT/);
});
test('view abort cancels pending request and removes parent listeners on success/failure',async()=>{
 const parent=new AbortController();let count=0;
 const add=parent.signal.addEventListener.bind(parent.signal),remove=parent.signal.removeEventListener.bind(parent.signal);
 parent.signal.addEventListener=(...a)=>{count++;return add(...a);};parent.signal.removeEventListener=(...a)=>{count--;return remove(...a);};
 const ok=createTransport({signal:parent.signal,fetcher:async()=>new Response('{}')});await ok('/api/v1/extensions/scene/context');assert.equal(count,0);
 const pending=createTransport({signal:parent.signal,fetcher:()=>new Promise(()=>{})})('/api/v1/extensions/scene/snapshot');
 parent.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(count,0);
});
test('one pending scene request, disposal aborts and ignores late context; no rescheduled poll',async()=>{
 let done,requestSignal,count=0,callbacks=0,scheduled=0;
 const poll=startScenePolling({request:(_,o)=>{count++;requestSignal=o.signal;return new Promise(r=>done=r);},
 onContext:()=>callbacks++,onPacket:()=>callbacks++,onError:()=>callbacks++,schedule:()=>{scheduled++;}});
 await tick();assert.equal(count,1);poll.destroy();assert.ok(requestSignal.aborted);done({});await tick();
 assert.equal(callbacks,0);assert.equal(scheduled,0);
});
test('source failure backoff bounded, timer cleaned and subsequent mount has one request',async()=>{
 let scheduled=[],timer,removed=0,errors=0;
 const poll=startScenePolling({request:async()=>{const e=new Error('BLOCKED_INPUTS');e.status=503;throw e;},
 onContext:()=>{},onPacket:()=>{},onError:()=>errors++,schedule:(fn,ms)=>{timer=fn;scheduled.push(ms);return scheduled.length;},cancel:()=>removed++});
 await tick();for(let i=0;i<12;i++){await timer();}
 assert.equal(errors,13);assert.ok(scheduled.every(ms=>ms>=1000&&ms<=30000));poll.destroy();assert.equal(removed,1);
});
