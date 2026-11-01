// Deterministic synthetic points generated in memory at execution time only.
export function generatePoints(index=0,count=2400) {
  const points=[];
  for(let i=0;i<count;i++) {
    const t=i/count*Math.PI*2,wing=i%3;
    const x=wing===0?-5+(i%160)/16:wing===1?4:Math.cos(t)*3;
    const y=wing===0?-2:wing===1?-2+(i%80)/20:Math.sin(t)*1.5;
    const z=(i%17)/17*1.8;
    // Each session has an independent origin and rotated source frame.
    const a=index*.32,c=Math.cos(a),s=Math.sin(a);
    points.push(c*x-s*y+index*1.8,s*x+c*y-index*.6,z);
  }
  return points;
}
