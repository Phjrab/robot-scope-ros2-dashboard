"""Synthetic solver only; actual proposal owner/global coordinator remain intact.

A production-specific trusted retention-proof generator is intentionally NOT
invented here. On integrated code, C0 must provide a pinned, reviewed fixture
adapter if the real envelope requires evidence beyond the legacy result shape.
"""
import copy,hashlib,importlib.util,math,os,pathlib,threading
import numpy as np
from test_anchor_proposal import result_for
from robot_dashboard.relocalization.v031_observation_compat import apply_ambiguity_override

def draft_for_fixture(fixture,pair):
 calibration=fixture.manager.status()['selected']['calibration']
 transform=np.asarray(calibration['T_nav_map_from_localization_map']) @ fixture.source.runner.pose @ np.asarray(calibration['T_imu_base'])
 return {'status':'ready','revision':'synthetic-draft-1','bundle_generation':pair['generation'],
 'navigation_map':{'id':pair['navigation_2d']['map_id'],'revision':pair['navigation_2d']['revision']},
 'pose':{'x':float(transform[0,3]),'y':float(transform[1,3]),'yaw':math.atan2(float(transform[1,0]),float(transform[0,0]))}}

def install_runner(fixture):
 # Only a C0-reviewed adapter pinned to an exact hash may invoke the actual
 # integrated retention evidence producer. No caller-supplied proof literals.
 name=os.environ.get('PRIOR_RETENTION_ADAPTER');expected=os.environ.get('PRIOR_RETENTION_ADAPTER_SHA256')
 if not name or not expected:raise RuntimeError('REVIEWED_RETENTION_ADAPTER_REQUIRED')
 path=pathlib.Path(name).resolve(strict=True)
 if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('RETENTION_ADAPTER_HASH_MISMATCH')
 spec=importlib.util.spec_from_file_location('reviewed_prior_retention_adapter',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 if not callable(getattr(module,'attach_real_retention_evidence',None)):raise RuntimeError('RETENTION_ADAPTER_ENTRYPOINT_REQUIRED')
 runner=fixture.source.runner;fixture.runner_thread_ids=[]
 def run_arrays(*,scan_bytes,map_bytes,context,cancel_event):
  fixture.runner_thread_ids.append(threading.get_ident());runner.calls+=1;runner.entered.set();runner.release.wait(5.)
  near=runner.pose.copy();far=runner.pose.copy();far[0,3]+=4.
  if fixture.solver_variant in ('unique-in','unique-out'):
   single=near if fixture.solver_variant=='unique-in' else far
   result=result_for(context,single)
   fixture.synthetic_observation={'gate_reasons':copy.deepcopy(result['gate_reasons']),'candidate_count':len(result['candidates']),'selected_candidate':result['selected_candidate']}
   return module.attach_real_retention_evidence(result,context,variant=fixture.solver_variant)
  if fixture.solver_variant=='zero':near[0,3]+=4.;far[0,3]+=4.
  if fixture.solver_variant=='multiple':far=near.copy();far[2,3]+=1.
  result=result_for(context,near);template=result['candidates'][0];candidates=[]
  for matrix,rmse in ((near,.20),(far,.01)):
   c=copy.deepcopy(template);c.update(map_from_scan=matrix.tolist(),gate_reasons=['AMBIGUOUS_ALTERNATIVES'],capped_full_rmse_m=.10,rmse_m=rmse);candidates.append(c)
  if fixture.solver_variant=='bad-quality':candidates[1]['inlier_count']=0
  result.update(gate_reasons=['AMBIGUOUS_ALTERNATIVES'],selected_candidate=None,candidates=candidates)
  # Existing observation-only rank chooses the far, lower-rmse candidate. The
  # integration under test must not treat that rank as a unique resolution.
  apply_ambiguity_override(result,allow_ambiguous=True)
  fixture.synthetic_observation={'gate_reasons':copy.deepcopy(result['gate_reasons']),'candidate_count':len(result['candidates']),'selected_candidate':result['selected_candidate']}
  # The adapter must call the integrated implementation's genuine retention
  # evidence producer for this synthetic observation; do not accept a hand-made
  # success proof. The truncated branch must model the actual producer format.
  return module.attach_real_retention_evidence(result,context,variant=fixture.solver_variant)
 runner.run_arrays=run_arrays
