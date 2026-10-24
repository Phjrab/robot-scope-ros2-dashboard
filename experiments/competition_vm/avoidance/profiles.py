"""Versioned VM candidate builder. Production allowlists are intentionally unchanged."""
import copy,json,hashlib
from pathlib import Path
import yaml
RPP='nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController'
MPPI='nav2_mppi_controller::MPPIController'
def build(base,controller,footprint='circle'):
 if controller not in ('RPP','MPPI') or footprint not in ('circle','polygon'): raise ValueError('unsupported profile')
 d=copy.deepcopy(base)
 d.pop("robot_scope_navigation_runtime",None)
 d['planner_server']['ros__parameters']['GridBased'].update(allow_unknown=False,tolerance=0.)
 p=d['controller_server']['ros__parameters']; p['odom_topic']='/competition_vm/odom'; p['controller_frequency']=10.
 p['FollowPath']={'plugin':RPP,'desired_linear_vel':.25,'lookahead_dist':.4,'use_velocity_scaled_lookahead_dist':False,'use_collision_detection':True,'max_allowed_time_to_collision_up_to_carrot':1.,'allow_reversing':False,'use_rotate_to_heading':True} if controller=='RPP' else {'plugin':MPPI,'motion_model':'DiffDrive','time_steps':30,'model_dt':.05,'batch_size':256,'iteration_count':1,'vx_max':.25,'vx_min':0.,'vy_max':0.,'wz_max':.8,'vx_std':.1,'vy_std':0.,'wz_std':.2,'temperature':.3,'gamma':.015,'critics':['ConstraintCritic','CostCritic','GoalCritic','PathFollowCritic','PathAngleCritic','PreferForwardCritic'],'CostCritic':{'enabled':True,'consider_footprint':footprint=='polygon','collision_cost':1000000.}}
 for root in ('global_costmap','local_costmap'):
  c=d[root][root]['ros__parameters']; c['robot_radius']=.31; c['resolution']=.05; c['track_unknown_space']=True
  c['footprint']='[[-0.25,-0.18],[0.25,-0.18],[0.25,0.18],[-0.25,0.18]]' if footprint=='polygon' else '[]'
  c['obstacle_layer']['scan']['topic']='/competition_vm/scan'
  c['obstacle_layer']['scan']['expected_update_rate']=.3
  c['obstacle_layer']['scan']['observation_persistence']=0.
  c['inflation_layer']['inflation_radius']=.4
  if 'static_layer' in c: c['static_layer']['map_topic']='/competition_vm/map'
 d['behavior_server']['ros__parameters']['behavior_plugins']=['wait']
 for k in list(d):
  if 'ros__parameters' in d[k]: d[k]['ros__parameters']['use_sim_time']=True
 for k in ('global_costmap','local_costmap'): d[k][k]['ros__parameters']['use_sim_time']=True
 d['bt_navigator']['ros__parameters']['odom_topic']='/competition_vm/odom'
 return d

def assert_effective(expected,actual):
 for k in ('planner_server','controller_server','global_costmap','local_costmap'):
  if expected[k]!=actual[k]: raise ValueError('POLICY_READBACK_MISMATCH:'+k)
 return True
if __name__=='__main__':
 root=Path(__file__).resolve().parent; repo=root.parents[2]
 base=yaml.safe_load((repo/'config/nav2_params_go2_humble.yaml').read_text())
 for controller in ('RPP','MPPI'):
  for footprint in ('circle','polygon'):
   profile=build(base,controller,footprint)
   (root/'config'/f'{controller.lower()}_{footprint}_vm_candidate.yaml').write_text(yaml.safe_dump(profile,sort_keys=False))
