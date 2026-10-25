"""Independent read-only fixture witness audit. Imports no project geometry helper.
Uses complex-plane winding numbers, edge intersections, and vertex-edge distances.
No planner, controller, ROS, dynamic claim, or generated map is involved.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STEP = .0005


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def as_complex(points):
    a = np.asarray(points)
    return a[..., 0] + 1j * a[..., 1]


def inside(points, polygon):
    delta = polygon - points[..., None]
    angles = np.angle(np.roll(delta, -1, axis=-1) * np.conj(delta))
    return np.abs(angles.sum(axis=-1)) > math.pi


def cross(a, b):
    return (np.conj(a) * b).imag


def separation(robot, poly):
    a = robot[:, :, None]
    b = np.roll(robot, -1, axis=1)[:, :, None]
    c = poly[None, None, :]
    d = np.roll(poly, -1)[None, None, :]
    # Including collinear intersections is handled by the zero endpoint distance.
    proper_cross = ((cross(b-a, c-a) * cross(b-a, d-a) < 0) &
                    (cross(d-c, a-c) * cross(d-c, b-c) < 0)).any(axis=(1, 2))
    def point_edge(p, x, y):
        edge = y-x
        fraction = np.clip(((p-x)*np.conj(edge)).real / np.abs(edge)**2, 0, 1)
        return np.abs(p-x-fraction*edge)
    distance = np.minimum.reduce([point_edge(a,c,d), point_edge(b,c,d),
                                  point_edge(c,a,b), point_edge(d,a,b)]).min(axis=(1,2))
    return np.where(proper_cross, 0., distance)


def audit(truth, witness):
    poses = np.array(witness['poses'])
    assert poses.ndim == 2 and poses.shape[1] == 3 and len(poses) >= 2
    assert np.isfinite(poses).all()
    assert np.allclose(poses[0], truth['start'], atol=1e-12)
    assert np.allclose(poses[-1], truth['goal'], atol=1e-12)
    body = as_complex(truth['footprint'])
    boundary = as_complex(truth['boundary_polygon'])
    obstacles = [as_complex(o['polygon']) for o in truth['obstacles']]
    obstacles += [as_complex(p) for p in truth['forbidden_polygons']]
    radius = float(np.abs(body).max())
    bound = float('inf')
    sample_min = float('inf')
    count = 0
    lateral = 0
    for p, q in zip(poses, poses[1:]):
        motion = float(np.linalg.norm(q[:2]-p[:2]) + radius*abs(q[2]-p[2]))
        n = max(1, math.ceil(motion/STEP))
        pose = p+(q-p)*np.linspace(0, 1, n+1)[:, None]
        robot = as_complex(pose[:, :2])[:, None] + np.exp(1j*pose[:, 2, None])*body
        valid = inside(robot, boundary).all(axis=1)
        clear = separation(robot, boundary)
        for poly in obstacles:
            overlap = inside(robot, poly).any(axis=1)
            # Broadcasting supports each moving robot polygon separately.
            overlap |= inside(poly[None, :], robot[:, None, :]).any(axis=1)
            valid &= ~overlap
            clear = np.minimum(clear, separation(robot, poly))
        clear = np.where(valid, clear, 0.)
        local = float(clear.min())
        sample_min = min(sample_min, local)
        bound = min(bound, local-motion/(2*n))
        count += n+1
        lateral += int(abs(cross(np.exp(1j*p[2]), complex(*(q[:2]-p[:2])))) > 1e-10)
    assert bound >= truth['clearance_m']
    return dict(pass_=True, samples=count, sampled_clearance_m=sample_min,
                continuous_clearance_lower_bound_m=bound, max_vertex_step_m=STEP,
                lateral_translation_edges=lateral, witness_sha256=digest(witness),
                truth_sha256=digest(truth))


def main():
    manifest = json.loads((ROOT/'fixtures/manifest.json').read_text())
    for name, expected in manifest['files'].items():
        assert digest(json.loads((ROOT/'fixtures'/name).read_text())) == expected, name
    results = {}
    for path in sorted((ROOT/'witnesses').glob('*.json')):
        truth = json.loads((ROOT/'fixtures'/f'{path.stem}.truth.json').read_text())
        witness = json.loads(path.read_text())
        results[path.stem] = audit(truth, witness)
    assert len(results) == 6
    output = dict(scope='INDEPENDENT_GEOMETRY_ONLY_NOT_NATIVE_NAV2',
                  method='Complex winding and independent edge geometry; 0.5mm motion samples minus half-step Hausdorff bound',
                  manifest_sha256=digest(manifest), results=results)
    (ROOT/'review/independent_results.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
