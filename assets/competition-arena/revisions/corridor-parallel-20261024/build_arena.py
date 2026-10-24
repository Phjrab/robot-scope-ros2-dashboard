"""blender --background --python build_arena.py -- [output-directory]"""
import sys, math, json, argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import geometry as g
import bpy
from mathutils import Vector
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=g.ROOT);parser.add_argument('--profile',type=Path);parser.add_argument('--no-render',action='store_true');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []);OUT=args.output
profile=json.loads(args.profile.read_text()) if args.profile else {'signal_01':'RED','signal_02':'GREEN','debug_markers':False,'hard_negatives':False}
OUT.mkdir(exist_ok=True,parents=True)
b, walls=g.write_contracts(OUT)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
materials={}
def mat(name,color):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);materials[name]=m;return m
for n,c in {'floor':(.12,.24,.29),'wall':(.68,.76,.77),'ramp':(.27,.48,.57),'stairs':(.34,.56,.64),'stop':(.95,.30,.16),'parking':(.15,.53,.38),'black':(.025,.035,.045),'green':(.08,.85,.22),'red':(.95,.04,.025),'white':(.94,.95,.87)}.items():mat(n,c)
for name in ['green','red']:
 m=materials[name];m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=m.diffuse_color;bs.inputs['Emission Color'].default_value=m.diffuse_color;bs.inputs['Emission Strength'].default_value=.8
records=[];collision=[]
def mesh(name,verts,faces,material,kind='SOLID',semantic=None):
 me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update();ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob);ob.data.materials.append(materials[material]);ob['object_id']=name;ob['collision_kind']=kind
 bbox=[[min(v[k] for v in verts) for k in range(3)],[max(v[k] for v in verts) for k in range(3)]]
 records.append(dict(id=name,bbox_m=bbox,kind=kind,semantic_id=semantic or name))
 if kind=='TERRAIN_SOLID':collision.append(dict(id=name,vertices=verts,faces=faces))
 return ob

def prism(name,poly,z0,z1,material,kind='SOLID',semantic=None):
 n=len(poly);v=[[*p,z0]for p in poly]+[[*p,z1]for p in poly];f=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)];return mesh(name,v,f,material,kind,semantic)
def label(name,text,xyz,size=.22,rotation=(0,0,0)):
 cu=bpy.data.curves.new(name,'FONT');cu.body=text;cu.size=size;cu.align_x='CENTER';cu.align_y='CENTER';ob=bpy.data.objects.new(name,cu);bpy.context.collection.objects.link(ob);ob.location=xyz;ob.rotation_euler=rotation;cu.materials.append(materials['white']);return ob
for name,poly in g.FLOORS.items():prism(name,poly,-.05,0,'parking' if 'parking'in name else 'floor',semantic=name)
for w in walls:
 a,c=w['a'],w['b'];mesh(w['id'],[[*a,0],[*c,0],[*c,.6],[*a,.6]],[(0,1,2,3)],'wall','VIRTUAL_FENCE')
prism('terrain_platform',g.oriented(-.5,.5,-.5,.5),0,.18,'ramp','TERRAIN_SOLID','floor_center_base')
for sign,side in [(-1,'sw'),(1,'ne')]:
 poly=g.oriented(min(sign*.5,sign*1.6),max(sign*.5,sign*1.6),-.5,.5)
 # Closed wedge, lower face at -0.005 avoids degenerate near-zero outer edge.
 vv=[[*xy,-.005]for xy in poly]
 for xy in poly:
  u=(xy[0]-g.C[0]+xy[1]-g.C[1])*g.Q;vv.append([*xy,max(0,.18*(1.6-abs(u))/1.1)])
 mesh('terrain_ramp_'+side,vv,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],'ramp','TERRAIN_SOLID','ramp_'+side)
for sign,side in [(1,'nw'),(-1,'se')]:
 for i in range(2):
  lo=.5+i*.25;hi=lo+.25;poly=g.oriented(-.5,.5,min(sign*lo,sign*hi),max(sign*lo,sign*hi));prism(f'terrain_stairs_{side}_{i+1}',poly,0,.12-i*.06,'stairs','TERRAIN_SOLID','stairs_'+side)
for z in b['semantic_zones']:
 if z['type']=='STOP_ZONE':prism(z['id'],z['polygon'],.181,.184,'stop',semantic=z['id'])
 if z['type']=='TRAFFIC_SIGNAL':
  x=sum(p[0]for p in z['polygon'])/4;y=sum(p[1]for p in z['polygon'])/4
  prism(z['id']+'_post',g.rect(x-.025,y-.025,x+.025,y+.025),0,.75,'black',semantic=z['id'])
  state=profile.get(z['id'],'OFF');assert state in ['RED','GREEN','OFF','AMBIGUOUS'];color={'RED':'red','GREEN':'green','OFF':'black','AMBIGUOUS':'white'}[state]
  prism(z['id'],g.rect(x-.09,y-.06,x+.09,y+.06),.75,.92,color,semantic=z['id'])
