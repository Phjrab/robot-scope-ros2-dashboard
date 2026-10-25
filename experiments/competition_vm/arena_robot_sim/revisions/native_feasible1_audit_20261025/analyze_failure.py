"""One recorded native feasible1 failure, read-only offline geometry audit.

No native controller run or exact rejected-arc reconstruction is claimed. The
artifact omits local costmap, rejected twist, controller pose and Path orientation.
"""
from pathlib import Path
import argparse, base64, csv, hashlib, importlib.util, io, json, math, os, re, zipfile, zlib
import numpy as np
HERE=Path(__file__).resolve().parent
SHARED=HERE.parent/'shared_scenarios_20261025'
ARTIFACT_SHA='c2d20937c7e2d7d2d20527994e8eaa116d2fab1d556638562ce688972317d8cb'
PREFIX='d0/rpp-d0_feasible1-0/run/'
SOURCE='5eacacf42378ad91319a5de323df7844f34ea33b'
HELPER=SHARED/'review/audit_saved_witnesses.py'
spec=importlib.util.spec_from_file_location('frozen_independent_geometry',HELPER)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def polygon(pose,footprint):
    p=np.asarray(pose);body=g.as_complex(footprint)
    return g.as_complex(p[:2])+np.exp(1j*p[2])*body

def geometry_clearances(poses,footprint,truth):
    poses=np.asarray(poses,float)
    robot=g.as_complex(poses[:,:2])[:,None]+np.exp(1j*poses[:,2,None])*g.as_complex(footprint)
    boundary=g.as_complex(truth['boundary_polygon'])
    valid=g.inside(robot,boundary).all(axis=1);distance=g.separation(robot,boundary)
    for points in [x['polygon'] for x in truth['obstacles']]+truth['forbidden_polygons']:
        p=g.as_complex(points)
        valid &= ~g.inside(robot,p).any(axis=1)
        valid &= ~g.inside(p[None,:],robot[:,None,:]).any(axis=1)
        distance=np.minimum(distance,g.separation(robot,p))
    return np.where(valid,distance,0.)

def propagate(pose,v,w,t):
    x,y,a=pose;t=np.asarray(t)
    if abs(w)<1e-12:return np.c_[x+v*t*np.cos(a),y+v*t*np.sin(a),np.full_like(t,a)]
    return np.c_[x+v/w*(np.sin(a+w*t)-np.sin(a)),y-v/w*(np.cos(a+w*t)-np.cos(a)),a+w*t]

def load_archive(path):
    raw=Path(path).read_bytes()
    if sha(raw)!=ARTIFACT_SHA:raise ValueError('Wrong native artifact SHA256; do not substitute another run')
    z=zipfile.ZipFile(io.BytesIO(raw))
    names=('fixture.json','params.yaml','trace.jsonl','raw_commands.jsonl','observations.jsonl','native.log','result.json','validation.json')
    blobs={n:z.read(PREFIX+n) for n in names}
    return blobs,{n:sha(b) for n,b in blobs.items()}

def decode_costmap(record):
    raw=zlib.decompress(base64.b64decode(record['data_zlib_base64']))
    if len(raw)!=record['height']*record['width']:raise ValueError('Costmap byte count mismatch')
    return np.frombuffer(raw,np.int8).reshape(record['height'],record['width'])

def classify(value):
    return 'unknown' if value==-1 else 'lethal' if value==100 else 'inscribed' if value==99 else 'free' if value==0 else 'inflation_cost'

