// One same-origin bounded transport. No credential persistence or robot API port.
export function createTransport({fetcher=fetch, signal, timeoutMs=3000, onUnauthorized=()=>{}}={}) {
  if(!Number.isFinite(timeoutMs)||timeoutMs<=0||timeoutMs>30000)throw new Error('REQUEST_TIMEOUT_INVALID');
  return async function request(path, {method='GET', body, raw=false, signal:requestSignal}={}) {
    if (!path.startsWith('/api/v1/extensions/') || path.includes('..') || path.includes('\\')) throw new Error('UNSUPPORTED_EXTENSION_ROUTE');
    const controller=new AbortController(), subscriptions=[];
    let reader=null, timer=null, abortListener;
    const abort=()=>controller.abort(new DOMException('View closed','AbortError'));
    for(const parent of new Set([signal,requestSignal].filter(Boolean))){
      if(parent.aborted)abort();else {parent.addEventListener('abort',abort,{once:true});subscriptions.push(()=>parent.removeEventListener('abort',abort));}
    }
    const stopped=new Promise((_,reject)=>{
      abortListener=()=>reject(controller.signal.reason);
      controller.signal.addEventListener('abort',abortListener,{once:true});
      if(controller.signal.aborted)abortListener();
      else timer=setTimeout(()=>controller.abort(new Error('REQUEST_TIMEOUT')),timeoutMs);
    });
    async function read(){
      if(controller.signal.aborted)throw controller.signal.reason;
      const response=await fetcher(path,{method,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,
        headers:body===undefined?{}:{'Content-Type':'application/json'},
        body:body===undefined?undefined:JSON.stringify(body)});
      reader=response.body?.getReader();
      if(controller.signal.aborted){void reader?.cancel().catch(()=>{});throw controller.signal.reason;}
      if(!reader)throw new Error('RESPONSE_BODY_UNAVAILABLE');
      const chunks=[];let size=0;
      for(;;){const {value,done}=await reader.read();if(controller.signal.aborted)throw controller.signal.reason;if(done)break;
        size+=value.byteLength;if(size>131072)throw new Error('DOCUMENT_LIMIT');chunks.push(value);}
      const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
      const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
      if(!response.ok){if(response.status===401)onUnauthorized();let data;try{data=JSON.parse(text);}catch{data={};}
        const code=typeof data.error?.code==='string'?data.error.code:`HTTP_${response.status}`;
        const message=typeof data.error?.message==='string'?data.error.message:typeof data.detail==='string'?data.detail:'요청이 거절되었습니다.';
        const error=new Error(`${code}: ${message}`);error.code=code;error.status=response.status;throw error;}
      return raw?text:JSON.parse(text);
    }
    try{return await Promise.race([stopped,read()]);}
    finally {clearTimeout(timer);subscriptions.forEach(unsubscribe=>unsubscribe());
      controller.signal.removeEventListener('abort',abortListener);controller.abort();void reader?.cancel().catch(()=>{});}
  };
}
