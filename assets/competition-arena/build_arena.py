#!/usr/bin/env python3
"""Rebuild the competition arena in Blender 4.3+; no add-ons or network required.
Usage: blender -b --python build_arena.py -- --output-dir /path/to/output
Source coordinates: metres, Z-up. See arena.json and ASSUMPTIONS.md.
"""
import bpy, bmesh, math, os, sys, json, hashlib, csv, argparse
from mathutils import Vector
from pathlib import Path

argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',default=str(Path(__file__).resolve().parent)); parser.add_argument('--skip-renders',action='store_true')
args=parser.parse_args(argv); OUT=Path(args.output_dir); OUT.mkdir(parents=True,exist_ok=True)
SOURCE_DIR=Path('/workspace/scratch/b09eacf6919d/course_images')
SOURCES=[('S01','KakaoTalk_Photo_2026-10-19-13-43-02 001.png',100131,'Dimensioned isometric overview'),('S02','KakaoTalk_Photo_2026-10-19-13-43-02 002.png',47099,'Ramp and stair detail'),('S03','KakaoTalk_Photo_2026-10-19-13-43-02 003.png',115601,'Dimensioned annotated plan'),('S04','KakaoTalk_Photo_2026-10-19-13-43-03 004.png',95144,'Alternate isometric overview')]
DIMS=[
 {'id':'overall_x','label':'전체 가로','value_m':8.0,'status':'explicit','source':'S01/S03/S04: 8000 mm','uncertainty':'Drawing nominal dimension; physical venue not surveyed.'},
 {'id':'overall_y','label':'전체 세로','value_m':6.018,'status':'explicit','source':'S01/S03/S04: 6018 mm','uncertainty':'Drawing nominal dimension; physical venue not surveyed.'},
 {'id':'left_length','label':'좌측 직선 구간 길이','value_m':5.018,'status':'explicit','source':'S01/S03/S04: 5018 mm','uncertainty':'Location within global bounds is raster-derived.'},
 {'id':'wall_height','label':'벽 높이','value_m':0.6,'status':'explicit','source':'S01/S04: vertical 600 mm callout','uncertainty':'Wall thickness is not specified.'},
 {'id':'right_corridor_width','label':'우측 복도 폭','value_m':1.0,'status':'explicit','source':'S01/S03/S04: 1000 mm across right corridor','uncertainty':'1.0 m clear distance is preserved using zero-thickness wall surfaces; physical wall thickness is unspecified.'},
 {'id':'ramp_run','label':'경사로 한쪽 수평 길이','value_m':1.1,'status':'explicit','source':'S02: 1100 mm, supported by S03 3200 mm total','uncertainty':'Interpreted as horizontal plan run, not surface length.'},
 {'id':'platform_height','label':'교차부 높이','value_m':0.18,'status':'explicit','source':'S02: 180 mm','uncertainty':'Nominal top surface above course datum.'},
 {'id':'stair_riser','label':'계단 단높이','value_m':0.06,'status':'explicit','source':'S02: levels 60/120/180 mm','uncertainty':'Three risers; two exposed treads plus the top platform.'},
 {'id':'stair_tread','label':'계단 디딤판 깊이','value_m':0.25,'status':'explicit','source':'S02: two 250 mm dimensions','uncertainty':'Two exposed treads on each side.'},
 {'id':'ramp_total_length','label':'경사로 방향 전체 장애물 길이','value_m':3.2,'status':'explicit','source':'S01/S03/S04: 3200 mm','uncertainty':'Includes two ramps and central 1 m platform.'},
 {'id':'stairs_total_length','label':'계단 방향 전체 장애물 길이','value_m':2.0,'status':'explicit','source':'S01/S03/S04: 2000 mm','uncertainty':'Includes four 0.25 m treads and central 1 m platform.'},
 {'id':'platform_width','label':'중앙 평탄부 한 변','value_m':1.0,'status':'derived','source':'3.2 - 2×1.1 = 1.0; also 2.0 - 4×0.25 = 1.0','uncertainty':'Square platform interpretation follows S02/S03.'}]
