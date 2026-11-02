"""Opt-in current-scan weighting for stored-map ICP, never FAST-LIO or /scan.

Directions use full exact-stamp T_odom_base, not LiDAR X or travel direction.
Map neighbourhoods describe surfaces; only current query points supply votes.
The information spectrum is a degeneracy diagnostic, not pose covariance.
"""
from __future__ import annotations

import math
import time

import numpy as np

from .experimental_se3 import transform_points, inverse, validate_transform

BASELINE = 'ALL_DIRECTION_BASELINE'
CANDIDATE = 'REAR_SIDE_QUALITY_V1'
SECTORS = ('front', 'rear', 'left', 'right')
DEFAULTS = dict(rear_max_gain=1.5, side_max_gain=1.25, pitch_start_deg=4.,
                pitch_full_deg=12., transition_s=1., max_gain_rate_per_s=.25,
                density_voxel_m=.25, residual_scale_m=.15,
                min_information_ratio=.001, independent_sector_mass_cap=48.)


def validate_weighting(value=None):
    if value is None:
        return {'mode': BASELINE}
    if not isinstance(value, dict) or set(value) - {'mode', 'evidence', *DEFAULTS}:
        raise ValueError('INVALID_DIRECTIONAL_WEIGHTING')
    mode = value.get('mode')
    if mode == BASELINE:
        if set(value) != {'mode'}:
            raise ValueError('BASELINE_REQUIRES_NO_WEIGHTING_OVERRIDES')
        return {'mode': BASELINE}
    if mode != CANDIDATE or not isinstance(value.get('evidence'), str) or not 1 <= len(value['evidence']) <= 256:
        raise ValueError('WEIGHTING_CANDIDATE_EVIDENCE_REQUIRED')
    result = {'mode': mode, 'evidence': value['evidence'], **DEFAULTS, **value}
    limits = dict(rear_max_gain=(1., 2.), side_max_gain=(1., 1.5),
                  pitch_start_deg=(0., 15.), pitch_full_deg=(2., 30.),
                  transition_s=(.5, 5.), max_gain_rate_per_s=(.05, .5),
                  density_voxel_m=(.1, .5), residual_scale_m=(.05, .3),
                  min_information_ratio=(.001, .02), independent_sector_mass_cap=(12., 128.))
    for key, (low, high) in limits.items():
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('INVALID_DIRECTIONAL_WEIGHTING_' + key.upper())
    if result['pitch_full_deg'] <= result['pitch_start_deg']:
        raise ValueError('INVALID_DIRECTIONAL_PITCH_INTERVAL')
    return result


def body_coordinates(points, odom_base):
    return transform_points(inverse(validate_transform(odom_base)), points)


def sector_ids(body_points):
    x, y = np.asarray(body_points)[:, :2].T
    ids = np.where(x > np.abs(y), 0, np.where(-x > np.abs(y), 1, np.where(y >= np.abs(x), 2, 3)))
    return ids.astype(np.int64)


def sector_counts(points, odom_base):
    ids = sector_ids(body_coordinates(points, odom_base))
    return dict(zip(SECTORS, map(int, np.bincount(ids, minlength=4))))


class SurfaceSupport:
    """Bounded cache of immutable map normals; no accumulated query history."""
    def __init__(self, reference_index):
        self.index = reference_index
        n = len(reference_index.points)
        self.normals = np.zeros((n, 3))
        self.confidence = np.zeros(n)
        self.known = np.zeros(n, dtype=bool)

    def get(self, ids, deadline):
        if self.index.tree is None:
            return self.normals[ids], self.confidence[ids]
        missing = np.unique(ids[~self.known[ids]])
        for start in range(0, len(missing), 128):
            if time.monotonic() > deadline:
                raise ValueError('COMPUTE_BUDGET_EXCEEDED')
            rows = missing[start:start + 128]
            distance, neighbours = self.index.tree.query(self.index.points[rows], k=12,
                distance_upper_bound=.75, workers=1)
            valid = np.isfinite(distance) & (neighbours < len(self.index.points))
            count = valid.sum(axis=1)
            xyz = self.index.points[np.minimum(neighbours, len(self.index.points)-1)]
            centre = (xyz * valid[:, :, None]).sum(axis=1) / np.maximum(count[:, None], 1)
            centred = (xyz-centre[:, None, :]) * valid[:, :, None]
            covariance = np.einsum('nki,nkj->nij', centred, centred) / np.maximum(count[:, None, None], 1)
            eigen, vectors = np.linalg.eigh(covariance)
            planar = np.clip(1.-eigen[:, 0]/np.maximum(.2*eigen[:, 1], 1e-12), 0., 1.)
            spread = np.clip(eigen[:, 1]/np.maximum(.05*eigen[:, 2], 1e-12), 0., 1.)
            confidence = planar * spread * (count >= 6)
            self.normals[rows] = vectors[:, :, 0]
            self.confidence[rows] = confidence
            self.known[rows] = True
        if time.monotonic() > deadline:
            raise ValueError('COMPUTE_BUDGET_EXCEEDED')
        return self.normals[ids], self.confidence[ids]


