"""Deterministic generated geometry only; never commits sensor recordings."""
import copy
import numpy as np


def metadata(stamp=1_000_000_000, sequence=1, epoch='synthetic-1'):
    return {'frame_key':{'source_epoch':epoch,'frame_id':'odom'},'stamp_ns':str(stamp),
            'source_epoch':epoch,'sequence':sequence,'clock_domain':'fixture-clock',
            'host_clock_id':'fixture-host','received_monotonic_ns':stamp,
            'evidence_kind':'SYNTHETIC','map_binding':{'map_id':'a'*24,'revision':'b'*64,'generation':0},
            'field_layout':['x:float32','y:float32','z:float32']}


def scene(cones=1, slope=.15, wall=True, body=True):
    x,y=np.meshgrid(np.arange(-.6,3.5,.1),np.arange(-1.2,1.2,.1))
    ground=np.column_stack((x.ravel(),y.ravel(),slope*x.ravel()))
    parts=[ground]; oracle=[]
    for i in range(cones):
        center=np.array([1.+i*.8,0.,slope*(1.+i*.8)])
        # Include low 8 cm cone, with sample spacing below the voxel linkage.
        height=.08 if i else .28
        rows=[]
        for z in np.linspace(.04,height,8):
            for t in np.linspace(0,2*np.pi,24,endpoint=False):
                radius=.11*(1-z/(height+.05)); rows.append(center+[radius*np.cos(t),radius*np.sin(t),z])
        points=np.asarray(rows); parts.append(points)
        oracle.append({'min':points.min(axis=0).tolist(),'max':points.max(axis=0).tolist()})
    if wall:
        y,z=np.meshgrid(np.arange(-.7,.7,.04),np.arange(.5,1.5,.04))
        parts.append(np.column_stack((np.full(y.size,2.8),y.ravel(),z.ravel())))
    if body: parts.append(np.array([[0,0,.3],[.02,0,.3],[0,.02,.3]]))
    n=np.array([-slope,0.,1.]); n/=np.linalg.norm(n)
    return np.vstack(parts),{'normal':n.tolist(),'d':0.,'uncertainty_m':.002,'gravity_up':[0,0,1]},oracle


def rgbd_fixture(meta):
    k={'fx':60.,'fy':60.,'ppx':20.,'ppy':20.,'width':40,'height':40,'model':'none','coeffs':[0]*5}
    c={'id':'synthetic-calibration','verified':True,'clock_correspondence_verified':True,'meta':copy.deepcopy(meta),
       'depth_intrinsics':k.copy(),'color_intrinsics':k.copy(),'depth_scale_m':.001,'uncertainty_m':.01,
       'T_color_depth':np.eye(4).tolist(),'T_local_depth':np.eye(4).tolist()}
    depth=np.full((40,40),3000.); depth[12:28,12:28]=1000.
    d={'class_id':0,'class_name':'cone','score':.9,'bbox_xyxy':[12,12,28,28],'native_shape':[40,40]}
    model={'sha256':'c'*64,'preprocess':'native_xyxy_no_resize','class_names':{'0':'cone'},'evidence_kind':'SYNTHETIC'}
    return [d],depth,c,model