ASSUMPTIONS=[
 {'id':'A01','item':'도면 축척 및 평면 꼭짓점','value':'x=(pixel_x-118)×8/739; y=(657-pixel_y)×6.018/555; 주요 꼭짓점 반올림','status':'estimated','source':'S03 raster trace, dimensions anchor the bounding box','confirmation_needed':'원본 CAD 또는 현장 실측으로 각 분기/회전 코너 위치 확인. 래스터 판독 오차 미검증, 실측 필요.'},
 {'id':'A02','item':'중앙 교차부 위치/방향','value':'(3.303, 3.009, 0) m; 대각선 ±45°','status':'estimated','source':'S03 central diamond and corridor slopes','confirmation_needed':'교차부 정확한 X/Y 위치 및 각도 확인.'},
 {'id':'A03','item':'일반 복도 및 장애물 폭','value':'1.0 m nominal','status':'derived','source':'S03 explicit right corridor 1000; S02/S03 3200/2000/1100/250 derive 1 m platform','confirmation_needed':'우측 외 다른 구간의 정확한 폭은 직접 명시되지 않음. 대부분 래스터를 따르므로 일부 회전부 폭은 다름.'},
 {'id':'A04','item':'벽 두께와 기준선','value':'물리 두께 미정; 기본 모델은 양면 surface, 두께 0 m','status':'estimated','source':'S01/S04 depict walls but no thickness dimension','confirmation_needed':'명시된 1 m 복도 폭과 8×6.018 m 전체 경계를 모두 보존하기 위해 두께를 임의로 넣지 않음. 실제 벽 두께/치수 기준 확인 후 충돌용 솔리드 제작 필요. 바깥쪽 0.04 m 두께를 가정하면 전체 벽 외곽은 약 8.08×6.098 m가 되어 현재 미적용.'},
 {'id':'A05','item':'바닥판 두께','value':'0.06 m; top z=0, underside z=-0.06','status':'estimated','source':'Rendering/mesh thickness only, not specified in drawings','confirmation_needed':'실제 바닥 구조 두께 확인. 주행 기준 높이는 z=0 유지.'},
 {'id':'A06','item':'IN/OUT 구역 크기','value':'2.0×1.0 m nominal','status':'estimated','source':'S03 raster trace: x=6..8; y=0..1 / 5.018..6.018','confirmation_needed':'영역의 정확한 크기와 물리적 출입 개구 위치 확인. S01/S04를 따라 외곽벽은 닫힌 형태로 유지.'},
 {'id':'A07','item':'주차 구역','value':'1.0×1.0 m; x=7..8, y=2.5..3.5','status':'estimated','source':'S03 raster trace, red P outline','confirmation_needed':'주차면 실측 크기와 위치 확인.'},
 {'id':'A08','item':'경사로 1100 해석','value':'수평 run=1.1 m, rise=0.18 m; surface=1.11463 m; grade=16.364%, angle=9.293°','status':'derived','source':'S02 with S03 3200 total','confirmation_needed':'1100이 수평 투영인지 실제 경사면 길이인지 원본 CAD로 확인.'},
 {'id':'A09','item':'신호등','value':'symbol centers=(2.295,3.009)/(4.341,3.009) m; total height 0.84 m; base 0.32×0.32 m','status':'estimated','source':'S03 blue markers indicate position only; physical fixture shape not specified','confirmation_needed':'실제 신호등 위치/치수/정지선 연동 및 방향 확인. 렌더링용 신호 상태는 시뮬레이션 동작이 아님.'},
 {'id':'A10','item':'정지선','value':'width=0.045 m; on SW/SE platform edges; black','status':'estimated','source':'S03 black segments adjacent to signal labels','confirmation_needed':'정지선 폭/정확한 위치/색상 및 신호별 주행 방향 확인.'},
 {'id':'A11','item':'슬라럼 영역','value':'x=0.10..0.90, y=2.50..3.50 m; no cones created','status':'estimated','source':'S03 라바콘 슬라럼 label, no cone center dimensions','confirmation_needed':'콘 개수/간격/좌표는 미지정. 기본 모델에 콘을 임의 배치하지 않음.'},
 {'id':'A12','item':'재질/표시','value':'neutral gray walls/floor; teal ramp; blue IN/OUT and slalom tint; red parking outline','status':'estimated','source':'S01/S04 gray CAD; S03 semantic text/marking colors','confirmation_needed':'재질과 보조 색상은 시각화용이며 실제 현장 색상/마찰계수가 아님.'},
 {'id':'A13','item':'전체 바운딩박스와 좌측 세로 배치','value':'left corridor y=0.500..5.518 m','status':'derived','source':'(6.018-5.018)/2 = 0.500; S03 roughly symmetric','confirmation_needed':'좌측 구간 상하 오프셋 대칭 여부 확인.'},
 {'id':'A14','item':'IN/OUT/P 및 보조 글자','value':'flat mesh labels z≈0.005 m; font sizes 0.10..0.25 m','status':'estimated','source':'S03 text semantics','confirmation_needed':'문구는 도면 의미를 보존하되 글꼴/배치는 가독성을 위해 조정.'},
]
META={'schema_version':'1.0.0','title':'Competition arena — drawing-based reconstruction','description':'Attached competition drawings reconstructed as a visualization model. Not a surveyed venue, validated navigation map, or physics-certified scene.','coordinate_system':{'unit':'metre','origin':'Lower-left of the entire S03 plan bounding rectangle, at course floor top. x=0 is leftmost outer boundary; y=0 is OUT-side lowest outer boundary; z=0 is flat course level.','source_axes':{'x':'plan right','y':'plan up','z':'vertical up'},'gltf_axes':{'x':'source +X','y':'source +Z (up)','z':'source -Y'},'gltf_transform':{'formula':'(x_glTF,y_glTF,z_glTF) = (x_source,z_source,-y_source)','matrix_4x4_row_major':[[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],'exporter':'Blender glTF 2.0, export_yup=True','recentered':False},'bounds_xy_m':{'min':[0,0],'max':[8.0,6.018]},'heading_convention':'Source yaw 0 points +X; positive yaw counterclockwise toward +Y.'},'dimensions':DIMS,'assumptions':ASSUMPTIONS,'sources':[],'objects':[],'validation':{'status':'visual_reconstruction_only','navigation_map_validated':False,'localization_validated':False,'collision_physics_validated':False,'source_geometry':'Dimension-anchored raster trace; no original CAD available.','notes':['No cones created: count and coordinates are absent.','GLB is a visualization asset; no occupancy grid, Nav2 map, URDF, or robot collision test is claimed.','Right clear corridor width is 1 m. Walls are double-sided zero-thickness surfaces so both this width and the 8×6.018 m overall footprint are preserved. Physical thickness remains unspecified.']}}
for sid,fn,size,desc in SOURCES:
 p=SOURCE_DIR/fn
 META['sources'].append({'id':sid,'filename':fn,'description':desc,'expected_size_bytes':size,'local_size_bytes':p.stat().st_size if p.exists() else None,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None,'comparison':'Existing local file size matches latest reattachment metadata; reattachment bytes unavailable for independent hash comparison.','source_unmodified':True})
def write_meta(): (OUT/'arena.json').write_text(json.dumps(META,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
write_meta()
# Reset scene.
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for c in list(bpy.data.collections):
 if c.name!='Collection' and c.users==0:bpy.data.collections.remove(c)
scene=bpy.context.scene; scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
collections={}
for name in ['01_Floor','02_Walls','03_Ramps_and_Stairs','04_Signals','05_Markings','06_Labels','07_Zones','90_Presentation']:
 c=bpy.data.collections.new(name); scene.collection.children.link(c);collections[name]=c

def material(name,color,metallic=0,roughness=.65):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;n=m.node_tree.nodes.get('Principled BSDF');n.inputs['Base Color'].default_value=(*color,1);n.inputs['Roughness'].default_value=roughness;n.inputs['Metallic'].default_value=metallic;return m
MAT={'floor':material('Floor • warm concrete',(.32,.37,.40)), 'wall':material('Walls • cool ivory',(.67,.72,.75)), 'ramp':material('Ramp • muted teal',(.21,.46,.48)), 'stairs':material('Stairs • blue gray',(.34,.44,.50)), 'platform':material('Crossing • pale concrete',(.66,.72,.73)), 'black':material('Stop line • charcoal',(.035,.045,.06)), 'white':material('Letters • chalk white',(.94,.96,.97)), 'yellow':material('Ramp edge • ochre',(.96,.69,.13)), 'blue':material('Zones • blue',(.16,.31,.53)), 'zone':material('Zone tint • desaturated blue',(.09,.23,.39)), 'red':material('Parking • vermilion',(.84,.12,.085)), 'metal':material('Signal posts • graphite',(.11,.14,.18),.5,.35),'green':material('Signal green illustrative',(.08,.60,.31)), 'amber':material('Signal amber illustrative',(.87,.52,.08)), 'red_lens':material('Signal red illustrative',(.66,.07,.04))}

OBJECT_META={}
def register(obj,category,collection,mat=None,status='estimated',source='S03',uncertainty='',extra=None):
 for c in list(obj.users_collection):c.objects.unlink(obj)
 collections[collection].objects.link(obj)
 if mat:obj.data.materials.append(MAT.get(mat,mat))
 obj['arena_id']=obj.name;obj['category']=category;obj['source']=source;obj['status']=status;obj['uncertainty']=uncertainty
 obj['source_unit']='metre';obj['source_up_axis']='Z'
 OBJECT_META[obj.name]={'id':obj.name,'name':obj.name,'category':category,'collection':collection,'status':status,'source':source,'uncertainty':uncertainty,'visible_default':collection!='90_Presentation'}
 if extra:OBJECT_META[obj.name].update(extra)
 return obj

def mesh(name,verts,faces,cat,coll,mat,**kw):
 me=bpy.data.meshes.new(name+'_mesh');me.from_pydata(verts,[],faces);me.update();ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob);return register(ob,cat,coll,mat,**kw)

def prism(name,poly,z0,z1,cat='floor',coll='01_Floor',mat='floor',**kw):
 n=len(poly); verts=[(x,y,z0) for x,y in poly]+[(x,y,z1) for x,y in poly];faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
 return mesh(name,verts,faces,cat,coll,mat,**kw)

def box(name,loc,scale,cat,coll,mat,rotation=0,**kw):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);ob=bpy.context.object;ob.name=name;ob.dimensions=scale;ob.rotation_euler.z=rotation;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);return register(ob,cat,coll,mat,**kw)

