"""VM-only initial OPEN observed-grid planning profile. Source remains read-only."""
from pathlib import Path
import argparse, cProfile, hashlib, importlib, io, json, os, platform, pstats, sys, time
import numpy as np
OUT = Path(__file__).resolve().parent
SOURCE = Path('/workspace/scratch/b09eacf6919d/robot-scope-left-slalom-20261024/experiments/competition_vm/arena_robot_sim/revisions/curved_progress_20261024')
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))
import simulate_curved as c
import run_candidate as candidate

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def summary(times):
    return dict(samples_s=times, min_s=min(times), median_s=float(np.median(times)), p95_s=float(np.percentile(times,95)), max_s=max(times), median_tick_ratio=float(np.median(times))/.1, median_freshness_ratio=float(np.median(times))/.25)
def timed(fn, pose, grid, repeats):
    results=[]; paths=[]
    for i in range(repeats):
        start=time.perf_counter(); path=fn(pose,grid); elapsed=time.perf_counter()-start
        results.append(elapsed); paths.append(path)
        print(f'{fn.__name__} repeat {i+1}: {elapsed:.6f}s, {len(path)} waypoints',flush=True)
    assert all(p == paths[0] for p in paths)
    return summary(results), paths[0]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repeats',type=int,default=5);args=ap.parse_args()
    hashes={str(p):sha(p) for p in (SOURCE/'simulate_curved.py',SOURCE/'run_candidate.py',Path(c.base.__file__),Path(sys.modules['core'].__file__),Path(c.base.sim.__file__))}
    c.YAW_MAX=.12
    pose=tuple(c.base.START)
    setup_start=time.perf_counter();static=c.static_grid();occ=c.Occupancy(static,c.RES)
    tris=c.base.sim.mesh(candidate.OPEN)
    ranges,points=c.base.sim.raycast(tris,pose)
    scan=c.Scan('curved-slalom',0,'1','VM_SIM','vm_laser',c.base.sim.ANGLES,ranges,8.,0.)
    assert occ.update(scan,pose,0.)
    observed,unknown=occ.masks(0.,ttl=2.);grid=observed|unknown
    setup_s=time.perf_counter()-setup_start
    np.savez_compressed(OUT/'initial_open_observed_fixture.npz',pose=np.array(pose),static=static,grid=grid,observed=observed,unknown=unknown,angles=c.base.sim.ANGLES,ranges=ranges)
    print(f'Observed fixture ready in {setup_s:.3f}s. No truth raster built or passed to planning.',flush=True)
    stats,path=timed(c.build_path,pose,grid,args.repeats)
    profile=cProfile.Profile();start=time.perf_counter();profiled_path=profile.runcall(c.build_path,pose,grid);profile_wall=time.perf_counter()-start
    assert profiled_path==path
    profile.dump_stats(str(OUT/'baseline.prof'))
    stream=io.StringIO();ps=pstats.Stats(profile,stream=stream);ps.sort_stats('cumulative').print_stats(40);ps.sort_stats('tottime').print_stats(40)
    (OUT/'baseline_profile.txt').write_text(stream.getvalue())
    top=[]
    for (file,line,name),(cc,nc,tt,ct,callers) in sorted(ps.stats.items(),key=lambda x:x[1][3],reverse=True)[:35]:
        top.append(dict(file=file,line=line,name=name,primitive_calls=cc,calls=nc,self_s=tt,cumulative_s=ct,cumulative_share=ct/ps.total_tt,self_share=tt/ps.total_tt))
    result=dict(scope='VM-only frozen build_path; initial OPEN occupancy from ideal raycast plus Occupancy.update, not hidden raster truth',source_sha256=hashes,python=sys.version,platform=platform.platform(),numpy=np.__version__,cpu_count=os.cpu_count(),setup_wall_s=setup_s,grid_shape=list(grid.shape),static_cells=int(static.sum()),observed_blocked_cells=int(observed.sum()),unknown_cells=int(unknown.sum()),path_waypoints=len(path),path_sha256=hashlib.sha256(json.dumps(path,separators=(',',':')).encode()).hexdigest(),baseline_unprofiled=stats,baseline_profile_wall_s=profile_wall,baseline_profile_total_s=ps.total_tt,baseline_hotspots=top)
    (OUT/'baseline_path.json').write_text(json.dumps(path,separators=(',',':')))
    assert all(sha(Path(p))==h for p,h in hashes.items())
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
