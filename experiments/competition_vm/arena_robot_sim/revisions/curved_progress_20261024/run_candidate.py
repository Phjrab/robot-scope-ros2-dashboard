from pathlib import Path
import simulate_curved as c
HERE=Path(__file__).resolve().parent
OPEN=[c.base.cone(i+1,x,y) for i,(x,y) in enumerate([(.18,1.8),(.18,2.08),(.18,2.36),(.82,4.05),(.82,4.33)])]
if __name__=='__main__':
 import sys
 static=c.static_grid()
 for name in sys.argv[1:] or ['open_normal','tight_normal']:
  c.YAW_MAX=.015 if name.startswith('tight') else .12
  cones=c.base.configs()['slalom_5'] if name.startswith('tight') else c.base.configs()['blocked_5'] if name=='blocked_5' else OPEN
  c.run(name,cones,static,HERE/'results/candidate02',sensor='dropout' if name.endswith('dropout') else 'delay' if name.endswith('delay') else 'normal')