def line_box(name,a,b,z,width,height,cat='marking',coll='05_Markings',mat='black',**kw):
 dx=b[0]-a[0];dy=b[1]-a[1]
 return box(name,((a[0]+b[0])/2,(a[1]+b[1])/2,z+height/2),(math.hypot(dx,dy),width,height),cat,coll,mat,math.atan2(dy,dx),**kw)

q=2**-.5; C=(3.303,3.009);U=(q,q);V=(-q,q)
def p(u,v):return (C[0]+u*U[0]+v*V[0],C[1]+u*U[1]+v*V[1])
N=p(.5,.5);W=p(-.5,.5);S=p(-.5,-.5);E=p(.5,-.5)
A=(1.11,4.49);B=(1.83,5.20);D=(1.11,1.52);F=(1.83,.81);G=(5.27,5.68);H=(6.,5.018);I=(5.27,.34);J=(6.,1.)
floors={
 'floor_left_straight':[(0,.5),(1,.5),(1,5.518),(0,5.518)],
 'floor_nw_turn':[(1,4.49),A,B,(1.414,5.518),(1,5.518)],
 'floor_nw_diagonal':[A,W,N,B],
 'floor_sw_turn':[(1,.5),(1.414,.5),F,D,(1,1.52)],
 'floor_sw_diagonal':[D,F,S,W],
 'floor_center_base':[S,E,N,W],
 'floor_ne_diagonal':[N,E,H,G],
 'floor_ne_turn':[G,H,(6,6.018),(5.597,6.018)],
 'floor_in_bay':[(6,5.018),(8,5.018),(8,6.018),(6,6.018)],
 'floor_right_straight':[(6,1),(7,1),(7,5.018),(6,5.018)],
 'floor_parking_bay':[(7,2.5),(8,2.5),(8,3.5),(7,3.5)],
 'floor_out_bay':[(6,0),(8,0),(8,1),(6,1)],
 'floor_se_turn':[(5.597,0),(6,0),J,I],
 'floor_se_diagonal':[S,I,J,E]}
