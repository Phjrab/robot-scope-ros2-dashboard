"""Small fixed baseline; VM timing is not Jetson latency. No parameter sweeps."""
import argparse
import json
import platform
import resource
import time
from pathlib import Path
import numpy as np
from robot_dashboard.obstacle_fusion_core import Tracker, process_lidar
from .scenarios import metadata, scene


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--fixture',type=Path)
    args=ap.parse_args(); durations=[]; results=[]; counts=[]
    for count in range(3):
        p,g,oracle=scene(count); m=metadata(); boxes=[{'min':[-.2,-.2,.2],'max':[.2,.2,.4],'meta':m}]
        for _ in range(5):
            begin=time.perf_counter(); o=process_lidar(p,m,ground=g,self_boxes=boxes); frame=Tracker().step(o); durations.append((time.perf_counter()-begin)*1000)
        assert len(o['obstacles'])==count+1
        results.append({'cones':count,'wall':True,'low_cone':count==2,'point_count':len(p),'object_count':len(o['obstacles']),'drops':o['dropped_counts'],'evidence_kind':'SYNTHETIC'})
        counts.append(len(p))
        if args.fixture and count==2: args.fixture.write_text(json.dumps({'points':p.tolist(),'meta':m,'ground':g,'self_boxes':boxes}))
    report={'platform':platform.platform(),'python':platform.python_version(),'evidence_kind':'SYNTHETIC','runs':15,'timing_ms':{'p50':float(np.percentile(durations,50)),'p95':float(np.percentile(durations,95))},'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'max_points':max(counts),'frame_budget_drop_rate':0.,'scenarios':results,'semantic_evaluation':'SEMANTIC_MODEL_INPUT_REQUIRED','real_calibration_evaluation':'INPUT_REQUIRED','real_replay':'INPUT_REQUIRED','device':'DEVICE_NOT_RUN'}
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,sort_keys=True))

if __name__=='__main__': main()