def analyze(archive):
    import yaml
    blobs,hashes=load_archive(archive)
    fixture=json.loads(blobs['fixture.json']);params=yaml.safe_load(blobs['params.yaml'])
    truth=json.loads((SHARED/'fixtures/feasible1.truth.json').read_text())
    assert fixture['scenario']=='d0_feasible1' and fixture['d0_scene_sha256']==truth['scene_sha256']
    raw=fixture['footprint'];pad=fixture['effective_footprint']
    assert np.allclose(raw,[[-.405,-.28],[.405,-.28],[.405,.28],[-.405,.28]],atol=1e-15)
    assert np.allclose(pad,[[-.435,-.31],[.435,-.31],[.435,.31],[-.435,.31]],atol=1e-15)
    for key in ('global_costmap','local_costmap'):
        cp=params[key][key]['ros__parameters']
        assert cp['footprint_padding']==0. and cp['resolution']==.02
        assert np.allclose(json.loads(cp['footprint']),pad,atol=1e-15)
    rows=lambda n:[json.loads(line) for line in blobs[n].splitlines()]
    trace=rows('trace.jsonl');commands=rows('raw_commands.jsonl');observations=rows('observations.jsonl')
    lines=blobs['native.log'].decode().splitlines()
    index,line=next((i+1,l) for i,l in enumerate(lines) if 'RegulatedPurePursuitController detected collision ahead!' in l)
    event_wall=float(re.search(r'\[(\d+\.\d+)\]',line).group(1))
    zero=next(x for x in commands if x['source_timestamp_ns']/1e9>=event_wall and x['owner']=='controller_server' and x['v']==x['w']==0.)
    # Same-host wall/steady bridge from the recorded callback. This brackets a
    # captured simulation sample; it is not a recovered controller TF lookup.
    event_mono=zero['receipt_monotonic']+(event_wall-zero['source_timestamp_ns']/1e9)-zero['source_age_s']
    before=max((x for x in trace if x['monotonic']<=event_mono),key=lambda x:x['monotonic'])
    after=min((x for x in trace if x['monotonic']>event_mono),key=lambda x:x['monotonic'])
    previous=max((x for x in commands if x['source_timestamp_ns']/1e9<event_wall and x['owner']=='controller_server' and x['accepted']),key=lambda x:x['source_timestamp_ns'])
    path=max((x for x in observations if x['kind']=='path' and x['receipt_monotonic']<event_mono),key=lambda x:x['receipt_monotonic'])
    cm=max((x for x in observations if x['kind']=='costmap' and x['receipt_monotonic']<event_mono),key=lambda x:x['receipt_monotonic'])
    grid=decode_costmap(cm)
    spin=next(l for l in lines if 'Collision Ahead - Exiting Spin' in l)
    spin_wall=float(re.search(r'\[(\d+\.\d+)\]',spin).group(1))
    current=before['pose'];current_clear={label:float(geometry_clearances([current],body,truth)[0]) for label,body in [('raw_body',raw),('padded_body',pad)]}
    xy=np.asarray(path['points']);delta=np.diff(xy,axis=0)
    assert np.all(np.linalg.norm(delta,axis=1)>0)
    # Path orientation was discarded by the recorder. These yaw values are
    # explicitly derived diagnostics, NEVER presented as recorded native yaw.
    tangent=np.c_[xy[:-1],np.arctan2(delta[:,1],delta[:,0])]
    clear=geometry_clearances(tangent,raw,truth);bad=np.flatnonzero(clear<=1e-10)
    i=int(bad[0]);point=tangent[i]
    gx=int((point[0]-cm['origin'][0])/cm['resolution']);gy=int((point[1]-cm['origin'][1])/cm['resolution'])
    center_value=int(grid[gy,gx])
    chord=xy[i+1]-xy[i-1]
    chord_pose=[*xy[i],float(np.arctan2(chord[1],chord[0]))]
    sensitivity={'heading_definition':'central chord between preceding and following points','pose':chord_pose,'raw_clearance_m':float(geometry_clearances([chord_pose],raw,truth)[0]),'padded_clearance_m':float(geometry_clearances([chord_pose],pad,truth)[0])}
    times=np.linspace(0.,1.,1001);arc=propagate(current,previous['v'],previous['w'],times)
    arc_raw=geometry_clearances(arc,raw,truth);arc_pad=geometry_clearances(arc,pad,truth)
    hit=np.flatnonzero(arc_pad<=1e-10);hit_i=int(hit[0]) if len(hit) else None
    witness=json.loads((SHARED/'witnesses/feasible1.json').read_text());wp=np.asarray(witness['poses']);wd=np.diff(wp[:,:2],axis=0)
    lateral=np.abs(-np.sin(wp[:-1,2])*wd[:,0]+np.cos(wp[:-1,2])*wd[:,1])
    classes={name:int(np.sum(grid==value)) for name,value in [('free',0),('unknown',-1),('lethal',100),('inscribed',99)]}
    classes['inflation_cost']=int(np.sum((grid>0)&(grid<99)))
    out={'scope':'RECORDED_NATIVE_NAV2_WITH_VIRTUAL_SENSOR; ONE_FEASIBLE1_FAILURE_OFFLINE_AUDIT',
      'source_commit':SOURCE,'artifact_id':12588085458,'run_id':40164154349,'artifact_sha256':ARTIFACT_SHA,
      'input_hashes':hashes,'scene_sha256':truth['scene_sha256'],'frozen_geometry_helper_sha256':sha(HELPER.read_bytes()),
      'first_event':{'native_log_line':index,'text':line,'wall_epoch_s':event_wall,'estimated_monotonic_s':event_mono,
       'clock_method':'Zero command DDS source wall stamp + recorded source age / receipt monotonic; brackets saved ticks, not exact control TF input',
       'latest_before_trace':before,'first_after_trace':after,'first_zero_command':zero,'previous_accepted_command':previous,
       'later_spin_failure_wall_s':spin_wall,'spin_delay_after_first_s':spin_wall-event_wall},
      'native_input':{'raw_body_m':[.81,.56],'padded_body_m':[.87,.62],'clearance_applied_once_m':.03,'native_footprint_padding_m':0.,'grid_resolution_m':.02,
       'latest_path_source_sim_s':path['source_sim_s'],'latest_path_receipt_monotonic':path['receipt_monotonic'],'path_points':len(xy),'path_yaw_recorded':False,
       'costmap_scope':'GLOBAL OccupancyGrid ONLY; not exact LOCAL RPP costmap','latest_costmap_source_sim_s':cm['source_sim_s'],
       'costmap_age_in_recorded_sim_s':before['sim_t']-cm['source_sim_s'],'classes':classes,
       'cost_encoding':'Occupancy100 = raw254 lethal;99 = raw253 inscribed;1..98 lossy inflation; -1 = raw255 unknown. Inflation99 is NOT by itself RPP lethal threshold.'},
      'current_recorded_geometry':{'pose_kind':'latest saved pre-event SIM_GT pose, not logged RPP TF pose','pose':current,'minimum_clearance_m':current_clear,'current_physical_contact':False},
      'path_tangent_diagnostic':{'status':'GEOMETRIC_COUNTEREXAMPLE_UNDER_DERIVED_HEADING_NOT_RECORDED_NATIVE_YAW','heading_definition':'outgoing forward-segment tangent, not recorded yaw','central_chord_sensitivity':sensitivity,'first_intersecting_point_index':i,'pose_with_derived_yaw':point.tolist(),'raw_body_clearance_m':float(clear[i]),'global_center_cell_value':center_value,'global_center_cell_class':classify(center_value),'intersecting_samples':len(bad),'meaning':'A free centerline cell does not certify this full rectangular body oriented along path tangent; exact RPP rejected yaw/path transform remains missing.'},
      'previous_command_counterfactual':{'status':'NOT_THE_REJECTED_CANDIDATE','v':previous['v'],'w':previous['w'],'horizon_s':1.,'sample_dt_s':.001,
       'first_padded_contact_sample_s':float(times[hit_i]) if hit_i is not None else None,'minimum_raw_clearance_m':float(arc_raw.min()),'minimum_padded_clearance_m':float(arc_pad.min()),
       'meaning':'Independent constant-twist projection of last published accepted command only; not actual future execution or reconstructed RPP failure arc.'},
      'witness_comparison':{'scope':'Original holonomic feasibility only; not fed to native planner','sha256':sha((SHARED/'witnesses/feasible1.json').read_bytes()),'lateral_translation_m':float(lateral.sum()),'lateral_edges':int(np.sum(lateral>1e-10))},
      'hypotheses':{
       'current_physical_geometry_contact':'EXCLUDED_AT_SAVED_PRE_EVENT_POSE; raw clearance exceeds .03m',
       'native_footprint_padding_double_application':'EXCLUDED_BY_CAPTURED_YAML; .87x.62 with padding0 in both maps; inflation remains a distinct cost policy',
       'centerline_vs_full_body_heading':'NUMERICALLY_SUPPORTED_CANDIDATE; tangent-derived sample intersects despite free center cell, not exact rejected-yaw proof',
       'raster_conservatism':'UNRESOLVED; only older global map recorded, exact local cell/perimeter absent',
       'inflation_cost_alone':'NOT_SUFFICIENT_FOR_RPP_LETHAL_TEST; exact returned cell max unavailable',
       'exact_rejected_sweep_cause':'NOT_RUN_MISSING_SIGNALS'},
      'minimum_next_action':'C3 records one first-warning packet: controller input pose/TF stamp, local raw costmap+footprint, rejected v/w, first failed projected pose/raw cost, and transformed path/carrot; rerun feasible1 only with unchanged geometry/config.',
      'not_run':['Exact local checker replay','Nonholonomic search (not needed for bounded minimum diagnosis)','Native rerun or parameter modification','feasible2/tight5/full-course/gait/physical validation']}
    return out,dict(truth=truth,grid=grid,costmap=cm,path=xy,current=current,raw=raw,padded=pad,tangent_bad=point,arc=arc,arc_hit=hit_i)