for name,poly in floors.items():prism(name,poly,-.06,0,source='S03 dimension-anchored raster trace; S01/S04 topology',uncertainty='Plan endpoints approximated from raster; floor thickness 0.06 m is estimated (A01/A05).',extra={'footprint_xy_m':poly,'floor_top_z_m':0})

outer=[(0,.5),(1.414,.5),F,S,I,(5.597,0),(8,0),(8,1),(7,1),(7,2.5),(8,2.5),(8,3.5),(7,3.5),(7,5.018),(8,5.018),(8,6.018),(5.597,6.018),G,N,B,(1.414,5.518),(0,5.518)]
left_hole=[(1,1.52),D,W,A,(1,4.49)]
right_hole=[J,H,E]
def area(poly):return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))/2

def inward_offset(poly,t):
 # Polygon left side is always the course, including clockwise hole outlines.
 out=[]
 for k,v in enumerate(poly):
  a=Vector(poly[k-1]);b=Vector(v);c=Vector(poly[(k+1)%len(poly)]);d1=(b-a).normalized();d2=(c-b).normalized();n1=Vector((-d1.y,d1.x));n2=Vector((-d2.y,d2.x));l1=b+t*n1;l2=b+t*n2;cross=d1.x*d2.y-d1.y*d2.x
  if abs(cross)<1e-7:o=b+t*n1
  else:
   delta=l2-l1;s=(delta.x*d2.y-delta.y*d2.x)/cross;o=l1+s*d1
  out.append(tuple(o))
 return out
