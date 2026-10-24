"""Default integration smoke now exercises strict D0 lifecycle/action boundaries.
Historical smoke source/results remain in the immutable original result and D0
baseline fixture. All outputs are SYNTHETIC_IN_PROCESS, never real action ACKs.
"""
import json
from d0_smoke import run

if __name__=='__main__':
    for row in run(): print(json.dumps(row,sort_keys=True))
