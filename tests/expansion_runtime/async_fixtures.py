"""Generated transport fixtures; algorithms/service come from exact peer exports."""
from dataclasses import replace
from types import SimpleNamespace as NS
import struct

from robot_dashboard.expansion_runtime.async_adapter import AsyncRuntimeAdapter, Capture
from robot_dashboard.expansion_runtime.owner_identity import from_owner
from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig
from robot_dashboard.ros.observation_identity import subscription_graph_snapshot, make_subscription_evidence
from . import latest_fixtures


def observation(ctx, stamp, receipt, *, topic='/review/input'):
    qos = dict(reliability='BEST_EFFORT',durability='VOLATILE',history='KEEP_LAST',depth=1)
    graph = subscription_graph_snapshot(topic,'sensor_msgs/msg/PointCloud2',1,
        [dict(node_name='generated_owner',node_namespace='/robot_scope_review_x',topic_type='sensor_msgs/msg/PointCloud2',
              endpoint_gid='01'*16,qos=qos)],receipt/1e9)
    return dict(publisher_epoch=ctx.source_epoch,source_stamp_ns=str(stamp),received_monotonic_s=receipt/1e9,
        identity_status='UNAVAILABLE',source_clock='ROS_HEADER_UNVERIFIED',reset_reason=None,
        subscription_evidence=make_subscription_evidence('a'*32,topic,'sensor_msgs/msg/PointCloud2',qos,graph))


def setup():
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    rt,p,state,clock = latest_fixtures.setup(active=False)
    captures = {}
    def factory(context):
        return SceneSnapshotService(context.map_binding,host_clock_id=context.host_clock_id,clock=clock,
                                    schema_version='0.2',stream_epoch=f'c4-{context.runtime_generation}')
    adapter = AsyncRuntimeAdapter(rt,capture_provider=lambda i: captures[(i.source_epoch,i.sequence)],
        scene_factory=factory,source_id='lidar',clock_ns=clock,config=RuntimeConfig(mode='synthetic'))

    def packet(sequence=1, points=((2.,0.,.3),(2.02,.02,.31)), context=None):
        ctx = context or adapter.context
        stamp = 1_000_000_000+sequence*1000
        receipt = stamp+1_000_000
        sec,ns = divmod(stamp,10**9)
        data = b''.join(struct.pack('<fff',*point) for point in points)
        msg = NS(header=NS(frame_id='review_lidar',stamp=NS(sec=sec,nanosec=ns)),
            width=len(points),height=1,point_step=12,row_step=len(data),data=data,is_bigendian=False,
            fields=[NS(name=n,offset=i*4,datatype=7,count=1) for i,n in enumerate('xyz')])
        obs = observation(ctx,stamp,receipt)
        ident = from_owner(msg,obs,context=ctx,source_id='lidar',sequence=sequence,receipt_ns=receipt,
                           clock_domain='fixture-clock',evidence_kind='SYNTHETIC')
        meta = dict(source_epoch=ctx.source_epoch,sequence=sequence,stamp_ns=str(stamp),
            frame_key=dict(source_epoch=ctx.source_epoch,frame_id=ctx.frame_id),map_binding=ctx.map_binding,
            clock_domain='fixture-clock',host_clock_id=ctx.host_clock_id,received_monotonic_ns=receipt,
            evidence_kind='SYNTHETIC')
        transform = dict(verified=True,source_frame='review_lidar',target_frame=ctx.frame_id,stamp_ns=str(stamp),
            source_epoch=ctx.source_epoch,tf_epoch=ctx.tf_epoch,clock_domain='fixture-clock',
            matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        captures[(ctx.source_epoch,sequence)] = Capture(transform,dict(state,**meta,joint_stamp_ns=str(stamp)),
                                                     'fixture-calibration',10.,3.14,obs)
        return msg,ident
    return adapter,packet,clock,captures,replace
