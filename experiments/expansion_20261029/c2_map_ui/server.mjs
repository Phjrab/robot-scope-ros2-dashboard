// Static allowlisted loopback fixture host. No robot / ROS / API proxy.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.woff2':'font/woff2','.svg':'image/svg+xml'};
export function startServer(port=4182){
  const server=createServer(async(req,res)=>{
    const pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
    if(pathname==='/c1-exact.json' && process.env.C2_C1_FIXTURE?.startsWith('/tmp/') && req.method==='GET'){try{res.writeHead(200,{'Content-Type':'application/json'});res.end(await readFile(process.env.C2_C1_FIXTURE));}catch{res.end('{}');}return;}
    if(pathname.startsWith('/api/v1/extensions/multimap/') && /^http:\/\/127\.0\.0\.1:\d+$/.test(process.env.C2_C1_SERVICE_URL||'')){
      const target=process.env.C2_C1_SERVICE_URL;const body=[];for await(const chunk of req)body.push(chunk);
      const response=await fetch(target+pathname,{method:req.method,headers:{'Authorization':'Bearer public-c2-exact-synthetic-only-bearer','Origin':target,'Content-Type':'application/json'},body:req.method==='GET'?undefined:Buffer.concat(body)});
      res.writeHead(response.status,{'Content-Type':'application/json'});res.end(await response.text());return;
    }
    const relative=pathname==='/'?'experiments/expansion_20261029/c2_map_ui/host.html':pathname.slice(1);
    const file=path.resolve(root,relative);
    const allowed=['experiments/expansion_20261029/c2_map_ui/','robot_dashboard/static/features/multimap_fusion/','robot_dashboard/static/fonts/'];
    const exact=['robot_dashboard/static/styles.css','robot_dashboard/static/scene3d.js'];
    if(req.method!=='GET'||!file.startsWith(root)||(!allowed.some(p=>relative.startsWith(p))&&!exact.includes(relative))){res.writeHead(403);res.end('Fixture host: denied');return;}
    try{const body=await readFile(file);res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(body);}catch{res.writeHead(404);res.end('Not found');}
  });
  return new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',()=>resolve(server));});
}
if(process.argv[1]===fileURLToPath(import.meta.url)){const server=await startServer(Number(process.env.C2_PORT||4182));console.log(`C2 synthetic fixture host http://127.0.0.1:${server.address().port}`);}
