import { gridToWorld } from '../route_planner/spatial_editor.js';

// Projection and robot rendering belong to the injected existing scene. These
// primitives only visualize supplied geometry; they never assess intersections.
export function createOverlayPainter(canvas, scene) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Overlay canvas unavailable');
  const corners = new Float64Array(24); // one reusable box scratch buffer
  const edges = [[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
  let renderedObjects = 0;
  function line(points, color, width = 2, dashed = false) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dashed ? [5, 5] : []);
    ctx.beginPath(); let started = false;
    for (const xyz of points) {
      const p = scene.project(xyz);
      if (!p) { started = false; continue; }
      if (started) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y);
      started = true;
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
  function box(geometry, color, dashed) {
    const [qx,qy,qz,qw] = geometry.orientation_xyzw;
    for (let i = 0; i < 8; i++) {
      const x = geometry.extent_m[0] * (i & 1 ? .5 : -.5);
      const y = geometry.extent_m[1] * (i & 2 ? .5 : -.5);
      const z = geometry.extent_m[2] * (i & 4 ? .5 : -.5);
      const tx = 2 * (qy*z - qz*y), ty = 2 * (qz*x - qx*z), tz = 2 * (qx*y - qy*x);
      corners[i*3] = geometry.center_m[0] + x + qw*tx + qy*tz - qz*ty;
      corners[i*3+1] = geometry.center_m[1] + y + qw*ty + qz*tx - qx*tz;
      corners[i*3+2] = geometry.center_m[2] + z + qw*tz + qx*ty - qy*tx;
    }
    for (const [a,b] of edges) line([corners.subarray(a*3,a*3+3), corners.subarray(b*3,b*3+3)], color, 2, dashed);
  }
  function draw(view, layers, selected, theme) {
    const rect = scene.canvas.getBoundingClientRect();
    const ratio = Math.min(2.5, globalThis.devicePixelRatio || 1);
    const w = Math.max(1, rect.width), h = Math.max(1, rect.height);
    if (canvas.width !== Math.round(w*ratio) || canvas.height !== Math.round(h*ratio)) {
      canvas.width = Math.round(w*ratio); canvas.height = Math.round(h*ratio);
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, w, h);
    renderedObjects = 0;
    if (!view.ready) return;
    const dark = theme !== 'light';
    if (layers.costmap) for (const c of view.costmaps) {
      const v = c.value; if (!v) continue;
      const map = { ...v, resolution: v.resolution_m };
      for (let i = 0; i < v.cells.length; i++) {
        const cost = v.cells[i]; if (cost === 0) continue;
        const x = i % v.width, y = Math.floor(i / v.width);
        // Reuse the existing occupancy-grid origin/yaw helper. Its Y input is
        // image-down; incoming cost cells are grid-up.
        const quad = [[x,y],[x+1,y],[x+1,y+1],[x,y+1]].map(([gx,gy]) => {
          const p = gridToWorld(map, gx, v.height-gy); return scene.project([p.x,p.y,v.plane_z_m]);
        });
        if (quad.some(p => !p)) continue;
        ctx.fillStyle = cost === -1 || cost === 255 ? (dark ? '#9ba9bb45' : '#44556a45') : cost >= 253 ? '#f06a4b99' : '#e3af3d55';
        ctx.beginPath(); quad.forEach((p,j) => j ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y)); ctx.closePath(); ctx.fill();
      }
    }
    if (layers.path) {
      for (const p of view.history) if (p.value.generation !== view.path.value?.generation) line(p.value.points_m, dark ? '#8e9fb7' : '#66768c', 1.5, true);
      if (view.path.value) line(view.path.value.points_m, dark ? '#70b7ff' : '#1262b5', 3);
    }
    if (layers.local && view.local.value) line(view.local.value.points_m, dark ? '#c7a1ff' : '#7e3fc3', 3, true);
    for (const source of view.sources) {
      if (!layers[source.id] || !source.value || source.value.health !== 'OK') continue;
      ctx.fillStyle = source.kind === 'DEPTH' ? '#c296ff' : '#45cfc5';
      for (const xyz of source.value.points_m) { const p = scene.project(xyz); if (p) ctx.fillRect(p.x-1.5,p.y-1.5,3,3); }
    }
    if (layers.obstacles) for (const object of view.obstacles.value?.obstacles || []) {
      box(object.geometry, object.track_id === selected ? '#ffdc74' : '#f1a55a', object.state !== 'OBSERVED');
      const p = scene.project(object.geometry.center_m);
      if (p) {
        ctx.font = '12px system-ui'; ctx.fillStyle = dark ? '#fff1d5' : '#39220a';
        ctx.fillText(`${object.track_id} · ${object.class_name}`, p.x+8,p.y-10);
      }
      renderedObjects++;
    }
    if (layers.envelope && view.collision.value) for (const e of view.collision.value.envelopes) {
      box(e.geometry, view.collision.value.severity === 'CLEAR' ? '#50cdaa' : '#ff6c73', e.kind.includes('sweep'));
    }
  }
  return { draw, diagnostics: () => ({ boxScratchBytes: corners.byteLength, renderedObjects }),
    clear() { ctx.clearRect(0,0,canvas.width,canvas.height); } };
}
