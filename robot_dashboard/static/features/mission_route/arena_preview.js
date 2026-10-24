// Bounded GLB view adapter for the published arena bundle. No map/pose inputs.
// glTF Y-up stays visual; it is never reinterpreted as navigation coordinates.
export function decodeArenaGLB(buffer) {
  if (buffer.byteLength > 2_000_000 || buffer.byteLength < 28) throw new Error('GLB size unsupported');
  const view = new DataView(buffer);
  if (view.getUint32(0,true) !== 0x46546c67 || view.getUint32(4,true) !== 2 || view.getUint32(8,true) !== buffer.byteLength) throw new Error('Invalid GLB');
  let document, binary;
  for (let offset=12; offset<buffer.byteLength;) {
    const size=view.getUint32(offset,true), type=view.getUint32(offset+4,true); offset+=8;
    if(offset+size>buffer.byteLength) throw new Error('Invalid GLB chunk');
    if(type===0x4e4f534a) document=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,offset,size)));
    if(type===0x004e4942) binary=new DataView(buffer,offset,size);
    offset+=size;
  }
  if(!document || !binary || document.extensionsRequired?.length) throw new Error('Unsupported GLB extensions');
  function values(index, type) {
    const a=document.accessors?.[index], b=document.bufferViews?.[a?.bufferView];
    if(!a || !b || b.buffer!==0 || a.sparse || a.type!==type || a.count>100000) throw new Error('Unsupported GLB accessor');
    const width=type==='VEC3'?3:1, bytes={5126:4,5123:2,5125:4}[a.componentType], stride=b.byteStride || bytes*width;
    if(!bytes || (type==='VEC3' && a.componentType!==5126)) throw new Error('Unsupported GLB component');
    const start=(b.byteOffset||0)+(a.byteOffset||0), result=[];
    for(let i=0;i<a.count;i++) {
      const row=[];
      for(let j=0;j<width;j++) {
        const offset=start+i*stride+j*bytes;
        if(offset+bytes>binary.byteLength || offset+bytes>(b.byteOffset||0)+b.byteLength) throw new Error('GLB accessor outside buffer');
        const value=a.componentType===5126?binary.getFloat32(offset,true):a.componentType===5123?binary.getUint16(offset,true):binary.getUint32(offset,true);
        if(!Number.isFinite(value)) throw new Error('Nonfinite GLB'); row.push(value);
      }
      result.push(type==='SCALAR'?row[0]:row);
    }
    return result;
  }
  const triangles=[];
  for(const nodeIndex of document.scenes?.[document.scene||0]?.nodes || []) {
    const node=document.nodes[nodeIndex];
    if(node.children?.length || node.matrix || node.skin!==undefined) throw new Error('Hierarchical GLB needs model adapter update');
    if(node.mesh===undefined) continue;
    const t=node.translation||[0,0,0], q=node.rotation||[0,0,0,1], scale=node.scale||[1,1,1];
    if(t.length!==3 || q.length!==4 || scale.length!==3 || ![...t,...q,...scale].every(Number.isFinite)) throw new Error('Invalid node transform');
    function transform(p) {
      const v=p.map((x,i)=>x*scale[i]), [x,y,z,w]=q;
      const uv=[y*v[2]-z*v[1],z*v[0]-x*v[2],x*v[1]-y*v[0]];
      const uuv=[y*uv[2]-z*uv[1],z*uv[0]-x*uv[2],x*uv[1]-y*uv[0]];
      return v.map((value,i)=>value+2*(w*uv[i]+uuv[i])+t[i]);
    }
    for(const primitive of document.meshes[node.mesh].primitives) {
      if((primitive.mode??4)!==4) throw new Error('Only triangular GLB is supported');
      const points=values(primitive.attributes.POSITION,'VEC3').map(transform), indices=primitive.indices===undefined?points.map((_,i)=>i):values(primitive.indices,'SCALAR');
      const color=document.materials?.[primitive.material]?.pbrMetallicRoughness?.baseColorFactor || [.5,.6,.7,1];
      if(indices.length%3 || color.length!==4 || !color.every(Number.isFinite)) throw new Error('Invalid GLB primitive');
      for(let i=0;i<indices.length;i+=3) {
        const vertices=indices.slice(i,i+3).map(index=>points[index]);
        if(vertices.some(v=>!v) || triangles.length>=50000) throw new Error('GLB triangle bounds exceeded');
        triangles.push({vertices,color});
      }
    }
  }
  if(!triangles.length) throw new Error('Empty GLB');
  return triangles;
}

