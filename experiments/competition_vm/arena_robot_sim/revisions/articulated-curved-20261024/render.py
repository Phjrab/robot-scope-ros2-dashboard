"""Render saved planar trace plus separately labeled offline articulated IK animation."""
import bpy,json,math,sys,argparse
from pathlib import Path
from mathutils import Matrix,Vector,Euler
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[4]
sys.path.insert(0,str(HERE)); from gait import fk as dynamic_fk; import numpy as np
p=argparse.ArgumentParser();p.add_argument('--trace',default='cone_detour');p.add_argument('--trace-path');p.add_argument('--arena-path');p.add_argument('--frames',type=int,default=80);p.add_argument('--preview',action='store_true');p.add_argument('--view',choices=['oblique','top'],default='oblique');a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
trace_path=Path(a.trace_path) if a.trace_path else HERE.parents[1]/'results'/f'{a.trace}.json'
d=json.loads(trace_path.read_text());asset=json.loads((ROOT/'robot_dashboard/static/assets/go2/go2-official-lite.json').read_text())
joints=json.loads((HERE/'output'/f'{a.trace}_joints.json').read_text())['records']
bpy.ops.wm.open_mainfile(filepath=str(Path(a.arena_path) if a.arena_path else ROOT/'assets/competition-arena/revisions/rulebook-20261015/arena.blend'))
s=bpy.context.scene;s.render.engine='BLENDER_WORKBENCH';s.cycles.device='CPU';s.cycles.samples=12;s.cycles.use_denoising=False;s.render.resolution_x=960;s.render.resolution_y=720;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.threads_mode='FIXED';s.render.threads=6
s.world.color=(.22,.22,.22)
# Display-only shortened fences keep feet visible; collision/sensor traces unchanged.
for ob in s.objects:
 if ob.get('collision_kind')=='VIRTUAL_FENCE':ob.scale.z=.08
def mat(name,color):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);return m
def mesh(name,v,f,m):
 me=bpy.data.meshes.new(name);me.from_pydata(v,[],f);me.update();ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);ob.data.materials.append(m);return ob
orange=mat('Cone orange',(1,.18,.015));white=mat('Cone white',(.95,.95,.9));black=mat('Cone base',(.025,.03,.035));cyan=mat('Sensor returns',(.02,.95,.9));trail=mat('Executed SIM_GT',(.9,.65,.04))
def origin(o):return Matrix.Translation(Vector(o['xyz']))@Euler(o['rpy'],'XYZ').to_matrix().to_4x4()
T={'base':Matrix.Identity(4)}
for j in asset['skeleton']['joints']:
 q=asset['skeleton']['default_joint_positions'].get(j['name'],0)
 T[j['child']]=T[j['parent']]@origin(j['origin'])@(Matrix.Rotation(q,4,Vector(j['axis'])) if q else Matrix.Identity(4))
robot=bpy.data.objects.new('Go2_SYNTHETIC_KINEMATIC_ANIMATION',None);s.collection.objects.link(robot)
link_objects=[]
for link in asset['skeleton']['links']:
 m=asset['meshes'][link['mesh']];vq=m['vertices_q'];v=[tuple(Vector(vq[i:i+3])*m['quantization_m']) for i in range(0,len(vq),3)]
 for gi,g in enumerate(m['groups']):
  c=g['color'].lstrip('#');color=tuple(int(c[i:i+2],16)/255 for i in (0,2,4));idx=g['indices'];ob=mesh(link['name']+str(gi),v,[idx[i:i+3] for i in range(0,len(idx),3)],mat(link['name']+str(gi),color));ob.parent=robot;ob.matrix_local=T[link['name']]@origin(link['visual_origin']);link_objects.append((ob,link))
for cone in d['scene']['cones']:
 x,y=cone['xy'];b=cone['base_side_m'];bh=cone['base_height_m'];h=cone['height_m'];r=cone['radius_m']
 bpy.ops.mesh.primitive_cube_add(size=1,location=(x,y,bh/2));ob=bpy.context.object;ob.name=cone['id']+'_square_base';ob.dimensions=(b,b,bh);ob.data.materials.append(black)
 # Frustum bands lie on exactly the same 32-sided cone as sensor geometry.
 for k,(z0,z1) in enumerate(((bh,.12),(.12,.21),(.21,h))):
  r0=r*(h-z0)/(h-bh);r1=r*(h-z1)/(h-bh)
  vv=[(x+rr*math.cos(i*math.tau/32),y+rr*math.sin(i*math.tau/32),z) for z,rr in ((z0,r0),(z1,r1)) for i in range(32)]
  mesh(cone['id']+'_band'+str(k),vv,[(i,(i+1)%32,(i+1)%32+32,i+32) for i in range(32)],white if k==1 else orange)
