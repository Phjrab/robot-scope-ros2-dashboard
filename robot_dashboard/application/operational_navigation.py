"""Explicit idle selection and immutable per-Nav2-job 3D map bundles."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import shutil
import threading
import uuid
import time

from ..relocalization.experimental_se3 import from_translation_rpy, validate_transform
from ..relocalization.operational import SCHEMA, digest, validate_bundle
from ..saved_maps import SavedMapError


class OperationalNavigation:
    def __init__(self, catalog, root, jobs):
        self.catalog, self.root, self.jobs = catalog, Path(root), jobs
        self.lock = threading.RLock()
        # Never restore execution selection/seed across dashboard restarts.
        self.selected = None
        self.used_geometry = None
        self.snapshot_binding = None

    def status(self):
        with self.lock:
            initial = None
            if self.selected and self.selected.get('seed_T_map_imu') is not None:
                calibration = self.selected['calibration']
                pose = (validate_transform(calibration['T_nav_map_from_localization_map'])
                        @ validate_transform(self.selected['seed_T_map_imu'])
                        @ validate_transform(calibration['T_imu_base']))
                initial = {'map_id': self.selected['navigation_2d']['map_id'],
                           'map_revision': self.selected['navigation_2d']['revision'],
                           'pose': {'x': float(pose[0, 3]), 'y': float(pose[1, 3]),
                                    'yaw': math.atan2(pose[1, 0], pose[0, 0])}}
            pair = self._pair_status()
            return {'selected': copy.deepcopy(self.selected), 'pair': pair,
                    'initial_pose_confirmation': initial,
                    'calibration_available': (self.root / 'operational-calibration.json').is_file(),
                    'activation': 'NEXT_NAVIGATION_START' if self.selected else 'LEGACY_2D'}

    def _idle(self):
        if self.jobs.snapshot()['pipeline']['state'] not in {'idle', 'stopped', 'failed'}:
            raise ValueError('STOP_NAVIGATION_BEFORE_SOURCE_SELECTION')

    def _calibration(self):
        path = self.root / 'operational-calibration.json'
        if not path.is_file():
            raise ValueError('DEVICE_BODY_MAP_ALIGNMENT_READBACK_REQUIRED')
        if path.is_symlink() or path.stat().st_size > 128 * 1024:
            raise ValueError('INVALID_CALIBRATION_FILE')
        calibration = json.loads(path.read_text())
        if calibration.get('verified') is not True or not calibration.get('evidence'):
            raise ValueError('BODY_AND_MAP_CALIBRATION_REQUIRED')
        from ..relocalization.transform_authority import TransformAuthorityMonitor
        TransformAuthorityMonitor(calibration.get('tf_publishers'))
        validate_transform(calibration['T_imu_base'])
        return calibration, digest(path)

    def _family(self, source, nav):
        """Use persisted conversion proof, never map names or coincident frame labels."""
        from ..map_lineage import parse_family_document
        families = self.catalog.map_family(nav.map_id)['families']
        matches = [parse_family_document(item) for item in families
                   if item['source']['pcd_map_id'] == source['map_id']
                   and item['source']['pcd_revision'] == source['revision']
                   and item['source']['frame_id'] == source['frame_id']
                   and item['occupancy']['map_id'] == nav.map_id
                   and item['occupancy']['map_revision'] == nav.revision]
        if len(matches) != 1:
            raise ValueError('MAP_PAIR_LINEAGE_MISMATCH')
        family = matches[0]
        geometry = self.catalog._read_map_yaml(nav.yaml_path)
        metadata = self.catalog.metadata(nav.map_id)
        expected = {'frame_id': nav.frame_id, 'resolution': geometry['resolution'],
                    'origin': list(geometry['origin']), 'width': metadata['width'], 'height': metadata['height']}
        if any(family['occupancy'].get(key) != value for key, value in expected.items()):
            raise ValueError('MAP_PAIR_GEOMETRY_MISMATCH')
        return family

    def _pair_status(self):
        bundle = self.selected
        if not bundle or bundle.get('workflow') != 'staged_navigation_pair':
            return None
        checks = []
        try:
            self._revalidate_pair(bundle)
        except (ValueError, KeyError, OSError, SavedMapError) as exc:
            checks.append({'code': str(exc), 'current': '지도 또는 교정 확인이 무효가 됨',
                'required': '현재 ID·revision·교정과 일치하는 지도 조합',
                'remedy': '정상 정지 후 지도를 다시 선택하고 ①부터 연결 확인'})
        geometry = bundle.get('seed_geometry')
        if geometry is not None and self.used_geometry == (bundle['generation'], geometry['confirmed_at']) and self.jobs.snapshot()['pipeline']['state'] in {'idle', 'stopped', 'failed'}:
            checks.append({'code': 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED', 'current': '이전 실행에서 사용한 높이·기울기',
                'required': '새 실행의 현재 초기 높이·기울기 확인', 'remedy': '②에서 현재 값을 다시 확인하고 적용'})
        if geometry is None:
            checks.append({'code': 'INITIAL_HEIGHT_TILT_REQUIRED', 'current': '초기 높이·기울기 미지정',
                'required': '지도 좌표의 본체 높이(z)·roll·pitch 초기값',
                'remedy': '②에서 확인한 높이·기울기를 입력하고 적용. 미확인 값은 비워 두기'})
        return {'generation': bundle['generation'], 'localization_3d': copy.deepcopy(bundle['localization_3d']),
                'navigation_2d': copy.deepcopy(bundle['navigation_2d']),
                'family': copy.deepcopy(bundle['map_binding']['family']),
                'calibration_sha256': bundle['map_binding']['calibration_sha256'],
                'seed_geometry': copy.deepcopy(geometry), 'checks': checks,
                'valid': not any(item['code'] not in {'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'} for item in checks),
                'can_start': not checks, 'restart_from_step': 1 if any(item['code'] not in {'INITIAL_HEIGHT_TILT_REQUIRED', 'INITIAL_GEOMETRY_RECONFIRM_REQUIRED'} for item in checks) else 2 if checks else None}

    def _revalidate_pair(self, bundle):
        source = self.catalog.pcd_edit_source(bundle['localization_3d']['map_id'])
        if source['revision'] != bundle['localization_3d']['revision'] or source['sha256'] != bundle['localization_3d']['sha256']:
            raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
        pin = bundle['navigation_2d']
        nav = self.catalog.resolve_navigation_map(pin['map_id'], pin['revision'])
        family = self._family(source, nav)
        if family != bundle['map_binding']['family']:
            raise ValueError('MAP_PAIR_LINEAGE_CHANGED')
        calibration, sha = self._calibration()
        if sha != bundle['map_binding']['calibration_sha256']:
            raise ValueError('CALIBRATION_CHANGED_REAPPLY_PAIR')
        if (calibration.get('controller_odom_topic') != self.jobs.controller_odom_topic
                or calibration.get('navigation_profile') != self.jobs.navigation_profile):
            raise ValueError('CALIBRATION_PROFILE_OR_MAP_MISMATCH')

    def select_pair(self, body):
        return self._select(body, paired=True)

    def seed_geometry(self, body):
        with self.lock:
            self._idle()
            bundle = self.selected
            if not bundle or bundle.get('workflow') != 'staged_navigation_pair' or body.get('generation') != bundle['generation']:
                raise ValueError('MAP_PAIR_GENERATION_CHANGED')
            self._revalidate_pair(bundle)
            if set(body) != {'generation', 'z', 'roll', 'pitch'}:
                raise ValueError('INVALID_SEED_GEOMETRY')
            for key, limit in (('z', 1000), ('roll', math.pi), ('pitch', math.pi / 2)):
                value = body[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                    raise ValueError('INVALID_SEED_GEOMETRY')
            candidate = copy.deepcopy(bundle)
            candidate['seed_geometry'] = {key: float(body[key]) for key in ('z', 'roll', 'pitch')}
            candidate['seed_geometry'].update(frame='map', source='operator',
                confirmed_at=time.time())
            self.selected = validate_bundle(candidate)
            return self.status()

    def select(self, body):
        return self._select(body)

    def _select(self, body, *, paired=False):
        allowed = {'map_id', 'map_revision', 'navigation_map_id', 'navigation_map_revision', 'seed_pose', 'course_region'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise ValueError('INVALID_SELECTION_FIELDS')
        with self.lock:
            self._idle()
            if not body:
                self.selected = None
                return self.status()
            source = self.catalog.pcd_edit_source(body['map_id'])
            if source['revision'] != body['map_revision']:
                raise ValueError('LOCALIZATION_MAP_REVISION_CHANGED')
            nav = self.catalog.resolve_navigation_map(body['navigation_map_id'], body['navigation_map_revision'])
            metadata = self.catalog.metadata(nav.map_id)
            nav_geometry = self.catalog._read_map_yaml(nav.yaml_path)
            calibration, calibration_sha = self._calibration()
            expected = {'localization_frame': source['frame_id'],
                        'controller_odom_topic': self.jobs.controller_odom_topic,
                        'navigation_profile': self.jobs.navigation_profile}
            if not paired:
                expected.update(navigation_map_id=nav.map_id, navigation_map_revision=nav.revision)
            if any(calibration.get(k) != v for k, v in expected.items()):
                raise ValueError('CALIBRATION_PROFILE_OR_MAP_MISMATCH')
            family = self._family(source, nav) if paired else None
            source_metadata = self.catalog.metadata(body['map_id'])
            if paired:
                # Reuse only the trusted body/TF/profile/quality calibration. Map-to-map
                # binding comes from the exact conversion document, not the old map pin.
                root = source_metadata.get('origin') or source
                calibration['localization_root'] = {key: root[key] for key in ('map_id', 'revision', 'sha256', 'frame_id', 'units')}
                calibration.update(navigation_map_id=nav.map_id, navigation_map_revision=nav.revision)
                projection = family['frame_projection']
                calibration['T_nav_map_from_localization_map'] = from_translation_rpy(
                    projection['translation'], projection['rotation_rpy']).tolist()
                seed = None
            else:
                pose = body['seed_pose']
                seed = from_translation_rpy([pose[k] for k in ('x', 'y', 'z')],
                    [pose[k] for k in ('roll', 'pitch', 'yaw')]).tolist()
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
                'calibration': calibration, 'policy': calibration['policy'], 'seed_T_map_imu': seed}
            if paired:
                bundle.update(workflow='staged_navigation_pair', seed_geometry=None,
                    map_binding={'family': family, 'calibration_sha256': calibration_sha})
                bundle['localization_3d']['name'] = source_metadata['name']
                bundle['navigation_2d']['name'] = metadata['name']
            course = body.get('course_region')
            if course is not None:
                from ..course_regions import course_values
                bundle['course_region'] = course_values(course)
                if (course['map_id'], course['map_revision'], course['map_frame']) != (body['map_id'], source['revision'], source['frame_id']):
                    raise ValueError('COURSE_REFERENCE_CHANGED')
            self.selected = validate_bundle(bundle)
            return self.status()

    def expected_source(self, job_id, map_id, revision):
        with self.lock:
            value = self.snapshot_binding
            if value and (value['job_id'], value['map_id'], value['map_revision']) == (job_id, map_id, revision):
                return copy.deepcopy(value)
            return None

    def preflight(self, map_id, revision):
        """Reject missing evidence before starting the shared sensor pipeline."""
        with self.lock:
            if self.selected is None:
                return
            bundle = self.selected
            if (bundle['navigation_2d']['map_id'], bundle['navigation_2d']['revision']) != (map_id, revision):
                raise ValueError('SELECTED_3D_BUNDLE_REQUIRES_ITS_PINNED_2D_MAP')
            if bundle.get('workflow') == 'staged_navigation_pair':
                self._revalidate_pair(bundle)
                geometry = bundle.get('seed_geometry')
                if geometry is None:
                    raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
                if self.used_geometry == (bundle['generation'], geometry['confirmed_at']):
                    raise ValueError('INITIAL_GEOMETRY_RECONFIRM_REQUIRED')

    def snapshot_for_job(self, map_id, revision, destination, navigation_snapshot=None):
        with self.lock:
            if self.selected is None:
                return
            bundle = copy.deepcopy(self.selected)
            if bundle.get('workflow') == 'staged_navigation_pair':
                self._revalidate_pair(bundle)
                if bundle.get('seed_geometry') is None:
                    raise ValueError('INITIAL_HEIGHT_TILT_REQUIRED')
                if self.used_geometry == (bundle['generation'], bundle['seed_geometry']['confirmed_at']):
                    raise ValueError('INITIAL_GEOMETRY_RECONFIRM_REQUIRED')
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
            self.snapshot_binding = {'job_id': destination.name, 'source': 'STORED_PCD_FASTLIO',
                'bundle_generation': bundle['generation'], 'map_id': map_id, 'map_revision': revision,
                'localization_map_id': bundle['localization_3d']['map_id'],
                'localization_map_revision': bundle['localization_3d']['revision']}
            if bundle.get('workflow') == 'staged_navigation_pair':
                self.used_geometry = (bundle['generation'], bundle['seed_geometry']['confirmed_at'])