for label,poly,is_hole in [('outer',outer,False),('left_inner',left_hole,True),('right_inner',right_hole,True)]:
 if (area(poly)<0)!=is_hole:poly=list(reversed(poly))
 # Physical wall thickness intentionally unspecified; preserve boundary and clear width.
 for k in range(len(poly)):
  j=(k+1)%len(poly);mesh(f'wall_{label}_{k+1:02d}',[(poly[k][0],poly[k][1],0),(poly[j][0],poly[j][1],0),(poly[j][0],poly[j][1],.6),(poly[k][0],poly[k][1],.6)],[(0,1,2,3)],'wall','02_Walls','wall',status='mixed',source='S01/S04 wall height 600; S03 raster outlines',uncertainty='0.6 m height explicit; actual thickness unspecified: modeled as double-sided zero-thickness surface to preserve explicit clear width and footprint (A04). Raster endpoints estimated (A01).',extra={'height_m':.6,'thickness_m':None,'modeled_surface_thickness_m':0,'double_sided':True,'boundary_line_xy_m':[poly[k],poly[j]]})

# Central square, exact raised crossing; two opposite ramps and two stair flights.
prism('floor_raised_crossing',[p(-.5,-.5),p(.5,-.5),p(.5,.5),p(-.5,.5)],0,.18,'platform','03_Ramps_and_Stairs','platform',status='derived',source='S02 height 180; S03 total dimensions 3200/2000',uncertainty='1 m square derived; placement/45° orientation estimated (A02).',extra={'height_m':.18,'side_length_m':1.0})
for sign,label in [(-1,'sw'),(1,'ne')]:
 u0=sign*.5;u1=sign*1.6
 poly=[p(u0,-.5),p(u1,-.5),p(u1,.5),p(u0,.5)]
 # Bottom face and top wedge, all positions stay in source coordinates.
 verts=[(x,y,0) for x,y in poly]+[(poly[0][0],poly[0][1],.18),(poly[3][0],poly[3][1],.18)]
 mesh('ramp_'+label,verts,[(0,3,2,1),(4,1,2,5),(0,1,4),(2,3,5),(3,0,4,5)],'ramp','03_Ramps_and_Stairs','ramp',status='mixed',source='S02 1100 run/180 rise; S03 3200 total',uncertainty='Horizontal run interpretation; nominal 1 m width derived; position estimated (A02/A08).',extra={'run_m':1.1,'rise_m':.18,'width_m':1.,'surface_length_m':math.hypot(1.1,.18),'slope_deg':math.degrees(math.atan2(.18,1.1)),'footprint_xy_m':poly})
 # Yellow short boundary line at the floor-side foot of each ramp, shown in S03.
 line_box('marking_ramp_foot_'+label,p(u1,-.5),p(u1,.5),.002,.023,.003,mat='yellow',source='S03 yellow ramp extent line',uncertainty='0.023 m width and color material estimated.')