def line(name,pts,radius,material):
 cu=bpy.data.curves.new(name,'CURVE');cu.dimensions='3D';cu.bevel_depth=radius;cu.bevel_resolution=1;sp=cu.splines.new('POLY');sp.points.add(len(pts)-1)
 for p,v in zip(sp.points,pts):p.co=(*v,1)
 ob=bpy.data.objects.new(name,cu);s.collection.objects.link(ob);ob.data.materials.append(material);return ob
for name,xy,color in [('START',d['scene']['start'][:2],(.1,.6,1)),('GOAL',d['scene']['goal'],(.3,1,.2))]:
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.18,depth=.008,location=(*xy,.009));bpy.context.object.data.materials.append(mat(name,color))
cam=bpy.data.objects.new('Simulation_camera',bpy.data.cameras.new('Simulation_camera'));s.collection.objects.link(cam);s.camera=cam;cam.data.type='ORTHO'
def camera(loc,target,scale):cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
out=HERE/'output'/a.trace;out.mkdir(exist_ok=True);(out/'frames').mkdir(exist_ok=True)
pointob=None;pathob=None
def frame(i):
 global pointob,pathob
 jf=joints[i]; nearest=max(k for k in range(len(d['frames'])) if d['frames'][k]['t']<=jf['t']+1e-10);f=dict(d['frames'][nearest]);f['pose']=jf['pose'];f['t']=jf['t'];robot.location=(*f['pose'][:2],.33407456);robot.rotation_euler=(0,0,f['pose'][2])
 TT=dynamic_fk(asset,jf['q'])
 for ob,link in link_objects:ob.matrix_local=Matrix(TT[link['name']].tolist())@origin(link['visual_origin'])
 for ob in (pointob,pathob):
  if ob:bpy.data.objects.remove(ob,do_unlink=True)
 v=[];faces=[]
 for pt in f['points'][::2]:
  x,y,z=pt[:3];n=len(v);r=.012;v.extend([(x-r,y-r,z),(x+r,y-r,z),(x,y+r,z),(x,y,z+r*2)]);faces.extend([(n,n+1,n+2),(n,n+1,n+3),(n+1,n+2,n+3),(n+2,n,n+3)])
 pointob=mesh('Measured_virtual_LiDAR_returns',v,faces,cyan)
 pts=[(*p['pose'][:2],.025) for p in joints[:i+1]];pathob=line('Executed_not_planned_path',pts if len(pts)>1 else pts*2,.018,trail)
 return f
if a.preview:
 frame(len(d['frames'])//2);camera((12,-8,12),(4,3,0),10.2);s.render.filepath=str(out/'arena_oblique.png');bpy.ops.render.render(write_still=True)
 camera((6.5,-3,8),(6.2,3,.1),5.4);s.render.filepath=str(out/'detour_close.png');bpy.ops.render.render(write_still=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'arena_robot_sim.blend'))
else:
 s.render.resolution_x=960;s.render.resolution_y=640
 camera((6.5,-3,8),(6.2,3,.1),5.4)
 if a.view=='top':camera((6.2,3,10),(6.2,3,0),4.4)
 ids=sorted(set(round(j*(len(joints)-1)/max(1,a.frames-1)) for j in range(a.frames)));meta=[]
 for n,i in enumerate(ids):
  f=frame(i);x,y=f['pose'][:2];camera((x+2.6,y-3.2,2.6),(x,y,.22),2.3);meta.append({'image':n,'trace_index':i,'t':f['t'],'state':f['state']});s.render.filepath=str(out/'frames'/f'{n:04}.png');bpy.ops.render.render(write_still=True)
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'articulated_scene.blend'))
 (out/'rendered_frame_indices.json').write_text(json.dumps(meta,indent=2))
