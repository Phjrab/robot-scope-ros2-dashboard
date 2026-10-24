"""Replay explicit image/detection/stop-evidence JSONL or deterministic synthetic fixture."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw
from core import ColorProfile, TemporalFilter, StopGoFSM, StopInput, classify_roi

def fixture():
    # Labels are defined by generator, not derived from HSV outputs.
    records=[]
    for n in range(100):
        t=n/10
        truth='RED' if t<3 else ('UNKNOWN' if t<4 else 'GREEN')
        bgr=np.full((120,160,3),30,np.uint8)
        cv2.rectangle(bgr,(55,12),(105,106),(12,12,12),-1)
        color={'RED':(0,0,230),'GREEN':(0,230,0),'UNKNOWN':(255,255,255)}[truth]
        cv2.circle(bgr,(80,60),16,color,-1)
        records.append(dict(t=t,sequence=n,image=bgr,truth=truth,roi=(55,12,106,107),
                            feet_inside=True,stopped=t<4.8,departure=t>=4.8,fully_crossed=t>=7))
    return records

def load_manifest(path):
    rows=[]
    root=path.parent.resolve()
    for line in path.read_text().splitlines():
        v=json.loads(line);image_path=(root/v['image']).resolve()
        if root not in image_path.parents:raise ValueError('image outside manifest directory')
        image=cv2.imread(str(image_path))
        if image is None:raise ValueError('unreadable RGB image')
        # This is a recorded-detection adapter, not inference or generated ground truth.
        rows.append(dict(t=v['receipt_s'],sequence=v['sequence'],image=image,truth=v['label'],
            roi=v.get('roi_xyxy_native'),feet_inside=v.get('feet_inside',False),
            stopped=v.get('body_stopped',False),departure=v.get('departure_observed',False),
            fully_crossed=v.get('fully_crossed',False),association=v.get('association_verified',False),
            age=v.get('source_age_s',1.),epoch=v.get('producer_epoch','recorded'),
            track=v.get('track_id','missing'),stamp=v.get('source_stamp_ns'),
            detector_available=v.get('detector_available',False)))
    return rows

def run(rows,out,synthetic):
    if not rows:raise ValueError('empty replay manifest')
    out.mkdir(parents=True,exist_ok=True)
    f=TemporalFilter();fsm=StopGoFSM(simulation=synthetic)
    fsm.begin('vm-run','signal-step','crossing-1','visit-1','signal_01')
    frames=[];records=[];timings=[]
    matrix={v:{t:{p:0 for p in ('RED','GREEN','UNKNOWN','AMBIGUOUS')} for t in ('RED','GREEN','UNKNOWN')} for v in ('raw','luminance','combined')}
    firstgreen=None;firststable=None;firstdepart=None;falsego=0
    for row in rows:
        t=float(row['t']);start=time.perf_counter()
        detected=row.get('detector_available',synthetic)
        assoc=row.get('association',synthetic)
        results={v:classify_roi(row['image'],row['roi'],association_verified=assoc and detected,variant=v) for v in matrix}
        for v,result in results.items():matrix[v][row['truth']][result['raw_state']]+=1
        result=results['combined'];flags=list(result['quality_flags'])
        if not detected:flags.append('DETECTOR_MISSING')
        if row['truth']=='GREEN' and firstgreen is None:firstgreen=t
        stamp=row.get('stamp') or str(round(t*1e9));epoch=row.get('epoch','fixture-1');track=row.get('track','fixture-housing')
        stable=f.update(result['raw_state'],identity=(epoch,track,'crossing-1','visit-1'),
            sequence=row['sequence'],source_stamp_ns=stamp,receipt_s=t,source_age_s=row.get('age',0.),flags=flags)
        if stable=='GREEN' and firststable is None:firststable=t
        i=StopInput(t,row['sequence'],stable_state=stable,signal_age_s=row.get('age',0.),
            epoch=epoch,left_inside=row['feet_inside'],right_inside=row['feet_inside'],
            feet_kind='SIM_GT' if synthetic else 'PROXY',visual_zone=row['feet_inside'],
            body_stopped=row['stopped'],approach_ack=True,departure_observed=row['departure'],fully_crossed=row['fully_crossed'])
        action=fsm.update(i)
        if action['depart_intent'] and firstdepart is None:firstdepart=t
        if action['depart_intent'] and row['truth']!='GREEN':falsego+=1
        timings.append((time.perf_counter()-start)*1000)
        obs={'schema_version':'0.1','producer_id':'traffic_vm_replay','producer_epoch':epoch,
             'sequence':row['sequence'],'source_stamp_ns':str(stamp),'source_clock':'fixture_sim' if synthetic else 'declared_source',
             'frame_id':'camera_rgb_optical','evidence_type':'SYNTHETIC' if synthetic else 'RECORDED_IMAGE_WITH_DETECTION_METADATA',
             'config_hash':ColorProfile().sha256,'signal_id':'signal_01','track_id':track,'crossing_id':'crossing-1',
             'mission_run_id':'vm-run','step_id':'signal-step','raw_state':result['raw_state'],'stable_state':stable,
             'confidence':{'kind':'UNCALIBRATED_COLOR_SCORE','value':result['score'],'detector':None},
             'roi_xyxy_native':row['roi'],'native_image_size':[row['image'].shape[1],row['image'].shape[0]],
             'quality_flags':flags,'exposure_metadata':None,'evidence_age':row.get('age',0.),'model_sha256':None,
             'preprocess_profile':'combined_design_initial','metrics':result['metrics']}
        records.append({'observation':obs,'action':action,'stop_input':asdict(i)})
        im=Image.new('RGB',(640,360),(24,27,35));im.paste(Image.fromarray(cv2.cvtColor(row['image'],cv2.COLOR_BGR2RGB)).resize((320,240)),(10,45))
        if result['mask'] is not None:
            im.paste(Image.fromarray(cv2.cvtColor(result['mask'],cv2.COLOR_BGR2RGB)).resize((100,180)),(340,85))
        d=ImageDraw.Draw(im);d.text((12,12),'SYNTHETIC VM REPLAY - NOT YOLO / NOT ROBOT' if synthetic else 'RECORDED IMAGE REPLAY - DETECTION METADATA',fill='orange')
        for idx,line in enumerate([f't={t:.1f}s label={row["truth"]}',f'raw={result["raw_state"]}',f'stable={stable}',action['state'],action['reason'],f'dwell={action["continuous_valid_stop_s"]:.1f}s',f'constraint={action["motion_constraint"]["mode"]}']):d.text((12,290+idx*9) if idx>=4 else (450,90+idx*35),line,fill='white')
        frames.append(im)
    frames[0].save(out/'replay.gif',save_all=True,append_images=frames[1:],duration=100,loop=0)
    contact=Image.new('RGB',(1280,720))
    for pos,index in enumerate([min(len(frames)-1,x) for x in [0,25,35,48]]):contact.paste(frames[index],((pos%2)*640,(pos//2)*360))
    contact.save(out/'contact_sheet.png')
    (out/'replay.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in records)+'\n')
    p95=float(np.percentile(timings,95))
    metrics={'evidence_type':'SYNTHETIC' if synthetic else 'RECORDED_METADATA','frames':len(rows),'confusion_by_variant':matrix,
             'false_depart_intent_events':falsego,'first_green_s':firstgreen,'first_stable_green_s':firststable,
             'first_depart_intent_s':firstdepart,'green_transition_delay_s':None if firststable is None or firstgreen is None else firststable-firstgreen,
             'p95_core_processing_ms':p95,'mean_core_processing_ms':statistics.mean(timings),
             'yolo_detection_recall':None,'model_sha256':None,'real_RGB_validated':False,'Jetson_performance':None,
             'runtime':{'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__,'platform':platform.platform()},
             'limits':['No actual owner weights or RGB clips provided','Timing excludes detector, IO and render','No physical safety guarantee; finite fixture only','Design thresholds not calibrated on field data']}
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    return metrics

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path);p.add_argument('--synthetic',action='store_true');p.add_argument('--output',type=Path,default=Path('results'))
    a=p.parse_args()
    if bool(a.manifest)==a.synthetic:p.error('choose exactly --synthetic or --manifest')
    print(json.dumps(run(fixture() if a.synthetic else load_manifest(a.manifest),a.output,a.synthetic),indent=2))