def draw(out,ctx,target):
    os.environ.setdefault('MPLCONFIGDIR','/tmp/d0-round4-matplotlib')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.colors import ListedColormap
    fig,ax=plt.subplots(figsize=(10,10),dpi=145)
    cm=ctx['costmap'];grid=ctx['grid'];image=np.zeros_like(grid,dtype=np.uint8)
    image[(grid>0)&(grid<99)]=1;image[grid==99]=2;image[grid==100]=3;image[grid==-1]=4
    r=cm['resolution'];ox,oy=cm['origin']
    ax.imshow(image,origin='lower',extent=[ox,ox+r*cm['width'],oy,oy+r*cm['height']],cmap=ListedColormap(['#ffffff','#fff7cb','#ffdfa0','#eecccc','#aaaaaa']),vmin=0,vmax=4,alpha=.8)
    boundary=np.asarray(ctx['truth']['boundary_polygon']);ax.add_patch(Polygon(boundary,fill=False,color='black',linewidth=2,label='Original route boundary'))
    for o in ctx['truth']['obstacles']:ax.add_patch(Polygon(o['polygon'],facecolor='#ed771e',edgecolor='black',label='True 0.26 m square cone base'))
    xy=ctx['path'];ax.plot(xy[:,0],xy[:,1],color='#2766b0',lw=2,label='Recorded global path XY (yaw missing)')
    def box(p,fp,color,label,style='-'):
        q=polygon(p,fp);ax.plot(np.r_[q.real,q.real[0]],np.r_[q.imag,q.imag[0]],color=color,lw=2,ls=style,label=label)
    box(ctx['current'],ctx['raw'],'#15915a','Saved pose: raw body 0.81 x 0.56 m')
    box(ctx['current'],ctx['padded'],'#15915a','Saved pose: padded body 0.87 x 0.62 m','--')
    box(ctx['tangent_bad'],ctx['raw'],'#bd1726','Derived forward-tangent body: intersects cone')
    arc=ctx['arc'];ax.plot(arc[:,0],arc[:,1],color='#7a3caf',ls=':',lw=2,label='Last accepted twist, 1 s counterfactual')
    if ctx['arc_hit'] is not None:box(arc[ctx['arc_hit']],ctx['padded'],'#7a3caf','Counterfactual padded contact (not RPP arc)',':')
    p=ctx['current'];ax.scatter([p[0]],[p[1]],color='green',zorder=5);ax.annotate('Last pre-warning saved pose\nsim 6.40 s / elapsed 4.85 s',(p[0],p[1]),xytext=(.9,1.35),arrowprops={'arrowstyle':'->'},fontsize=9)
    ax.set_xlim(-.03,1.42);ax.set_ylim(1.15,3.25);ax.set_aspect('equal');ax.set_xlabel('arena_design / simulation map x [m]');ax.set_ylabel('y [m]')
    ax.set_title('D0 feasible1: first RPP collision-ahead warning\nGlobal map from sim 6.15 s, NOT the missing local checker input')
    ax.legend(loc='upper right',fontsize=7.5,framealpha=.95)
    fig.text(.08,.02,'Cells: white free; pale yellow inflation; amber inscribed 99; pale red lethal 100.\nExact rejected v/w, controller TF pose, local costmap and arc were not recorded. No native replay claimed.',fontsize=8)
    fig.subplots_adjust(bottom=.11,top=.91);fig.savefig(target);plt.close(fig)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifact-zip',required=True,type=Path);parser.add_argument('--output',type=Path,default=HERE/'results');args=parser.parse_args()
    out,ctx=analyze(args.artifact_zip);args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'judgment.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    draw(out,ctx,args.output/'first_failure_topdown.png')
    with (args.output/'selected_samples.csv').open('w') as f:
        writer=csv.writer(f,lineterminator="\n");writer.writerow(['evidence_kind','sim_t','x','y','yaw'])
        for k in ('latest_before_trace','first_after_trace'):
            x=out['first_event'][k];writer.writerow([k,x['sim_t'],*x['pose']])
        writer.writerow(['derived_path_tangent_not_native_yaw','',*ctx['tangent_bad']])
    print(json.dumps({'event_sim_bracket':[out['first_event'][k]['sim_t'] for k in ('latest_before_trace','first_after_trace')],'current_clearance':out['current_recorded_geometry']['minimum_clearance_m'],'tangent_counterexample':out['path_tangent_diagnostic'],'previous_command':out['previous_command_counterfactual']},indent=2))
