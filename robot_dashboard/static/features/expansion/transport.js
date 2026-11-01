// One same-origin bounded transport. No credential persistence or robot API port.
export function createTransport({fetcher=fetch, signal}={}) {
  return async function request(path, {method='GET', body, raw=false}={}) {
    if (!path.startsWith('/api/v1/extensions/') || path.includes('..') || path.includes('\\')) throw new Error('UNSUPPORTED_EXTENSION_ROUTE');
    const response=await fetcher(path,{method,credentials:'same-origin',cache:'no-store',signal,
      headers:body===undefined?{}:{'Content-Type':'application/json'},
      body:body===undefined?undefined:JSON.stringify(body)});
    const reader=response.body.getReader(), chunks=[];let size=0;
    try { for(;;) { const {value,done}=await reader.read();if(done)break;size+=value.byteLength;
      if(size>131072)throw new Error('DOCUMENT_LIMIT');chunks.push(value); } }
    finally { await reader.cancel(); }
    const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
    if(!response.ok) {let data;try{data=JSON.parse(text);}catch{data={};}
      const code=typeof data.error?.code==='string'?data.error.code:`HTTP_${response.status}`;
      const message=typeof data.error?.message==='string'?data.error.message:typeof data.detail==='string'?data.detail:'요청이 거절되었습니다.';
      const error=new Error(`${code}: ${message}`);error.code=code;error.status=response.status;throw error;}
    return raw?text:JSON.parse(text);
  };
}