for sign,label in [(1,'nw'),(-1,'se')]:
 for step,(near,far,height) in enumerate([(.75,1.,.06),(.5,.75,.12)],start=1):
  poly=[p(-.5,sign*near),p(.5,sign*near),p(.5,sign*far),p(-.5,sign*far)]
  prism(f'stair_{label}_tread_{step:02d}',poly,0,height,'stair','03_Ramps_and_Stairs','stairs',status='mixed',source='S02 60/120/180 and 250/250; S03 direction',uncertainty='Tread dimensions explicit; 1 m width derived; center position estimated.',extra={'tread_depth_m':.25,'width_m':1.,'top_z_m':height,'riser_height_m':.06})
 line_box('marking_stair_foot_'+label,p(-.5,sign),p(.5,sign),.002,.023,.003,mat='yellow',source='S03 yellow stair extent line',uncertainty='0.023 m width estimated.')
line_box('marking_stop_line_01',W,S,.181,.045,.003,source='S03 black SW crossing edge/신호등1 정지선',uncertainty='Line width, height and exact alignment inferred (A10).')
line_box('marking_stop_line_02',S,E,.181,.045,.003,source='S03 black SE crossing edge/신호등2 정지선',uncertainty='Line width, height and exact alignment inferred (A10).')

# Semantic floor areas are separate from physical floor cells.
box('zone_in',(6.98,5.50,.002),(1.70,.62,.003),'zone','07_Zones','zone',source='S03 IN 입구',uncertainty='Tint is presentation-only; bay boundary geometry traced.')
box('zone_out',(6.98,.50,.002),(1.70,.62,.003),'zone','07_Zones','zone',source='S03 OUT 출구',uncertainty='Tint is presentation-only; bay boundary geometry traced.')
box('zone_slalom',(.50,3.0,.002),(.80,1.0,.003),'zone','07_Zones','zone',source='S03 라바콘 슬라럼 annotation',uncertainty='Region extent approximate (A11). No cones created.',extra={'cones_defined':False})
box('zone_parking',(7.5,3.0,.002),(.84,.84,.003),'zone','07_Zones','floor',source='S03 P 주차',uncertainty='1 m nominal bay inferred from raster (A07).')
for k,(a,b) in enumerate([((7.07,2.57),(7.93,2.57)),((7.93,2.57),(7.93,3.43)),((7.93,3.43),(7.07,3.43)),((7.07,3.43),(7.07,2.57))]):line_box(f'marking_parking_outline_{k+1}',a,b,.005,.025,.003,mat='red',source='S03 red parking rectangle',uncertainty='Inset and line thickness estimated.')

# Signals are illustrative fixtures at the two source symbols; all dimensions assumed.
def cylinder(name,loc,r,depth,mat,rotation=(0,0,0),cat='signal',coll='04_Signals',**kw):
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=r,depth=depth,location=loc,rotation=rotation);ob=bpy.context.object;ob.name=name;return register(ob,cat,coll,mat,**kw)
for idx,x in [(1,2.295),(2,4.341)]:
 base='signal_%02d'%idx; kw={'source':'S03 blue signal symbol; physical form illustrative','uncertainty':'Fixture shape, dimensions, facing and light state estimated (A09).'}
 box(base+'_base',(x,3.009,.015),(.32,.32,.03),'signal','04_Signals','blue',math.pi/4,**kw)
 cylinder(base+'_pole',(x,3.009,.34),.025,.65,'metal',**kw)
 box(base+'_housing',(x,3.009,.64),(.16,.12,.40),'signal','04_Signals','metal',**kw)
 for j,mat in enumerate(['red_lens','amber','green']):cylinder(base+'_lens_'+mat,(x,2.941,.75-j*.11),.042,.015,mat,rotation=(math.pi/2,0,0),**kw)

FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
font=bpy.data.fonts.load(FONT) if os.path.exists(FONT) else None
def text_obj(name,body,xy,size,mat='white',rotation=0,z=.008):
 cu=bpy.data.curves.new(name+'_curve','FONT');cu.body=body;cu.align_x='CENTER';cu.align_y='CENTER';cu.size=size;cu.extrude=.0002;cu.space_character=1.05
 if font:cu.font=font
 ob=bpy.data.objects.new(name,cu);bpy.context.collection.objects.link(ob);ob.location=(xy[0],xy[1],z);ob.rotation_euler.z=rotation
 register(ob,'label','06_Labels',mat,source='S03 zone/feature annotations',uncertainty='Font, exact placement and size adjusted for legibility (A14).')
 # Convert for GLB portability; Korean font is no longer required to view exported model.
 bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH');ob.select_set(False)
 return ob
bpy.ops.object.select_all(action='DESELECT')
text_obj('label_in','IN  입구',(7.,5.50),.38)
text_obj('label_out','OUT  출구',(7.,.50),.36)
text_obj('label_parking','P  주차',(7.5,3.),.32,'red')
text_obj('label_slalom','라바콘 슬라럼',(.50,3.),.20,rotation=math.pi/2)
for sign,label in [(-1,'sw'),(1,'ne')]:
 ob=text_obj('label_ramp_'+label,'경사로',p(sign*1.20,0),.25,rotation=math.pi/4,z=(1.6-1.2)/1.1*.18+.004)
 ob.rotation_euler.y=sign*math.atan2(.18,1.1)

# Consistent mesh normals, including independent floor pieces and glyphs.
for ob in list(bpy.data.objects):
 if ob.type=='MESH':
  bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free()

# Camera and lighting are presentation-only, excluded from GLB.
def move_to_presentation(ob):
 for c in list(ob.users_collection):c.objects.unlink(ob)
 collections['90_Presentation'].objects.link(ob)

def camera(name,loc,target,ortho):
 bpy.ops.object.camera_add(location=loc);ob=bpy.context.object;ob.name=name;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler();ob.data.type='ORTHO';ob.data.ortho_scale=ortho;ob.data.lens=45;move_to_presentation(ob);return ob
cam_iso=camera('camera_isometric',(10.,-13.,14.),(4.,3.,.0),11.3)
cam_top=camera('camera_top',(4.,3.009,16.),(4.,3.009,0),9.2);cam_top.rotation_euler=(0,0,0)
for name,loc,power,size in [('light_key',(2,-1,11),800,8),('light_fill',(10,6,9),500,7)]:
 bpy.ops.object.light_add(type='AREA',location=loc);ob=bpy.context.object;ob.name=name;ob.data.energy=power;ob.data.shape='DISK';ob.data.size=size;ob.rotation_euler=(Vector((4,3,0))-ob.location).to_track_quat('-Z','Y').to_euler();move_to_presentation(ob)
scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.80,.83,.86,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.65
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=96;scene.cycles.use_denoising=False
scene.render.resolution_x=1500;scene.render.resolution_y=1125;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=True
scene.use_nodes=True
nt=scene.node_tree;nt.nodes.clear();rl=nt.nodes.new('CompositorNodeRLayers');ao=nt.nodes.new('CompositorNodeAlphaOver');ao.inputs[0].default_value=1;ao.inputs[1].default_value=(.94,.955,.97,1);co=nt.nodes.new('CompositorNodeComposite');nt.links.new(rl.outputs['Image'],ao.inputs[2]);nt.links.new(ao.outputs['Image'],co.inputs['Image'])
scene.view_settings.view_transform='Standard';scene.render.image_settings.color_mode='RGB'
scene.camera=cam_iso
# Friendly first-open Blender view, centered on the complete model.
for screen in bpy.data.screens:
 for ar in screen.areas:
  if ar.type=='VIEW_3D':
   ar.spaces.active.region_3d.view_distance=11.5;ar.spaces.active.region_3d.view_location=(4,3,.05);ar.spaces.active.clip_end=200
   ar.spaces.active.shading.type='MATERIAL'

