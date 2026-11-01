"""Small synthetic packet/robot; no sensor, model weights, or simulated physics."""
from dataclasses import replace
import copy
import numpy as np

from robot_dashboard.expansion_runtime import ClockMapping, InputFramePacket, RuntimeContext, Runtime, SyntheticCoverage
from robot_dashboard.expansion_runtime.binding import digest
from robot_dashboard.expansion_runtime.ports import CorePorts


class Clock:
    def __init__(self, now=1_010_000_000):
        self.now = now

    def __call__(self):
        return self.now


def setup(*, active=True, point_x=2., sequence=1, stamp=1_000_000_000, clock=None):
    from robot_dashboard.collision_geometry_core import RobotGeometry
    geometry = RobotGeometry('<robot><link name="base"><collision><geometry><box size="0.716 0.324 0.35"/></geometry></collision></link></robot>',
                             provenance='SYNTHETIC_C4_packet_fixture_NOT_GAIT')
    ctx = RuntimeContext(1, 'a'*24, 'b'*64, 0, 'synthetic-family', 'family-r1', 'footprint-r1',
        geometry.geometry_hash, 'goal-1', 1, 'lease-1', 'bounded-body-twist', 'synthetic-1',
        'odom', 'tf-1', 'clock-1', 'fixture-host')
    mapping = ClockMapping('fixture-clock', ctx.source_epoch, ctx.clock_epoch, ctx.host_clock_id,
                           0, 0, 0, 10**12, 'SYNTHETIC_SHARED_CLOCK')
    clock = clock or Clock()
    runtime = Runtime(CorePorts.from_installed(geometry), ctx, mapping,
                      mode='ACTIVE_CONSTRAINT' if active else 'ADVISORY_ONLY', clock=clock)
    meta = dict(frame_key=dict(source_epoch=ctx.source_epoch, frame_id=ctx.frame_id),
        stamp_ns=str(stamp), source_epoch=ctx.source_epoch, sequence=sequence,
        clock_domain='fixture-clock', host_clock_id=ctx.host_clock_id, received_monotonic_ns=stamp+1_000_000,
        evidence_kind='SYNTHETIC', map_binding=ctx.map_binding, calibration_id='fixture-calibration')
    points = np.array([[point_x, 0, .3], [point_x+.02, .02, .31]]) if point_x is not None else np.empty((0, 3))
    source = dict(meta=copy.deepcopy(meta), tf_epoch=ctx.tf_epoch, origin_m=[0., 0., .3],
        max_range_m=10., fov_rad=3.14, valid_measurement=True, calibration_id='fixture-calibration',
        raw_reference='generated-lidar-'+str(sequence), free_rays=[])
    packet = InputFramePacket(meta, ctx.key, ctx.clock_epoch, ctx.tf_epoch, points, dict(lidar=source))
    state = dict(meta, pose=[[1,0,0,0],[0,1,0,0],[0,0,1,.3],[0,0,0,1]], joints={},
        joint_stamp_ns=str(stamp), calibration_known=True, pose_uncertainty_m=.01, joint_uncertainty_m=0.)
    return runtime, packet, state, clock


def coverage(runtime, packet, *, command_sequence=1, velocity=(.1, 0., 0.), horizon=.1):
    return SyntheticCoverage(runtime.context.key, digest(runtime.motion(command_sequence, velocity, horizon)),
        packet.meta['sequence'], 1_200_000_000, 'FINITE_SYNTHETIC_SCENE_C4')


def run(runtime, packet, state, *, complete=False, **kwargs):
    defaults = dict(command_sequence=1, velocity=(.1,0.,0.), authority_present=True)
    defaults.update(kwargs)
    if complete:
        defaults['coverage'] = coverage(runtime, packet, command_sequence=defaults['command_sequence'], velocity=defaults['velocity'])
    return runtime.process(packet, state, **defaults)


def rgbd(packet, *, invalid=False, detections=True):
    k = dict(fx=60.,fy=60.,ppx=20.,ppy=20.,width=40,height=40,model='none',coeffs=[0]*5)
    calibration = dict(id='synthetic-depth',verified=True,clock_correspondence_verified=True,meta=copy.deepcopy(packet.meta),
        depth_intrinsics=k.copy(),color_intrinsics=k.copy(),depth_scale_m=.001,uncertainty_m=.01,
        T_color_depth=np.eye(4).tolist(),T_local_depth=np.eye(4).tolist())
    depth=np.full((40,40),3000.); depth[12:28,12:28]=1000.
    if invalid:
        depth.fill(0)
    det = dict(class_id=0,class_name='cone',score=.9,bbox_xyxy=[12,12,28,28],native_shape=[40,40])
    manifest = dict(sha256='c'*64,preprocess='native_xyxy_no_resize',class_names={'0':'cone'},evidence_kind='SYNTHETIC')
    sensor = copy.deepcopy(packet.sensor_evidence)
    sensor['depth'] = dict(sensor['lidar'], calibration_id='synthetic-depth',raw_reference='generated-depth',
                           valid_measurement=not invalid)
    return replace(packet, depth=depth, detections=(det,) if detections else (), calibration=calibration,
                   model_manifest=manifest, sensor_evidence=sensor)
