"""Explicit named fixtures: NEVER substitute open layout for same-layout comparison."""
from pathlib import Path
import simulate_curved as c
HERE=Path(__file__).resolve().parent
OPEN=[c.base.cone(i+1,x,y) for i,(x,y) in enumerate([(.18,1.8),(.18,2.08),(.18,2.36),(.82,4.05),(.82,4.33)])]
if __name__=='__main__':
 import sys
 c.YAW_MAX=.12
 static=c.static_grid()
 for name in sys.argv[1:] or ['open_normal','open_dropout','open_delay','blocked_5']:
  cones=c.base.configs()['blocked_5'] if name=='blocked_5' else OPEN
  sensor='dropout' if name.endswith('dropout') else 'delay' if name.endswith('delay') else 'normal'
  c.run(name,cones,static,HERE/'results/final_regressions',sensor=sensor)
