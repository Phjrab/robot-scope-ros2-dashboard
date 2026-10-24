"""Create small lossless projections for offline tests; never modify full traces."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
NAMES=('delayed_offset_1__legacy_parking_allowed','dropout_offset_1__legacy_parking_allowed')
FIELDS=('t','v','w','sensor_fresh')
def build():
 out=HERE/'fixtures';out.mkdir(exist_ok=True)
 for name in NAMES:
  source=HERE/'results'/f'{name}__repeat1.json';raw=source.read_bytes();doc=json.loads(raw)
  fixture=dict(fixture_schema='d0-observation-projection.v1',source_file=str(source.relative_to(HERE)),source_file_sha256=hashlib.sha256(raw).hexdigest(),source_frame_count=len(doc['frames']),retained_frame_fields=list(FIELDS),projection='Exact values for every source frame; no downsampling or numeric rounding',metrics=doc['metrics'],frames=[{k:f[k] for k in FIELDS} for f in doc['frames']])
  (out/f'{name}.json').write_text(json.dumps(fixture,indent=2)+'\n')
def verify():
 rows=[]
 for name in NAMES:
  source=HERE/'results'/f'{name}__repeat1.json';raw=source.read_bytes();doc=json.loads(raw)
  fixture=HERE/'fixtures'/f'{name}.json';f=json.loads(fixture.read_text())
  expected=[{k:frame[k] for k in FIELDS} for frame in doc['frames']]
  row=dict(source_file=str(source.relative_to(HERE)),source_file_sha256=hashlib.sha256(raw).hexdigest(),fixture_file=str(fixture.relative_to(HERE)),fixture_file_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),source_frames=len(doc['frames']),fixture_frames=len(f['frames']),all_tested_fields_exactly_equal=f['frames']==expected,all_metrics_exactly_equal=f['metrics']==doc['metrics'],source_hash_matches=f['source_file_sha256']==hashlib.sha256(raw).hexdigest())
  rows.append(row)
 report=dict(retained_frame_fields=list(FIELDS),downsampling=False,numeric_rounding=False,all_pass=all(x['all_tested_fields_exactly_equal'] and x['all_metrics_exactly_equal'] and x['source_hash_matches'] and x['source_frames']==x['fixture_frames'] for x in rows),rows=rows)
 (HERE/'results/compact_projection_verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 if not report['all_pass']:raise SystemExit(1)
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--verify',action='store_true');args=ap.parse_args()
 if args.verify:verify()
 else:build()
