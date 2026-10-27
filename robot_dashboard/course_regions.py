"""Confirmed map-local weighting polygons. Never edits map geometry or robot state."""
from __future__ import annotations

import math
import re

import numpy as np

from .navigation_presets import PresetConflict, PresetInvalid
from .observation_presets import ObservationPresetStore
from .pcd_editing.geometry import PcdEditError, _compile_region, _selection_mask, validate_regions


def course_values(value):
    if not isinstance(value, dict) or set(value) != {
        'map_id', 'map_revision', 'map_frame', 'polygon', 'outside_weight', 'confirmed', 'units'
    }:
        raise PresetInvalid('코스 영역 형식이 올바르지 않습니다.')
    if (not isinstance(value['map_id'], str) or not re.fullmatch(r'[a-f0-9]{24}', value['map_id'])
            or not isinstance(value['map_revision'], str) or not re.fullmatch(r'[a-f0-9]{64}', value['map_revision'])
            or not isinstance(value['map_frame'], str) or not 1 <= len(value['map_frame']) <= 160
            or value['confirmed'] is not True or value['units'] != 'm'):
        raise PresetInvalid('확인된 지도 좌표의 코스 영역이 필요합니다.')
    weight = value['outside_weight']
    if type(weight) not in (int, float) or not math.isfinite(weight) or not .1 <= weight <= 1:
        raise PresetInvalid('주변 영역 비중은 10~100%여야 합니다.')
    try:
        polygon = value['polygon']
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 64:
            raise PcdEditError('코스 경계는 3~64개 꼭짓점으로 지정하세요.')
        normalized = validate_regions([dict(kind='localization', polygon=polygon, z_min=-1e6, z_max=1e6)])[0]
        if any(abs(n) > 1000 for xy in normalized['polygon'] for n in xy):
            raise PcdEditError('코스 좌표는 ±1000m 이내여야 합니다.')
    except PcdEditError as exc:
        raise PresetInvalid(str(exc)) from exc
    return {**value, 'polygon': normalized['polygon'], 'outside_weight': float(weight)}


def course_membership(points, course):
    """Use existing editor geometry; XY membership includes every height."""
    region = _compile_region(dict(kind='localization', selection='inside', polygon=course['polygon'],
                                  z_min=-1e6, z_max=1e6))
    return _selection_mask(points[:, 0], points[:, 1], np.zeros(len(points)), region)


def course_weights(points, course):
    return np.where(course_membership(points, course), 1., course['outside_weight'])


class CourseRegionStore(ObservationPresetStore):
    """Reuse bounded, locked, atomic preset storage, scoped to geometry revision."""
    values_validator = staticmethod(course_values)

    def snapshot(self, map_id):
        context = self._context(map_id)
        presets = self._store(map_id).snapshot()['presets']
        compatible = [p for p in presets if all(p['values'][k] == v for k, v in context.items())]
        return dict(map=context, presets=compatible, incompatible_count=len(presets)-len(compatible))

    def create(self, map_id, name, map_revision, map_frame, polygon, outside_weight, confirmed):
        context = self._context(map_id)
        if (context['map_revision'], context['map_frame']) != (map_revision, map_frame):
            raise PresetConflict('지도 좌표가 변경됐습니다. 현재 지도에서 영역을 다시 확인하세요.')
        values = course_values(dict(**context, polygon=polygon, outside_weight=outside_weight,
                                    confirmed=confirmed, units='m'))
        return self._store(map_id).create(name, values)
