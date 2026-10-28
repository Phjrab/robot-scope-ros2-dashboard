"""Explicit idle selection and immutable per-Nav2-job 3D map bundles."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import shutil
import threading
import uuid

from ..relocalization.experimental_se3 import from_translation_rpy, validate_transform
from ..relocalization.operational import SCHEMA, digest, validate_bundle


class OperationalNavigation:
    def __init__(self, catalog, root, jobs):
        self.catalog, self.root, self.jobs = catalog, Path(root), jobs
        self.lock = threading.RLock()
        # Never restore execution selection/seed across dashboard restarts.
        self.selected = None

    def status(self):
        with self.lock:
            initial = None
            if self.selected:
                calibration = self.selected['calibration']
                pose = (validate_transform(calibration['T_nav_map_from_localization_map'])
                        @ validate_transform(self.selected['seed_T_map_imu'])
                        @ validate_transform(calibration['T_imu_base']))
                initial = {'map_id': self.selected['navigation_2d']['map_id'],
                           'map_revision': self.selected['navigation_2d']['revision'],
                           'pose': {'x': float(pose[0, 3]), 'y': float(pose[1, 3]),
                                    'yaw': math.atan2(pose[1, 0], pose[0, 0])}}
            return {'selected': copy.deepcopy(self.selected),
                    'initial_pose_confirmation': initial,
                    'calibration_available': (self.root / 'operational-calibration.json').is_file(),
                    'activation': 'NEXT_NAVIGATION_START' if self.selected else 'LEGACY_2D'}

    def select(self, body):
        allowed = {'map_id', 'map_revision', 'navigation_map_id', 'navigation_map_revision', 'seed_pose', 'course_region'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise ValueError('INVALID_SELECTION_FIELDS')
        with self.lock:
            if self.jobs.snapshot()['pipeline']['state'] not in {'idle', 'stopped', 'failed'}:
                raise ValueError('STOP_NAVIGATION_BEFORE_SOURCE_SELECTION')
            if not body:
                self.selected = None
                return self.status()
            source = self.catalog.pcd_edit_source(body['map_id'])
            if source['revision'] != body['map_revision']:
                raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
            nav = self.catalog.resolve_navigation_map(body['navigation_map_id'], body['navigation_map_revision'])
            metadata = self.catalog.metadata(nav.map_id)
            nav_geometry = self.catalog._read_map_yaml(nav.yaml_path)
            path = self.root / 'operational-calibration.json'
            if not path.is_file():
                raise ValueError('DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED')
            if path.is_symlink() or path.stat().st_size > 128 * 1024:
                raise ValueError('INVALID_CALIBRATION_FILE')
            calibration = json.loads(path.read_text())
            # These pins are written after device/TF/profile readback, not by HTTP.
            expected = {'localization_frame': source['frame_id'], 'navigation_map_id': nav.map_id,
                        'navigation_map_revision': nav.revision, 'controller_odom_topic': self.jobs.controller_odom_topic,
                        'navigation_profile': self.jobs.navigation_profile}
            if any(calibration.get(k) != v for k, v in expected.items()):
                raise ValueError('CALIBRATION_PROFILE_OR_MAP_MISMATCH')
            from ..relocalization.transform_authority import TransformAuthorityMonitor
            TransformAuthorityMonitor(calibration.get('tf_publishers'))
            # Identity is not inferred just because both frames happen to be named map.
            pose = body['seed_pose']
            seed = from_translation_rpy([pose[k] for k in ('x', 'y', 'z')],
                [pose[k] for k in ('roll', 'pitch', 'yaw')])
            bundle = {'schema': SCHEMA, 'generation': uuid.uuid4().hex,
                'localization_3d': {'map_id': body['map_id'], 'revision': source['revision'],
                    'sha256': source['sha256'], 'frame': source['frame_id'], 'units': source['units'],
                    'lineage': self.catalog.metadata(body['map_id']).get('origin'),
                    'source': self.catalog.metadata(body['map_id']).get('source'),
                    'edit_history': self.catalog.metadata(body['map_id']).get('edit_history', [])},
                'navigation_2d': {'map_id': nav.map_id, 'revision': nav.revision, 'frame': nav.frame_id,
                    'resolution': nav_geometry['resolution'], 'origin': nav_geometry['origin'],
                    'metadata_revision': metadata['revision'],
                    'yaml_sha256': digest(nav.yaml_path), 'image_sha256': digest(nav.image_path)},
                'calibration': calibration, 'policy': calibration['policy'], 'seed_T_map_imu': seed.tolist()}
            course = body.get('course_region')
            if course is not None:
                from ..course_regions import course_values
                bundle['course_region'] = course_values(course)
                if (course['map_id'], course['map_revision'], course['map_frame']) != (body['map_id'], source['revision'], source['frame_id']):
                    raise ValueError('COURSE_REFERENCE_CHANGED')
            self.selected = validate_bundle(bundle)
            return self.status()

    def snapshot_for_job(self, map_id, revision, destination, navigation_snapshot=None):
        with self.lock:
            if self.selected is None:
                return
            bundle = copy.deepcopy(self.selected)
            if (bundle['navigation_2d']['map_id'], bundle['navigation_2d']['revision']) != (map_id, revision):
                raise ValueError('SELECTED_3D_BUNDLE_REQUIRES_ITS_PINNED_2D_MAP')
            source = self.catalog._pcd_edit_source_asset(bundle['localization_3d']['map_id'])
            if source.revision != bundle['localization_3d']['revision']:
                raise ValueError('LOCALIZATION_REFERENCE_CHANGED')
            nav = self.catalog.resolve_navigation_map(map_id, revision)
            if (digest(nav.yaml_path) != bundle['navigation_2d']['yaml_sha256']
                    or digest(nav.image_path) != bundle['navigation_2d']['image_sha256']):
                raise ValueError('NAVIGATION_MAP_GEOMETRY_CHANGED')
            if navigation_snapshot is not None:
                import yaml
                document = yaml.safe_load(navigation_snapshot.yaml_path.read_text())
                original = yaml.safe_load(nav.yaml_path.read_text())
                def geometry(value):
                    return {k: v for k, v in value.items() if k != 'image'}
                if (navigation_snapshot.map_id != map_id or navigation_snapshot.revision != revision
                        or navigation_snapshot.frame_id != 'map'
                        or digest(navigation_snapshot.image_path) != bundle['navigation_2d']['image_sha256']
                        or document.get('image') != navigation_snapshot.image_path.name
                        or navigation_snapshot.image_path.parent != navigation_snapshot.yaml_path.parent
                        or navigation_snapshot.image_path.parent != Path(destination)
                        or document.get('resolution') != navigation_snapshot.resolution
                        or tuple(document.get('origin', ())) != tuple(navigation_snapshot.origin)
                        or geometry(document) != geometry(original)):
                    raise ValueError('NAVIGATION_JOB_SNAPSHOT_MISMATCH')
                bundle['navigation_2d']['consumer_yaml_sha256'] = digest(navigation_snapshot.yaml_path)
                bundle['navigation_2d']['resolution'] = navigation_snapshot.resolution
                bundle['navigation_2d']['origin'] = list(navigation_snapshot.origin)
            destination = Path(destination)
            target = destination / 'localization-reference.pcd'
            # No overwrite, original file and all attributes survive unchanged.
            with source.path.open('rb') as reader, target.open('xb') as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
            if digest(target) != bundle['localization_3d']['sha256']:
                target.unlink()
                raise ValueError('LOCALIZATION_REFERENCE_HASH_CHANGED')
            with (destination / 'operational-3d.json').open('x') as stream:
                json.dump(bundle, stream, allow_nan=False, sort_keys=True)
