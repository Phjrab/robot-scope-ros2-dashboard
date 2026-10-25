"""VM-only convex-footprint / closed occupied-cell collision checks.

A broadphase includes one extra cell on *both* ends, avoiding roundoff at
integer cell boundaries. Narrowphase uses normalized SAT axes and a conservative
metric tolerance: 1e-12 m + 64 machine eps * max(1 m, absolute coordinates).
A positive gap below that tolerance may be reported as contact, never clearance.
This is not a calibrated uncertainty budget or a real-time/hardware guarantee.
"""
import math
import numpy as np


def _collides(mask, res, origin, pose, footprint):
    try:
        p = np.asarray(footprint, dtype=float)
        pose = np.asarray(pose, dtype=float)
    except (ValueError, TypeError):
        return True
    if (p.ndim != 2 or p.shape[1:] != (2,) or len(p) < 3
            or pose.shape != (3,) or not np.isfinite(p).all()
            or not np.isfinite(pose).all()):
        return True
    c, s = math.cos(pose[2]), math.sin(pose[2])
    p = p @ np.array([[c, s], [-s, c]]) + pose[:2]
    scale = max(1., float(np.abs(p).max()), float(np.abs(origin).max()),
                float(max(mask.shape) * res))
    tol = 1e-12 + 64 * np.finfo(float).eps * scale
    lower, upper = p.min(axis=0), p.max(axis=0)
    extent = np.array([mask.shape[1], mask.shape[0]]) * res + origin
    # Outside world is occupied, including closed world boundary contact.
    if np.any(lower <= origin + tol) or np.any(upper >= extent - tol):
        return True
    edges = np.roll(p, -1, axis=0) - p
    lengths = np.linalg.norm(edges, axis=1)
    if np.any(lengths <= tol):
        return True
    # All vertices must lie on one consistent side of every edge. Merely
    # checking successive turn signs incorrectly accepts self-crossing stars.
    relative = p - p[0]
    offsets = relative[None, :, :] - relative[:, None, :]
    side = edges[:, None, 0] * offsets[:, :, 1] - edges[:, None, 1] * offsets[:, :, 0]
    side_tol = tol * lengths[:, None]
    if not (np.all(side >= -side_tol) or np.all(side <= side_tol)):
        return True
    axes = np.vstack((np.column_stack((-edges[:, 1], edges[:, 0])) / lengths[:, None], np.eye(2)))
    if abs(np.sum(relative[:, 0] * np.roll(relative[:, 1], -1) - relative[:, 1] * np.roll(relative[:, 0], -1))) <= tol * max(lengths):
        return True
    low = np.floor((lower - tol - origin) / res).astype(int) - 1
    high = np.floor((upper + tol - origin) / res).astype(int) + 1
    x0, y0 = np.maximum(low, 0)
    x1, y1 = np.minimum(high, [mask.shape[1] - 1, mask.shape[0] - 1])
    yy, xx = np.nonzero(mask[y0:y1 + 1, x0:x1 + 1])
    if not len(xx):
        return False
    centers = np.column_stack((xx + x0 + .5, yy + y0 + .5)) * res + origin
    projections = relative @ axes.T
    center_proj = (centers - p[0]) @ axes.T
    radius = .5 * res * np.abs(axes).sum(axis=1)
    separated = ((center_proj + radius < projections.min(axis=0) - tol)
                 | (center_proj - radius > projections.max(axis=0) + tol))
    return bool(np.any(~np.any(separated, axis=1)))


def _validate(mask, res, origin):
    if np.ndim(mask) != 2 or min(np.shape(mask)) == 0:
        raise ValueError('Nonempty 2D occupancy mask required')
    origin = np.asarray(origin, dtype=float)
    if not math.isfinite(res) or res <= 0 or origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError('Positive finite resolution and finite 2D origin required')
    return origin


class Snapshot:
    """Owned immutable occupancy copy. Construct anew per planning call/epoch.

    No global cache or map identity shortcut. Source age/TTL are enforced by
    the caller; a snapshot is not evidence that an observation remains fresh.
    """
    def __init__(self, mask, res, origin=(0., 0.)):
        self.origin = _validate(mask, res, origin).copy()
        self.origin.flags.writeable = False
        self.res = float(res)
        self._mask = np.array(mask, dtype=bool, copy=True)
        self._mask.flags.writeable = False

    def collides(self, pose, footprint):
        return _collides(self._mask, self.res, self.origin, pose, footprint)


def polygon_collision(pose, footprint, mask, res):
    """Ephemeral borrowed-mask query; no copy/cache retained across guard calls."""
    origin = _validate(mask, res, (0., 0.))
    return _collides(np.asarray(mask, dtype=bool), float(res), origin, pose, footprint)
