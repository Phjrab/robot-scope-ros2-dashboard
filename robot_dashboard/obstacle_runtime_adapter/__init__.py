"""Default-off C4 ports. Importing this package starts no I/O or workers.

D2 perception, D3 collision and C1 contracts are injected by the caller.
No product registration, camera ownership or nonzero command publisher lives here.
"""

from .isolation import RuntimeConfig
from .messages import Identity, Sample

__all__ = ["RuntimeConfig", "Identity", "Sample"]
