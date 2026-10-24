from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'left_slalom_20261024'))
import simulate_slalom as b
assert b.RES==.02
cones=[b.cone(i+1,x,y) for i,(x,y) in enumerate([(.18,1.8),(.18,2.08),(.18,2.36),(.82,4.05),(.82,4.33)])]
b.run('open_baseline',cones,b.static_grid(),HERE/'results/final_regressions')
