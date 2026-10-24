"""Test one isolated, per-call, exact-coordinate allowed() memo. No source edit."""
from pathlib import Path
import cProfile, inspect, io, json, pstats, time
import profile_planning as fixture
import numpy as np
from functools import lru_cache
c=fixture.c; OUT=fixture.OUT; c.YAW_MAX=.12
source=inspect.getsource(c.build_path)
assert source.count(' def allowed(q):')==1
copy=source.replace('def build_path(', 'def build_path_memoized(',1).replace(' def allowed(q):',' def allowed(q):\n  return allowed_cached(tuple(q))\n @lru_cache(maxsize=None)\n def allowed_cached(q):',1).replace(' return out\n',' build_path_memoized.last_cache_info=allowed_cached.cache_info()._asdict()\n return out\n',1)
(OUT/'memoized_build_path.py').write_text('"""Isolated experimental copy. Requires frozen simulate_curved on sys.path. Do not deploy."""\nfrom simulate_curved import *\nfrom functools import lru_cache\nYAW_MAX=.12\n\n'+copy)
ns=dict(c.__dict__);ns['lru_cache']=lru_cache
exec(compile(copy,str(OUT/'memoized_build_path.py'),'exec'),ns)
fn=ns['build_path_memoized']
fixture_data=np.load(OUT/'initial_open_observed_fixture.npz');pose=tuple(fixture_data['pose']);grid=fixture_data['grid']
expected=json.loads((OUT/'baseline_path.json').read_text())
stats,path=fixture.timed(fn,pose,grid,5)
assert np.array_equal(np.asarray(path,dtype=np.float64).view(np.uint64),np.asarray(expected,dtype=np.float64).view(np.uint64))
profile=cProfile.Profile();start=time.perf_counter();profiled=profile.runcall(fn,pose,grid);wall=time.perf_counter()-start
assert np.array_equal(np.asarray(profiled,dtype=np.float64).view(np.uint64),np.asarray(expected,dtype=np.float64).view(np.uint64))
profile.dump_stats(str(OUT/'memoized.prof'));s=io.StringIO();ps=pstats.Stats(profile,stream=s);ps.sort_stats('cumulative').print_stats(30);(OUT/'memoized_profile.txt').write_text(s.getvalue())
original=json.loads((OUT/'results.json').read_text())
result=dict(optimization='Per-build_path lru_cache(maxsize=None) of allowed() keyed by exact (x,y) float tuple; no rounding, unchanged geometry, fresh cache for each call.',scope='Initial OPEN fixture only; no full-run, other-layout, hardware or concurrency qualification',unprofiled=stats,profile_wall_s=wall,cache_info=fn.last_cache_info,float64_bitwise_equal=True,baseline_path_sha256=original['path_sha256'],speedup_from_medians=original['baseline_unprofiled']['median_s']/stats['median_s'],remaining_median_tick_ratio=stats['median_tick_ratio'],remaining_median_freshness_ratio=stats['median_freshness_ratio'])
assert all(fixture.sha(Path(p))==h for p,h in original['source_sha256'].items())
(OUT/'memoization_results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
