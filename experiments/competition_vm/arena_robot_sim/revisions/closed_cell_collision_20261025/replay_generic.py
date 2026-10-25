"""Optional slow reference replay for exact optimized-vs-generic audit."""
from pathlib import Path
import sys
import simulate_curved as c
from collision import Snapshot as GenericSnapshot
from run_candidate import OPEN
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    c.Snapshot=GenericSnapshot
    static=c.static_grid()
    for name in sys.argv[1:] or ['open_normal','tight_normal','open_dropout','open_delay','blocked_5']:
        c.YAW_MAX=.015 if name.startswith('tight') else .12
        cones=c.base.configs()['slalom_5'] if name.startswith('tight') else c.base.configs()['blocked_5'] if name=='blocked_5' else OPEN
        c.run(name,cones,static,HERE/'results/generic_candidate02',sensor='dropout' if name.endswith('dropout') else 'delay' if name.endswith('delay') else 'normal')
