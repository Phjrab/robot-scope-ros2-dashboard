"""VM-only signal perception and intent core. No camera or command transport."""
from dataclasses import dataclass, asdict
import hashlib
import json
import math
import cv2
import numpy as np

@dataclass(frozen=True)
class ColorProfile:
    min_pixels: int = 12
    min_side: int = 6
    min_chroma: int = 55
    min_value: int = 45
    min_blur_variance: float = 2.0
    max_white_fraction: float = .85
    green_low: int = 35
    green_high: int = 90
    red_wrap_low: int = 10
    red_wrap_high: int = 170

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

def inverse_letterbox(box, native_size, model_size):
    """xyxy floating model coordinates -> conservative integer native crop.
    Uses exact rounded resize and asymmetric padding, matching letterbox()."""
    w,h = native_size; mw,mh = model_size
    if min(w,h,mw,mh)<=0 or len(box)!=4 or not all(math.isfinite(float(v)) for v in box):
        raise ValueError('invalid geometry')
    r=min(mw/w,mh/h); rw,rh=round(w*r),round(h*r)
    left=(mw-rw)//2; top=(mh-rh)//2
    x1,y1,x2,y2=box
    if x2<=x1 or y2<=y1: raise ValueError('empty box')
    crop=(max(0,math.floor((x1-left)*w/rw)),max(0,math.floor((y1-top)*h/rh)),
          min(w,math.ceil((x2-left)*w/rw)),min(h,math.ceil((y2-top)*h/rh)))
    if crop[2]<=crop[0] or crop[3]<=crop[1]: raise ValueError('outside image')
    return crop

def letterbox(bgr, size=(640,640)):
    h,w=bgr.shape[:2]; mw,mh=size; r=min(mw/w,mh/h)
    rw,rh=round(w*r),round(h*r)
    out=np.full((mh,mw,3),114,np.uint8); left=(mw-rw)//2; top=(mh-rh)//2
    out[top:top+rh,left:left+rw]=cv2.resize(bgr,(rw,rh))
    return out

def _state(bgr, profile, contrast=False):
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    h,s,v=cv2.split(hsv)
    valid=(s>=profile.min_chroma)&(v>=profile.min_value)
    # Discard fully achromatic clipped pixels, not saturated colored emitters.
    valid &= ~np.all(bgr>=250,axis=2)
    red=valid&((h<=profile.red_wrap_low)|(h>=profile.red_wrap_high))
    green=valid&(h>=profile.green_low)&(h<=profile.green_high)
    if contrast:
        b,g,r=bgr.astype(np.float32).transpose(2,0,1)
        red &= (2*r-g-b)>35
        green &= (2*g-r-b)>35
    def largest(mask):
        n,_,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
        return int(max(stats[1:,cv2.CC_STAT_AREA],default=0))
    nr,ng=largest(red),largest(green)
    if nr>=profile.min_pixels and ng>=profile.min_pixels: state='AMBIGUOUS'
    elif nr>=profile.min_pixels: state='RED'
    elif ng>=profile.min_pixels: state='GREEN'
    else: state='UNKNOWN'
    return state, nr, ng, valid, red, green

