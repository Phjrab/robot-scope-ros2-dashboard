"""Publish compact execution evidence, not bulky synthetic point/mesh streams."""
from pathlib import Path
import gzip,hashlib,json
HERE=Path(__file__).resolve().parent
NAMES=('open_normal','tight_normal','open_dropout','open_delay','blocked_5')
def digest(b):return hashlib.sha256(b).hexdigest()
if __name__=='__main__':
    result={}
    for name in NAMES:
        p=HERE/'results/candidate02'/f'{name}.json';raw=p.read_bytes();d=json.loads(raw)
        frames=[]
        for f in d['frames']:
            g={k:v for k,v in f.items() if k not in ('points','path','path_yaws')}
            g['planned_path_sha256']=digest(json.dumps([f['path'],f['path_yaws']],separators=(',',':')).encode())
            frames.append(g)
        result[name]={'full_local_trace_sha256':digest(raw),'full_local_trace_bytes':len(raw),'scene':d['scene'],'metrics':d['metrics'],'frames':frames}
    data=json.dumps(result,separators=(',',':')).encode();packed=gzip.compress(data,mtime=0)
    (HERE/'validation/execution_samples.json.gz').write_bytes(packed)
    report={'scope':'SYNTHETIC_ONLY; compact full execution samples, planned path hashes, no bulk point/mesh stream',
            'packed_file':'validation/execution_samples.json.gz','packed_sha256':digest(packed),'unpacked_sha256':digest(data),
            'packed_bytes':len(packed),'unpacked_bytes':len(data),
            'full_raw_trace_reproduction':'python -B run_candidate.py open_normal tight_normal open_dropout open_delay blocked_5; timings differ; deterministic execution/planned path checks independent',
            'scenarios':{n:{'metrics':d['metrics'],'full_local_trace_sha256':d['full_local_trace_sha256'],'frames':len(d['frames'])} for n,d in result.items()}}
    (HERE/'validation/execution_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='scenarios'},indent=2))