class DirectionalFrame:
    """Pure per-frame proposal; its small temporal state is committed by owner.

    Calls during ICP always derive from the previous *frame* state. Iteration
    count cannot speed up gain transitions. Stale/out-of-order/gapped stamps
    reset the gain to one; generation changes discard the proposal upstream.
    """
    def __init__(self, config, support, points, odom_base, stamp_ns, previous, deadline, *, frame_verified):
        self.config = validate_weighting(config)
        if self.config['mode'] != CANDIDATE or frame_verified is not True:
            raise ValueError('VERIFIED_BODY_FRAME_REQUIRED_FOR_WEIGHTING')
        config = self.config
        self.support, self.deadline = support, deadline
        self.body = body_coordinates(points, odom_base)
        self.ids = sector_ids(self.body)
        self.stamp = int(stamp_ns)
        if self.stamp <= 0:
            raise ValueError('INVALID_DIRECTIONAL_SOURCE_STAMP')
        self.pitch = math.asin(float(np.clip(-validate_transform(odom_base)[2, 0], -1, 1)))
        _, self.voxel_id, self.voxel_count = np.unique(
            np.floor(self.body/config['density_voxel_m']+1e-9).astype(np.int64), axis=0,
            return_inverse=True, return_counts=True)
        self.previous_gain = np.ones(4)
        self.dt = 0.
        if previous is not None:
            dt = (self.stamp-int(previous['stamp_ns']))*1e-9
            gains = np.asarray(previous['gains'], dtype=float)
            if (0 < dt <= .75 and gains.shape == (4,) and np.isfinite(gains).all()
                    and np.all(gains >= 1.) and np.all(gains <= [1., config['rear_max_gain'],
                        config['side_max_gain'], config['side_max_gain']])):
                self.dt, self.previous_gain = dt, gains.copy()
        self.diagnostics = {}
        self.next_state = {'stamp_ns': self.stamp, 'gains': [1., 1., 1., 1.]}

    def __call__(self, moved, target_ids, squared, mask):
        if time.monotonic() > self.deadline:
            raise ValueError('COMPUTE_BUDGET_EXCEEDED')
        c = self.config
        good = np.flatnonzero(mask)
        normals, confidence = self.support.get(target_ids[good], self.deadline)
        pairs, pair_id, repeats = np.unique(
            np.column_stack([self.voxel_id[good], target_ids[good]]), axis=0,
            return_inverse=True, return_counts=True)
        targets_per_voxel = np.bincount(pairs[:, 0], minlength=len(self.voxel_count))
        density = 1./(repeats[pair_id]*targets_per_voxel[self.voxel_id[good]])
        _, target_id = np.unique(target_ids[good], return_inverse=True)
        target_mass = np.bincount(target_id, weights=density)
        density /= np.maximum(1., target_mass[target_id])
        residual_quality = np.exp(-squared[good]/(c['residual_scale_m']**2))
        quality = .25 + .75*confidence*residual_quality
        raw_mass = density*quality
        quality_by_sector = np.zeros(4)
        groups = []
        for sector, name in enumerate(SECTORS):
            selected = self.ids[good] == sector
            count = int((self.ids == sector).sum())
            independent = len(np.unique(self.voxel_id[good[selected]]))
            supported = selected & (confidence >= .3)
            diversity = 0.
            spatial = 0.
            if supported.sum() >= 6 and independent >= 6:
                ns = normals[supported]
                mass = density[supported]*confidence[supported]
                eigen = np.linalg.eigvalsh((ns*mass[:, None]).T @ ns/max(mass.sum(), 1e-12))
                ratio = float(eigen[1]/max(eigen[-1], 1e-12))
                # A numerical/noisy single normal is not a second structure.
                diversity = 0. if ratio < .02 else float(np.clip(ratio/.15, 0., 1.))
                points = self.body[good[supported]]
                centred = points-np.average(points, axis=0, weights=mass)
                spread = np.linalg.eigvalsh((centred*mass[:, None]).T @ centred/max(mass.sum(), 1e-12))
                spatial = float(np.clip(spread[1]/max(.05*spread[-1], 1e-12), 0., 1.))
            overlap = float(selected.sum()/count) if count else 0.
            fit = float(np.average(residual_quality[selected], weights=density[selected])) if selected.any() else 0.
            quality_by_sector[sector] = overlap*fit*diversity*spatial
            # Many returns in one direction cannot supply unbounded mass.
            mass = float(raw_mass[selected].sum())
            if mass > c['independent_sector_mass_cap']:
                raw_mass[selected] *= c['independent_sector_mass_cap']/mass
            groups.append(dict(sector=name, input_points=count, matched_points=int(selected.sum()),
                independent_query_voxels=independent, unique_map_matches=int(len(np.unique(target_ids[good[selected]]))),
                overlap_ratio=overlap, surface_diversity=diversity, spatial_spread=spatial,
                boost_quality=float(quality_by_sector[sector])))
        pitch = np.clip((abs(math.degrees(self.pitch))-c['pitch_start_deg']) /
                        (c['pitch_full_deg']-c['pitch_start_deg']), 0., 1.)
        activation = float(pitch*pitch*(3.-2.*pitch))
        target_gain = 1.+(np.array([1., c['rear_max_gain'], c['side_max_gain'], c['side_max_gain']])-1.)*activation*quality_by_sector
        step = (1.-math.exp(-self.dt/c['transition_s']))*(target_gain-self.previous_gain)
        rate = c['max_gain_rate_per_s']*self.dt
        gains = self.previous_gain+np.clip(step, -rate, rate)
        gain = gains[self.ids[good]]
        weights = np.zeros(len(moved))
        weights[good] = raw_mass*gain
        total = float(weights.sum())
        for sector, group in enumerate(groups):
            selection = self.ids[good] == sector
            group['gain'] = float(gains[sector])
            group['weight_mass'] = float(weights[good[selection]].sum())
            group['contribution_ratio'] = group['weight_mass']/total if total else 0.
        supported = confidence >= .3
        information = np.zeros((6, 6))
        if supported.any():
            # Dimensionless lever arm prevents metres/radians from defining rank.
            mass = weights[good[supported]]
            positions = moved[good[supported]]
            vectors = positions-np.average(positions, axis=0, weights=mass)
            lever = max(1., float(np.sqrt(np.average(np.sum(vectors*vectors, axis=1), weights=mass))))
            ns = normals[supported]
            jacobian = np.column_stack([ns, np.cross(vectors/lever, ns)])
            information = (jacobian*mass[:, None]).T @ jacobian/max(mass.sum(), 1e-12)
        eigen = np.maximum(np.linalg.eigvalsh(information), 0.)
        information_ratio = float(eigen[0]/max(eigen[-1], 1e-12))
        rank = int((eigen > max(eigen[-1]*c['min_information_ratio'], 1e-12)).sum())
        observable = rank == 6 and information_ratio >= c['min_information_ratio']
        weighted_rmse = float(np.sqrt(np.sum(weights[good]*squared[good])/total)) if total else None
        self.next_state = {'stamp_ns': self.stamp, 'gains': list(map(float, gains))}
        self.diagnostics = dict(mode=CANDIDATE, direction_basis='FULL_EXACT_STAMP_BODY_AXES_NOT_TRAVEL_DIRECTION',
            query_population='CURRENT_SCAN_ONLY', body_pitch_rad=self.pitch,
            pitch_activation=activation, sectors=groups, gain_dt_s=self.dt,
            weighted_objective_rmse_m=weighted_rmse,
            normal_information_eigenvalues=list(map(float, eigen)), information_ratio=information_ratio,
            information_rank=rank, structure_observable=observable,
            information_is_pose_covariance=False, reliable_normal_points=int(supported.sum()),
            reason='STRUCTURE_SUPPORTED' if observable else 'DIRECTIONAL_STRUCTURE_INSUFFICIENT',
            cached_map_normals_are_not_new_observations=True)
        if time.monotonic() > self.deadline:
            raise ValueError('COMPUTE_BUDGET_EXCEEDED')
        return weights

    def finish(self, result):
        self.diagnostics['common_unweighted_rmse_m'] = result['metrics']['rmse_m']
        self.diagnostics['common_unweighted_overlap'] = result['metrics']['overlap_ratio']
        if result['status'] == 'CANDIDATE' and not self.diagnostics.get('structure_observable', False):
            result['status'], result['reason'] = 'REJECTED', 'DIRECTIONAL_STRUCTURE_INSUFFICIENT'
        result['metrics']['directional_weighting'] = self.diagnostics
