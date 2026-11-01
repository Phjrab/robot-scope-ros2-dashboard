// C1 owns opaque display bytes and fixed authenticated routes. The host supplies
// transport and an explicit decoder; C1 does not specify a cloud/costmap format.
export function createC1AssetCache({fetchAsset, decode, digest=async bytes=>
  Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')}) {
  const cache=new Map(); let generation=0, context='', closed=false, downloads=0, decodes=0;
  function clear(){generation++;cache.clear();}
  async function resolve(wire){
    if(closed)throw new Error('ASSET_CACHE_DISPOSED');
    const next=JSON.stringify([wire.map_binding,wire.stream_epoch]);
    if(next!==context){clear();context=next;}
    const mine=++generation, refs=wire.sources?.assets || [];
    if(!Array.isArray(refs)||refs.length>8)throw new Error('ASSET_COUNT_LIMIT');
    let total=0;const keys=new Set();
    for(const ref of refs){
      if(!ref || !/^[a-f0-9]{24}$/.test(ref.id) || !/^[a-f0-9]{64}$/.test(ref.revision)
        || !['saved_reference_cloud','live_cloud','costmap'].includes(ref.role) || ref.usage!=='DISPLAY_ONLY'
        || !['application/json','application/octet-stream'].includes(ref.media_type)
        || !Number.isSafeInteger(ref.bytes)||ref.bytes<1||ref.bytes>2*1024*1024
        || typeof ref.source!=='string'||ref.source.length>256)throw new Error('ASSET_REFERENCE_INVALID');
      total+=ref.bytes;const key=JSON.stringify(ref);if(keys.has(key))throw new Error('ASSET_DUPLICATE');keys.add(key);
    }
    if(total>8*1024*1024)throw new Error('ASSET_TOTAL_LIMIT');
    for(const key of cache.keys())if(!keys.has(key))cache.delete(key);
    const results=[];
    for(const ref of refs){
      const key=JSON.stringify(ref);let entry=cache.get(key);
      if(!entry){
        try{
          const response=await fetchAsset(`/api/v1/extensions/scene/assets/${ref.id}/${ref.revision}`);downloads++;
          if(!response.ok)throw new Error(`ASSET_HTTP_${response.status}`);
          if(response.headers.get('content-type')?.split(';')[0]!==ref.media_type)throw new Error('ASSET_MEDIA_MISMATCH');
          const reader=response.body.getReader(), chunks=[];let size=0;
          try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>ref.bytes)throw new Error('ASSET_BYTE_LIMIT');chunks.push(value);}}
          finally{await reader.cancel();}
          if(size!==ref.bytes)throw new Error('ASSET_LENGTH_MISMATCH');
          const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
          if(await digest(bytes)!==ref.revision)throw new Error('ASSET_HASH_MISMATCH');
          const value=await decode(bytes,ref,wire.map_binding);decodes++;
          entry={ref,value,status:'READY'};
        }catch(error){entry={ref,value:null,status:String(error.message)};}
        if(closed||mine!==generation)return [];
        // Failures are retained for this immutable reference, not retried every poll.
        cache.set(key,entry);
      }
      results.push(entry);
    }
    return closed||mine!==generation?[]:results;
  }
  return {resolve,clear,dispose(){closed=true;clear();},diagnostics:()=>({entries:cache.size,downloads,decodes})};
}
