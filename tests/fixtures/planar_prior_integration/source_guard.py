"""Fail closed until C0 supplies the exact integrated checkout and hashes."""
import hashlib,json,os,pathlib,subprocess,sys
REQUIRED={'robot_dashboard/api/routers/operational_navigation.py','robot_dashboard/api/routers/fastlio_observation.py','robot_dashboard/application/navigation_initialization_proposal.py','robot_dashboard/application/global_observation.py','robot_dashboard/application/operational_navigation.py','robot_dashboard/application/fastlio_observation.py','robot_dashboard/relocalization/handoff_policy.py','robot_dashboard/static/features/navigation/preparation.js','robot_dashboard/static/features/navigation/pose_draft.js','robot_dashboard/static/app.js','tests/test_anchor_proposal.py','tests/test_navigation_initialization_proposal.py','tests/test_navigation_proposal_handoff.py','tests/test_operational_navigation_bundle.py','tests/test_observation_subscription_evidence.py'}
def checked_root():
 root=os.environ.get('PRIOR_SOURCE_ROOT');name=os.environ.get('PRIOR_HASH_MANIFEST')
 if not root or not name:raise RuntimeError('EXACT_INTEGRATED_SOURCE_AND_HASH_MANIFEST_REQUIRED')
 root=pathlib.Path(root).resolve(strict=True);manifest=json.loads(pathlib.Path(name).read_text());files=manifest.get('files')
 if not isinstance(files,dict) or not REQUIRED.issubset(files) or not isinstance(manifest.get('snapshot_id'),str) or not manifest['snapshot_id']:raise RuntimeError('INCOMPLETE_SOURCE_PIN_MANIFEST')
 if manifest.get('complete_source_snapshot') is not True:raise RuntimeError('FULL_SOURCE_PIN_REQUIRED')
 tracked=subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z']).split(b'\0')
 names={p.decode() for p in tracked if p}
 if set(files)!=names:raise RuntimeError('SOURCE_SNAPSHOT_SET_MISMATCH')
 for rel,digest in files.items():
  p=pathlib.PurePosixPath(rel)
  if p.is_absolute() or '..' in p.parts or not isinstance(digest,str) or len(digest)!=64:raise RuntimeError('BAD_SOURCE_PIN')
  target=(root/rel).resolve(strict=True)
  if not target.is_relative_to(root) or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise RuntimeError('SOURCE_HASH_MISMATCH:'+rel)
 sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'));return root,manifest['snapshot_id']