# Structured source-coordinate record for every model object, excluding cameras/lights.
bpy.context.view_layer.update()
for name,item in OBJECT_META.items():
 ob=bpy.data.objects.get(name)
 if not ob:continue
 bounds=[ob.matrix_world@v.co for v in ob.data.vertices] if ob.type=='MESH' else [ob.matrix_world@Vector(v) for v in ob.bound_box]
 item.update({'location_m':[round(v,6) for v in ob.location],'local_dimensions_m':[round(v,6) for v in ob.dimensions],'dimensions_m':[round(max(v[k] for v in bounds)-min(v[k] for v in bounds),6) for k in range(3)],'rotation_euler_rad':[round(v,8) for v in ob.rotation_euler],'bbox_m':{'min':[round(min(v[k] for v in bounds),6) for k in range(3)],'max':[round(max(v[k] for v in bounds),6) for k in range(3)]},'mesh_vertices':len(ob.data.vertices) if ob.type=='MESH' else None})
 META['objects'].append(item)
META['validation']['object_count']=len(META['objects'])
META['validation']['mesh_object_ids_unique']=len(META['objects'])==len(set(o['id'] for o in META['objects']))
META['validation']['model_xy_bounds_m']={'min':[min(o['bbox_m']['min'][k] for o in META['objects']) for k in [0,1]],'max':[max(o['bbox_m']['max'][k] for o in META['objects']) for k in [0,1]]}
META['files']={'blend':'arena.blend','gltf':'arena.glb','metadata':'arena.json','generator':'build_arena.py','assumptions':'ASSUMPTIONS.md','assumptions_csv':'ASSUMPTIONS.csv','render_isometric':'isometric.png','render_top':'top.png'}
write_meta()
with (OUT/'ASSUMPTIONS.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=['id','item','value','status','source','confirmation_needed']);writer.writeheader();writer.writerows(ASSUMPTIONS)
md=['# 적용 치수 및 추정 항목 보고서','', '이 모델은 첨부 래스터 도면의 시각화 재구성입니다. 실측 또는 원본 CAD로 검증된 설계/주행 지도가 아닙니다.','', '## 도면에 직접 명시되거나 계산으로 유도한 치수','', '| 항목 | 적용값 (m) | 구분 | 근거 | 주의사항 |','|---|---:|---|---|---|']
for d in DIMS:md.append(f"| {d['label']} | {d['value_m']} | {d['status']} | {d['source']} | {d['uncertainty']} |")
md+=['','## 추정·해석 항목','']
for a in ASSUMPTIONS:md += [f"### {a['id']} · {a['item']}",f"- 적용값: {a['value']}",f"- 구분: {a['status']}",f"- 근거: {a['source']}",f"- 확인 필요: {a['confirmation_needed']}",'']
(OUT/'ASSUMPTIONS.md').write_text('\n'.join(md),encoding='utf-8')

# Keep only model geometry selected and export names/custom-property extras.
bpy.ops.object.select_all(action='DESELECT')
for ob in bpy.data.objects:
 if ob.name in OBJECT_META:ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'arena.glb'),export_format='GLB',use_selection=True,export_yup=True,export_extras=True,export_cameras=False,export_lights=False,export_apply=True,export_materials='EXPORT')
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'arena.blend'))
print('ARENA_EXPORT_READY',str(OUT/'arena.glb'),flush=True)
if not args.skip_renders:
 scene.camera=cam_iso;scene.render.filepath=str(OUT/'isometric.png');bpy.ops.render.render(write_still=True)
 scene.camera=cam_top;scene.render.resolution_x=1600;scene.render.resolution_y=1280;scene.render.filepath=str(OUT/'top.png');bpy.ops.render.render(write_still=True)
 scene.camera=cam_iso;scene.render.resolution_x=1500;scene.render.resolution_y=1125
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'arena.blend'))
print('ARENA_COMPLETE',len(META['objects']),'objects',flush=True)