def classify_roi(bgr, box=None, *, encoding='bgr8', exposure_settling=False,
                 association_verified=True, profile=ColorProfile(), variant='combined'):
    flags=[]; metrics={}; mask=None
    if encoding not in ('bgr8','rgb8') or bgr is None or bgr.dtype!=np.uint8 or bgr.ndim!=3 or bgr.shape[2]!=3:
        return dict(raw_state='UNKNOWN',quality_flags=['ENCODING_MISMATCH'],metrics={},score=0.,mask=None)
    image=cv2.cvtColor(bgr,cv2.COLOR_RGB2BGR) if encoding=='rgb8' else bgr
    h,w=image.shape[:2]
    if box is None: box=(0,0,w,h)
    if len(box)!=4 or not all(math.isfinite(float(x)) for x in box):
        return dict(raw_state='UNKNOWN',quality_flags=['ROI_INVALID'],metrics={},score=0.,mask=None)
    x1,y1,x2,y2=map(int,box)
    if x1<0 or y1<0 or x2>w or y2>h: flags.append('ROI_TRUNCATED')
    roi=image[max(0,y1):min(h,y2),max(0,x1):min(w,x2)]
    if x2<=x1 or y2<=y1 or roi.size==0 or min(roi.shape[:2])<profile.min_side:
        return dict(raw_state='UNKNOWN',quality_flags=flags+['TOO_SMALL'],metrics={},score=0.,mask=None)
    if exposure_settling: flags.append('EXPOSURE_SETTLING')
    if not association_verified: flags.append('ASSOCIATION_UNCERTAIN')
    metrics['channel_clip_fraction']=[float(np.mean(roi[:,:,i]>=250)) for i in range(3)]
    metrics['white_clip_fraction']=float(np.mean(np.all(roi>=250,axis=2)))
    metrics['blur_variance']=float(cv2.Laplacian(cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
    raw,nr,ng,valid,red,green=_state(roi,profile,contrast=variant=='combined')
    metrics.update(chroma_pixels=int(valid.sum()),red_component=nr,green_component=ng)
    if metrics['white_clip_fraction']>=profile.max_white_fraction: flags.append('CLIPPED')
    if metrics['chroma_pixels']<profile.min_pixels: flags.append('LOW_CHROMA')
    if metrics['blur_variance']<profile.min_blur_variance: flags.append('BLURRED')
    enhanced=raw
    if variant in ('luminance','combined'):
        lab=cv2.cvtColor(roi,cv2.COLOR_BGR2LAB)
        lab[:,:,0]=cv2.createCLAHE(clipLimit=1.5,tileGridSize=(2,2)).apply(lab[:,:,0])
        enhanced,*_= _state(cv2.cvtColor(lab,cv2.COLOR_LAB2BGR),profile,contrast=variant=='combined')
        if raw in ('RED','GREEN') and enhanced in ('RED','GREEN') and raw!=enhanced:
            raw='AMBIGUOUS'; flags.append('BRANCH_CONFLICT')
    metrics['enhanced_state']=enhanced
    mask=np.zeros((*roi.shape[:2],3),np.uint8);mask[red]=(0,0,255);mask[green]=(0,255,0)
    if flags: raw='UNKNOWN' if raw!='AMBIGUOUS' else raw
    score=max(nr,ng)/max(1,int(valid.sum())) if raw in ('RED','GREEN') else 0.
    return dict(raw_state=raw,quality_flags=flags,metrics=metrics,score=float(score),mask=mask)

class TemporalFilter:
    """Receiver-local time + synchronized explicit source age; never subtract host clocks."""
    def __init__(self, stability_s=.4, ttl_s=.25):
        if not all(math.isfinite(v) and v>0 for v in (stability_s,ttl_s)): raise ValueError('positive finite times required')
        self.stability_s=stability_s; self.ttl_s=ttl_s; self.retired_epochs=set(); self.reset()
    def reset(self):
        self.identity=None; self.seq=-1; self.source_ns=-1; self.last=None;self.since=None;self.candidate=None
    def update(self, state, *, identity, sequence, source_stamp_ns, receipt_s, source_age_s, flags=()):
        now=float(receipt_s)
        age=float(source_age_s)
        if not math.isfinite(now) or not math.isfinite(age) or age<0 or age>self.ttl_s:
            self.reset(); return 'UNKNOWN'
        stamp=int(source_stamp_ns)
        epoch=identity[0]
        if epoch in self.retired_epochs:
            self.since=None;self.candidate=None;return 'UNKNOWN'
        if identity!=self.identity:
            if self.identity is not None and self.identity[0]!=epoch:self.retired_epochs.add(self.identity[0])
            self.reset();self.identity=identity
        invalid=(sequence<=self.seq or stamp<=self.source_ns or (self.last is not None and now<=self.last))
        gap=self.last is not None and now-self.last>self.ttl_s
        if invalid:
            self.since=None;self.candidate=None;return 'UNKNOWN'
        self.seq=sequence;self.source_ns=stamp;self.last=now
        if flags or state not in ('RED','GREEN'):
            self.since=None;self.candidate=None;return state if state=='AMBIGUOUS' else 'UNKNOWN'
        if gap or state!=self.candidate:
            self.since=now;self.candidate=state
        return state if now-self.since>=self.stability_s-1e-9 else 'UNKNOWN'
    def current(self, now):
        if self.last is None or not math.isfinite(now) or now<self.last or now-self.last>self.ttl_s:
            self.since=None;self.candidate=None;return 'UNKNOWN'
        return self.candidate if self.since is not None and self.last-self.since>=self.stability_s-1e-9 else 'UNKNOWN'

@dataclass(frozen=True)
class StopInput:
    receipt_s: float
    sequence: int
    run_id: str='vm-run'
    step_id: str='signal-step'
    crossing_id: str='crossing-1'
    visit_id: str='visit-1'
    signal_id: str='signal_01'
    zone_id: str='stop_zone_01'
    epoch: str='epoch-1'
    stable_state: str='UNKNOWN'
    signal_age_s: float=0.
    observation_age_s: float=0.
    feet_kind: str='SIM_GT'
    left_inside: bool=False
    right_inside: bool=False
    visual_zone: bool=False
    body_stopped: bool=False
    path_clear: bool=True
    localization_ready: bool=True
    safety_stop: bool=False
    approach_ack: bool=False
    departure_observed: bool=False
    fully_crossed: bool=False
    cancel: bool=False
    generation: int=0

class StopGoFSM:
    """Explicit start required; result is constraint intent, never a velocity command."""
    def __init__(self, *, simulation=True, ttl_s=.25, minimum_stop_s=2.):
        if not math.isfinite(ttl_s) or ttl_s<=0: raise ValueError('positive finite TTL required')
        if minimum_stop_s<2 or not math.isfinite(minimum_stop_s): raise ValueError('RULEBOOK minimum is 2s')
        self.simulation=simulation;self.ttl=ttl_s;self.dwell=minimum_stop_s
        self.begun_keys=set()
        self.state='INTERRUPTED';self.key=None;self.last=None;self.seq=-1;self.start=None;self.epoch=None
    def begin(self, run_id, step_id, crossing_id, visit_id, signal_id, generation=0, zone_id='stop_zone_01'):
        key=(run_id,step_id,crossing_id,visit_id,signal_id,generation,zone_id)
        if key in self.begun_keys:return False
        self.begun_keys.add(key);self.key=key
        self.state='APPROACH';self.last=None;self.seq=-1;self.start=None;self.epoch=None;self.retired_epochs=set()
        return True
    def update(self, i:StopInput):
        key=(i.run_id,i.step_id,i.crossing_id,i.visit_id,i.signal_id,i.generation,i.zone_id)
        def output(reason, release=False):
            return {'state':self.state,'reason':reason,'depart_intent':release and self.state=='DEPART_PENDING',
                'motion_constraint':{'owner_id':'traffic_vm','run_id':self.key[0] if self.key else i.run_id,'step_id':self.key[1] if self.key else i.step_id,
                'request_id':f'{self.key[3] if self.key else i.visit_id}:{i.sequence}','generation':self.key[5] if self.key else i.generation,'reason':reason,
                'mode':'RELEASE' if release else 'HOLD','max_vx':None if release else 0.,
                'max_vy':None if release else 0.,'max_wz':None if release else 0.,
                'validity':{'receipt_ttl_s':self.ttl},'priority':60},
                'evidence_type':'SYNTHETIC' if self.simulation else 'ADAPTER_INPUT',
                'continuous_valid_stop_s':0. if self.start is None else max(0.,i.receipt_s-self.start)}
        bool_fields=('left_inside','right_inside','visual_zone','body_stopped','path_clear','localization_ready','safety_stop','approach_ack','departure_observed','fully_crossed','cancel')
        if any(type(getattr(i,f)) is not bool for f in bool_fields) or type(i.sequence) is not int or type(i.generation) is not int or any(type(v) not in (int,float) for v in (i.receipt_s,i.signal_age_s,i.observation_age_s)):
            self.state='INTERRUPTED';self.start=None;return output('INVALID_INPUT_TYPES')
        if self.key is None or key!=self.key:
            self.start=None
            if self.state not in ('CROSSING_COMMITTED','CLEAR','CANCELLED','INTERRUPTED'):self.state='STOP_ZONE_ALIGN'
            return output('IDENTITY_MISMATCH')
        if i.cancel:
            self.state='CANCELLED';self.start=None;return output('CANCELLED')
        if self.state in ('CANCELLED','INTERRUPTED'): return output(self.state)
        finite=all(math.isfinite(v) for v in (i.receipt_s,i.signal_age_s,i.observation_age_s))
        fresh=finite and 0<=i.observation_age_s<=self.ttl
        if i.epoch in self.retired_epochs:
            self.start=None
            if self.state not in ('CROSSING_COMMITTED','CLEAR'):self.state='STOP_ZONE_ALIGN'
            return output('RETIRED_EPOCH')
        epoch_change=self.epoch is not None and self.epoch!=i.epoch
        if epoch_change:
            self.retired_epochs.add(self.epoch);self.seq=-1;self.last=None;self.start=None
            if self.state not in ('CROSSING_COMMITTED','CLEAR'):self.state='STOP_ZONE_ALIGN'
        duplicate=i.sequence<=self.seq or (self.last is not None and i.receipt_s<=self.last)
        gap=self.last is not None and i.receipt_s-self.last>self.ttl
        epoch_change=self.epoch is not None and self.epoch!=i.epoch
        if not fresh or duplicate:
            if self.state not in ('CROSSING_COMMITTED','CLEAR'):self.state='STOP_ZONE_ALIGN';self.start=None
            return output('STALE_OR_REPEATED_INPUT')
        self.last=i.receipt_s;self.seq=i.sequence;self.epoch=i.epoch
        if gap or epoch_change:
            self.start=None
            if self.state not in ('CROSSING_COMMITTED','CLEAR'):self.state='STOP_ZONE_ALIGN'
        if i.safety_stop or not i.path_clear or not i.localization_ready:
            if self.state not in ('CROSSING_COMMITTED','CLEAR'):self.state='STOP_ZONE_ALIGN';self.start=None
            return output('SAFETY_OR_OBSTACLE_OR_LOCALIZATION_HOLD')
        if self.state=='CLEAR':return output('CLEARED',True)
        if self.state=='CROSSING_COMMITTED':
            if i.fully_crossed:self.state='CLEAR'
            return output('COMMITTED_PASS',True)
        green=i.stable_state=='GREEN' and 0<=i.signal_age_s<=self.ttl
        if i.departure_observed and i.body_stopped:
            self.start=None;self.state='STOP_ZONE_ALIGN'
            return output('CONTRADICTORY_DEPARTURE_EVIDENCE')
        # Pending is revoked before evaluating a same-frame movement acknowledgement.
        if self.state=='DEPART_PENDING' and green and i.departure_observed:
            self.state='CROSSING_COMMITTED';return output('DEPARTURE_CONFIRMED',True)
        eligible_kind=i.feet_kind in ('KINEMATIC','VISUAL') or (self.simulation and i.feet_kind=='SIM_GT')
        stopped=i.left_inside and i.right_inside and i.visual_zone and i.body_stopped and eligible_kind
        if not i.approach_ack:
            self.state='APPROACH';self.start=None;return output('WAIT_APPROACH_CANCEL_OR_COMPLETE_ACK')
        if not stopped:
            self.state='STOP_ZONE_ALIGN';self.start=None;return output('FEET_OR_STOP_UNPROVEN')
        if self.start is None:self.start=i.receipt_s
        if i.receipt_s-self.start<self.dwell-1e-9:
            self.state='HOLD_2S';return output('MINIMUM_DWELL')
        self.state='DEPART_PENDING' if green else 'WAIT_GREEN'
        return output('FRESH_GREEN_NEW_LEG_REQUIRED' if green else 'WAIT_FRESH_GREEN',green)
