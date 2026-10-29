import {identity,poseMatrix,transformPoint,xyProjection} from './contract.js';
export const COLORS=['#47b9ed','#ed9b45','#a385ee','#64c69a','#ed7e99','#92a744','#d28cdb','#70b7ae'];
export function createOverlay(canvas) {
  let projection=null,layers=[],rotation=0;
  function draw({draft,previews,proposal,visibility,mode='both',light=false,rotation:angle=0}) {
    rotation=angle;
    const rect=canvas.getBoundingClientRect(),w=Math.max(1,rect.width),h=Math.max(1,rect.height),dpr=Math.min(2.5,globalThis.devicePixelRatio||1);
    canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle=light?'#edf2f6':'#101d29';ctx.fillRect(0,0,w,h);
    layers=[];
    draft.sources.forEach((s,i)=>{
      const preview=previews.get(s.id);if(!preview||visibility[s.id]?.hidden)return;
      const prior=s.id===draft.anchor?identity():poseMatrix(draft.priors[s.id]);
      const solved=proposal?.transforms?.[s.id];
      const add=(m,kind)=>layers.push({id:s.id,color:COLORS[i],opacity:visibility[s.id]?.opacity??0.8,kind,points:preview.points.map(p=>({xyz:p,world:transformPoint(m,p)}))});
      if(mode==='before')add(identity(),'before');
      else { if(mode==='both'||!solved)add(prior,'prior');if(solved)add(solved,'solved'); }
    });
    const bounds={min:[Infinity,Infinity],max:[-Infinity,-Infinity]};
    for(const l of layers)for(const p of l.points)for(let k=0;k<2;k++){bounds.min[k]=Math.min(bounds.min[k],p.world[k]);bounds.max[k]=Math.max(bounds.max[k],p.world[k]);}
    if(!Number.isFinite(bounds.min[0])){bounds.min=[-5,-5];bounds.max=[5,5];}
    projection=xyProjection(bounds,w,h,rotation);
    ctx.strokeStyle=light?'#d3dce4':'#213241';ctx.lineWidth=1;
    for(let x=24;x<w;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
    for(let y=24;y<h;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
    for(const l of layers){ctx.fillStyle=ctx.strokeStyle=l.color;ctx.globalAlpha=l.opacity;
      for(const p of l.points){const [x,y]=projection.project(p.world);if(l.kind==='prior'){ctx.strokeRect(x-2,y-2,4,4);}else ctx.fillRect(x-1.6,y-1.6,3.2,3.2);}
    }
    ctx.globalAlpha=1;
    // Diagnostic data comes from the provider; the UI never computes residuals.
    for(const sample of (proposal?.heatmap||[]).slice(0,6000)) {
      if(!Array.isArray(sample.position)||sample.position.length!==3||!sample.position.every(Number.isFinite)||!Number.isFinite(sample.distance_m))continue;
      const [x,y]=projection.project(sample.position);ctx.fillStyle=sample.distance_m>0.2?'#ec6666':'#f0bc67';ctx.fillRect(x-3,y-3,6,6);
    }
    ctx.fillStyle=light?'#274359':'#b3c9da';ctx.font='12px sans-serif';
    ctx.fillText(`XY · m · sampled · ${(1/projection.scale).toFixed(3)} m/px · rotation ${rotation.toFixed(2)} rad`,14,22);
    ctx.fillText('□ manual prior   ■ solved / before · drag XY · yaw handle ↗',14,h-14);
    ctx.strokeStyle='#e9bc6c';ctx.beginPath();ctx.arc(w-34,46,14,0,Math.PI*1.6);ctx.stroke();
    return layers;
  }
  return {draw,delta:(dx,dy)=>projection?.delta(dx,dy)||[0,0],
    pick(x,y,id){let best=null,dist=12;for(const l of layers.filter(l=>l.id===id))for(const p of l.points){const q=projection.project(p.world),d=Math.hypot(q[0]-x,q[1]-y);if(d<dist){dist=d;best=p.xyz;}}return best?.slice()||null;},
    extent(id){const p=layers.find(l=>l.id===id)?.points||[];if(!p.length)return 'no preview';return [0,1,2].map(k=>`${Math.min(...p.map(v=>v.world[k])).toFixed(1)}…${Math.max(...p.map(v=>v.world[k])).toFixed(1)}`).join(' / ')+' m (sampled)';},
    points3d:()=>layers.filter(l=>l.kind!=='prior'||!layers.some(s=>s.id===l.id&&s.kind==='solved')).flatMap(l=>l.points.map(p=>p.world)).slice(0,12000)};
}
// Public RobotScene3D API only. Multi-source color is shown in the XY overlay.
export function createRobotSceneRenderer(Renderer) {
  return ({canvas})=>{
    const scene=new Renderer(canvas,{maxPoints:12000,showRobot:false,showTrail:false,heightColor:true,autoFitOnFirstCloud:true,maxCloudRadius:1000000});
    scene.setStatus({snapshot:true,message:'C2 · sampled merged 3D · height color'});
    let key='';
    return {render({points,revision,mode}){const next=`${revision}:${mode}:${points.length}`;scene.setPointCloud({points:points.flat(),frame_id:'c2-fused-preview',source_points:points.length},{fit:next!==key});key=next;},
      resize:()=>scene.resize(),destroy:()=>scene.destroy()};
  };
}
export function drawDerived(canvas,grid,light=false) {
  const ctx=canvas.getContext('2d');ctx.fillStyle=light?'#e4e9ef':'#1e2c38';ctx.fillRect(0,0,canvas.width,canvas.height);
  if(!grid||!Number.isInteger(grid.width)||!Number.isInteger(grid.height)||grid.width<1||grid.height<1
      ||grid.width*grid.height>65536||!Array.isArray(grid.cells)||grid.cells.length!==grid.width*grid.height
      ||!grid.cells.every(c=>[-1,0,100].includes(c)))return false;
  const scale=Math.min(canvas.width/grid.width,canvas.height/grid.height);
  grid.cells.forEach((v,i)=>{ctx.fillStyle=v===-1?'#687b8c':v===0?'#c3d1d9':'#263a4a';ctx.fillRect((i%grid.width)*scale,(grid.height-1-Math.floor(i/grid.width))*scale,Math.ceil(scale),Math.ceil(scale));});
  return true;
}
