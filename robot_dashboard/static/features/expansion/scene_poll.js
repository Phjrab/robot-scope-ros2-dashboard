import {adaptC1ScenePacket,parseC1SceneJSON} from '../obstacle_scene/c1_adapter.js';

// The existing scene subscription's single poll, extracted for lifecycle tests.
// C3's own clock expires displayed samples even while either request is pending.
export function startScenePolling({request,signal,onContext,onPacket,onError,clock=()=>performance.now(),
  schedule=setTimeout,cancel=clearTimeout}) {
  const controller=new AbortController();let closed=false,timer=null,failures=0;
  const abort=()=>destroy();
  function destroy(){if(closed)return;closed=true;cancel(timer);controller.abort();signal?.removeEventListener('abort',abort);}
  async function poll(){
    try {
      const context=await request('/api/v1/extensions/scene/context',{signal:controller.signal});
      if(closed)return;onContext(context);
      const started=clock();
      const raw=await request('/api/v1/extensions/scene/snapshot',{raw:true,signal:controller.signal});
      if(closed)return;
      const adapted=adaptC1ScenePacket(parseC1SceneJSON(raw),context,{transportAgeMs:Math.max(0,clock()-started)});
      if(!adapted.packet){onContext(null);throw new Error(adapted.reason);}
      failures=0;onPacket(adapted.packet);
    }catch(error){if(!closed&&error.name!=='AbortError'){
      if([401,403,409,503].includes(error.status))onContext(null);
      failures=Math.min(9,failures+1);onError(error);
    }}
    finally{if(!closed)timer=schedule(poll,failures?Math.min(30000,500*2**failures):100);}
  }
  signal?.addEventListener('abort',abort,{once:true});
  if(signal?.aborted)destroy();else void poll();
  return {destroy};
}