export function createArenaPreview({parent, document:doc=globalThis.document}) {
  const details=doc.createElement('details'), summary=doc.createElement('summary'), notice=doc.createElement('p'), canvas=doc.createElement('canvas'), load=doc.createElement('button'), rotate=doc.createElement('button');
  summary.textContent='설계 모델 · 실측 지도와 별도 보기'; notice.textContent='manifest 확인 전 · pose overlay 없음';
  load.textContent='설계 GLB 불러오기'; rotate.textContent='시점 회전'; load.type=rotate.type='button'; rotate.disabled=true;
  canvas.width=800; canvas.height=400; canvas.hidden=true; canvas.setAttribute('role','img'); canvas.setAttribute('aria-label','VM 설계 경기장 GLB · 정합 미확인 · 실측 pose 없음'); canvas.dataset.arenaGlb='true';
  details.append(summary,notice,load,rotate,canvas); parent.append(details);
  let triangles=null, yaw=.65, signature=null, alive=true;
  function draw() {
    if(!triangles) return;
    const pitch=.9, project=([x,y,z])=>{const u=x*Math.cos(yaw)+z*Math.sin(yaw), depth=-x*Math.sin(yaw)+z*Math.cos(yaw); return [u,depth*Math.sin(pitch)-y*Math.cos(pitch),depth*Math.cos(pitch)+y*Math.sin(pitch)];};
    const faces=triangles.map(t=>({...t,points:t.vertices.map(project)}));
    const points=faces.flatMap(t=>t.points), xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
    const minX=xs.reduce((a,b)=>Math.min(a,b),Infinity),maxX=xs.reduce((a,b)=>Math.max(a,b),-Infinity),minY=ys.reduce((a,b)=>Math.min(a,b),Infinity),maxY=ys.reduce((a,b)=>Math.max(a,b),-Infinity), scale=Math.min(740/(maxX-minX),340/(maxY-minY));
    const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,800,400); ctx.fillStyle='#111a22'; ctx.fillRect(0,0,800,400);
    faces.sort((a,b)=>b.points.reduce((s,p)=>s+p[2],0)-a.points.reduce((s,p)=>s+p[2],0));
    for(const face of faces) { ctx.beginPath(); face.points.forEach((p,i)=>ctx[i?'lineTo':'moveTo'](400+(p[0]-(minX+maxX)/2)*scale,200+(p[1]-(minY+maxY)/2)*scale)); ctx.closePath(); ctx.fillStyle=`rgba(${face.color.slice(0,3).map(v=>Math.round(Math.max(0,Math.min(1,v))*255)).join(',')},${face.color[3]})`; ctx.fill(); }
  }
  load.addEventListener('click',async()=>{
    load.disabled=true;
    try {
      const response=await fetch('/api/v1/mission-competition/arena',{credentials:'same-origin'}); if(!response.ok) throw new Error('manifest unavailable'); const manifest=await response.json();
      if(!manifest.available || manifest.visual_asset?.url!=='/api/v1/mission-competition/arena/asset') throw new Error(manifest.reason||'model unavailable');
      const asset=await fetch(manifest.visual_asset.url,{credentials:'same-origin'}); if(!asset.ok) throw new Error('GLB unavailable'); const buffer=await asset.arrayBuffer();
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),v=>v.toString(16).padStart(2,'0')).join('');
      if(hash!==manifest.visual_asset.sha256) throw new Error('GLB revision changed; reload manifest');
      const decoded=decodeArenaGLB(buffer); if(!alive) return; triangles=decoded; signature=manifest.semantic_sha256; canvas.hidden=false; rotate.disabled=false;
      notice.textContent=`${manifest.arena_id}@${manifest.revision} · VM 설계좌표 / GLB Y-up · 정합 미확인 · pose overlay 없음`; draw();
    } catch(error) { if(alive) {triangles=null;canvas.hidden=true;rotate.disabled=true;notice.textContent=error.message;} }
    finally {if(alive) load.disabled=false;}
  });
  rotate.addEventListener('click',()=>{yaw+=Math.PI/4;draw();});
  return {sync(manifest) {if(signature && signature!==manifest?.semantic_sha256) {triangles=null;signature=null;canvas.hidden=true;rotate.disabled=true;notice.textContent='모델 revision 변경 · 다시 불러와 검사하세요.';}}, destroy(){alive=false;details.remove();}};
}