label('label_in','IN',(7,5.49,.01),.35);label('label_out','OUT',(7,.509,.01),.35);label('label_parking','P',(7.25,3,.01),.4)
# Realistic dimensions only; QR payload and marker placement remain explicitly unconfirmed.
prism('wall_marker_P',g.rect(7.999,2.75,8.001,2.85),.25,.35,'black','VISUAL_ONLY','zone_parking')
prism('wall_marker_QR_PLACEHOLDER',g.rect(7.999,3.15,8.001,3.25),.25,.35,'white','VISUAL_ONLY','zone_parking')
label('wall_P_glyph','P',(7.996,2.80,.30),.075,(math.pi/2,0,-math.pi/2))
if profile.get('debug_markers'):
 for i,xy in enumerate([g.p(-.35,.05),g.p(-.35,.25)]):prism(f'debug_SIM_frontfoot_{i}',g.rect(xy[0]-.025,xy[1]-.025,xy[0]+.025,xy[1]+.025),.185,.195,'white','VISUAL_ONLY')
 for i,(a,c) in enumerate(zip(g.rect(6.6,2.4,7.2,2.72),g.rect(6.6,2.4,7.2,2.72)[1:]+g.rect(6.6,2.4,7.2,2.72)[:1])):mesh(f'debug_SIM_footprint_{i}',[[*a,.015],[*c,.015],[*c,.025],[*a,.025]],[(0,1,2,3)],'white','VISUAL_ONLY')
if profile.get('hard_negatives'):
 prism('negative_green_background',g.rect(4.7,5.3,5.2,5.6),0,.4,'green','VISUAL_ONLY')
 prism('negative_display_monitor',g.rect(.1,2.5,.3,2.9),0,.4,'black','VISUAL_ONLY')
 label('negative_red_P','P',(.5,3.6,.01),.3).data.materials[0]=materials['red']
label('marker_placeholder_caption','QR ?', (7.25,3.48,.01),.13)
# Scene metadata and export: Blender Z-up to glTF Y-up exactly once.
scene=bpy.context.scene;scene['revision']=g.REV;scene['frame_id']='arena_design';scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
bpy.ops.object.select_all(action='DESELECT')
for ob in bpy.context.scene.objects:
 if ob.type in {'MESH','FONT'}:ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'arena.glb'),export_format='GLB',use_selection=True,export_yup=True)
(OUT/'arena.json').write_text(json.dumps(dict(revision=g.REV,frame_id='arena_design',unit='m',objects=records,source_bounds_m=[[0,0,-.05],[8.001,6,.92]],semantic='arena.semantic.json',gltf_transform='(x,z,-y)',hardware_qualified=False),indent=2)+'\n')
(OUT/'collision/terrain_meshes.json').write_text(json.dumps(dict(frame_id='arena_design',closed_solids=collision,planar_navigation='BLOCKED_TERRAIN_HANDOFF',physics_load_status='NOT_RUN'),indent=2)+'\n')
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=False
scene.render.resolution_x=1100;scene.render.resolution_y=850;scene.render.resolution_percentage=100
scene.world.color=(.35,.35,.35)
ld=bpy.data.lights.new('Key','AREA');lo=bpy.data.objects.new('Key',ld);bpy.context.collection.objects.link(lo);lo.location=(3,-1,9);ld.energy=1600;ld.shape='DISK';ld.size=8
ld=bpy.data.lights.new('Fill','AREA');lo=bpy.data.objects.new('Fill',ld);bpy.context.collection.objects.link(lo);lo.location=(5,7,7);ld.energy=1100;ld.size=6
camd=bpy.data.cameras.new('ReviewCamera');cam=bpy.data.objects.new('ReviewCamera',camd);bpy.context.collection.objects.link(cam);scene.camera=cam;camd.type='ORTHO'
(OUT/'previews').mkdir(exist_ok=True)
def render(name,pos,target,scale):
 cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();camd.ortho_scale=scale;scene.render.filepath=str(OUT/'previews'/f'{name}.png');bpy.ops.render.render(write_still=True)
if not args.no_render:
 render('top',(4,3,15),(4,3,0),9.5)
 render('isometric',(11,-8,11),(4,3,0),11)
 render('terrain_signals',(6,-2,5),(3.3,3,.2),4.5)
 render('parking',(11,0,4),(7.2,3,.2),3.6)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'arena.blend'))
