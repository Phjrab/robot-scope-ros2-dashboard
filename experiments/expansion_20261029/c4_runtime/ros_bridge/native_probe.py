"""Minimal actual ROS owner -> C4 -> Nav2 planner readback, network-none only.

No controller, actuator, behavior server or navigation goal is launched. D3's
controller/plant runner has no C4 ingress hook at the pinned SHA; that remaining
boundary is recorded, not replaced by a path-following simulator.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import traceback
from collections import deque

from experiments.expansion_20261029.c4_runtime.ros_bridge.dependencies import load, PINS
from robot_dashboard.expansion_runtime import Runtime, RuntimeContext, ClockMapping
from robot_dashboard.expansion_runtime.canonical_ports import CanonicalCorePorts
from robot_dashboard.expansion_runtime.async_adapter import AsyncRuntimeAdapter, Capture
from robot_dashboard.expansion_runtime.owner_identity import from_owner
from robot_dashboard.expansion_runtime.marking_ros import MarkingRosPublisher, TOPIC
from robot_dashboard.obstacle_runtime_adapter.ros_port import ReviewRosPort
from robot_dashboard.obstacle_runtime_adapter.messages import pointcloud2
from robot_dashboard.obstacle_runtime_adapter.isolation import RuntimeConfig, require_local_ros, NAMESPACE
from robot_dashboard.ros.pointcloud import PointCloudHub
from robot_dashboard.ros.observation_identity import subscription_graph_snapshot,make_subscription_evidence
from experiments.expansion_20261029.c4_runtime.ros_bridge.http_probe import server,fetch


async def wait_for(test, label, timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=test()
        if value: return value
        await asyncio.sleep(.02)
    raise RuntimeError('TIMEOUT:'+label)


async def main(output):
    if os.environ.get('C4_NETWORK_NONE')!='1': raise RuntimeError('NETWORK_NONE_RECEIPT_REQUIRED')
    config=RuntimeConfig(mode='isolated_ros',domain_id=194)
    require_local_ros(config)
    paths=load()
    import yaml
    from ament_index_python.packages import get_package_share_directory,get_package_prefix
    import xml.etree.ElementTree as ET
    versions={p:ET.parse(Path(get_package_share_directory(p))/'package.xml').getroot().findtext('version')
              for p in ('nav2_planner','nav2_costmap_2d')}
    if set(versions.values())!={'1.1.20'}: raise RuntimeError('NAV2_VERSION_MISMATCH:'+str(versions))
    from robot_dashboard.collision_geometry_core import RobotGeometry
    from robot_dashboard.expansion_services.scene import SceneSnapshotService
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy,qos_profile_sensor_data
    from rclpy.action import ActionClient
    from sensor_msgs.msg import PointCloud2,PointField
    from nav_msgs.msg import OccupancyGrid
    from tf2_msgs.msg import TFMessage
    from geometry_msgs.msg import TransformStamped
    from lifecycle_msgs.srv import ChangeState,GetState
    from lifecycle_msgs.msg import Transition
    from nav2_msgs.action import ComputePathToPose
    from rcl_interfaces.srv import GetParameters

    rclpy.init(args=[],domain_id=194)
    node=Node('c4_existing_input_owner',namespace=NAMESPACE,enable_rosout=False)
    executor=SingleThreadedExecutor(); executor.add_node(node)
    ros_thread=threading.Thread(target=executor.spin,daemon=True); ros_thread.start()
    planner=None; adapter=None; port=None; log=None; pump=None
    evidence=dict(dependencies=PINS,ROS='STARTED',core='NOT_RUN',HTTP='NOT_RUN',marking='NOT_RUN',
        clearing='NOT_PROVEN',planner='NOT_RUN',simulated_actuator='NOT_RUN_NO_D3_INGRESS_HOOK',
        device='DEVICE_NOT_RUN',mode='ADVISORY_ONLY',versions=versions,cases=[])
    try:
        geometry=RobotGeometry('<robot><link name="base"><collision><geometry><box size="0.716 0.324 0.35"/></geometry></collision></link></robot>',
                               provenance='GENERATED_C4_TRANSPORT_BOX_NOT_GO2_CALIBRATION')
        hub=PointCloudHub(threading.RLock(),max_points=1000,radius_limit_m=20.,frame_interval_s=3.)
        context=RuntimeContext(1,'a'*24,'b'*64,0,'fixture-family','r1','footprint-r1',geometry.geometry_hash,
            'diagnostic-only',1,'no-control-lease','observation-only',hub.observation_identity.epoch,'map','tf-1','clock-1','c4-host')
        anchor=node.get_clock().now().nanoseconds; host=time.monotonic_ns()
        mapping=ClockMapping('generated-host-ros',context.source_epoch,context.clock_epoch,context.host_clock_id,
            host-anchor,2_000_000,anchor-10**9,anchor+120*10**9,'GENERATED_SAME_HOST_CLOCK_PAIR')
        captures={}; callback_errors=[]; accepted=deque(maxlen=64); sequence=[0]
        def factory(ctx):
            return SceneSnapshotService(ctx.map_binding,host_clock_id=ctx.host_clock_id,schema_version='0.2',
                stream_epoch=f'c4-{ctx.runtime_generation}')
        adapter=AsyncRuntimeAdapter(Runtime(CanonicalCorePorts.from_installed(geometry),context,mapping),
            capture_provider=lambda i:captures[(i.source_epoch,i.sequence)],scene_factory=factory,
            config=config,source_id='lidar')
        adapter.start()
        marker=MarkingRosPublisher(node,context_provider=lambda:adapter.context,clock_ns=time.monotonic_ns)
        adapter.observation_sink=marker
        port=ReviewRosPort(config=config,runtime=adapter,identity_provider=None,owner_loop=asyncio.get_running_loop())
        input_topic=NAMESPACE+'/c4/input'
        sender=node.create_publisher(PointCloud2,input_topic,qos_profile_sensor_data)
        # This single existing owner subscription serves both PointCloudHub and
        # C4 handoff. Neither AsyncRuntimeAdapter nor ReviewRosPort.start subscribes.
        def receive(message):
            receipt=time.monotonic_ns()
            try:
                graph=subscription_graph_snapshot(input_topic,'sensor_msgs/msg/PointCloud2',
                    node.count_publishers(input_topic),node.get_publishers_info_by_topic(input_topic),receipt/1e9)
                owner_context=make_subscription_evidence('a'*32,input_topic,'sensor_msgs/msg/PointCloud2',qos_profile_sensor_data,graph)
                hub.process(input_topic,message,receipt/1e9,selected_topic=lambda:input_topic,
                    stamp_ns=lambda m:m.header.stamp.sec*10**9+m.header.stamp.nanosec,
                    robot_pose_in_frame=lambda _:None,publisher_count=1,observation_context=owner_context)
                obs=hub.raw_context_snapshot()['observation']; sequence[0]+=1
                ctx=adapter.context
                identity=from_owner(message,obs,context=ctx,source_id='lidar',sequence=sequence[0],receipt_ns=receipt,
                                    clock_domain=mapping.source_domain,evidence_kind='SYNTHETIC')
                meta=dict(source_epoch=ctx.source_epoch,sequence=identity.sequence,stamp_ns=identity.stamp_ns,
                    clock_domain=identity.clock_domain,host_clock_id=identity.receipt_clock_id,
                    received_monotonic_ns=receipt,evidence_kind='SYNTHETIC',map_binding=ctx.map_binding,
                    frame_key=dict(source_epoch=ctx.source_epoch,frame_id=ctx.frame_id))
                state=dict(meta,pose=[[1,0,0,0],[0,1,0,0],[0,0,1,.3],[0,0,0,1]],joints={},
                    joint_stamp_ns=identity.stamp_ns,calibration_known=True,pose_uncertainty_m=.01,joint_uncertainty_m=0.)
                transform=dict(verified=True,source_frame='review_lidar',target_frame='map',stamp_ns=identity.stamp_ns,
                    source_epoch=ctx.source_epoch,tf_epoch=ctx.tf_epoch,clock_domain=identity.clock_domain,
                    matrix=[[1,0,0,0],[0,1,0,0],[0,0,1,.3],[0,0,0,1]])
                captures[(ctx.source_epoch,sequence[0])]=Capture(transform,state,'fixture-calibration',8.,2*math.pi,obs)
                while len(captures)>16: captures.pop(next(iter(captures)))
                accepted.append((message,identity))
                port.handoff(message,identity,pointcloud2)
            except Exception as exc: callback_errors.append(type(exc).__name__+':'+str(exc))
        subscription=node.create_subscription(PointCloud2,input_topic,receive,qos_profile_sensor_data)
        await wait_for(lambda:node.count_subscribers(input_topic)==1,'ONE_INPUT_OWNER')

        transient=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        static=node.create_publisher(TFMessage,NAMESPACE+'/tf_static',transient)
        transforms=[]
        for parent,child,z in [('map','base_link',.3),('base_link','review_lidar',0.)]:
            tf=TransformStamped(); tf.header.frame_id=parent; tf.child_frame_id=child
            tf.header.stamp=node.get_clock().now().to_msg(); tf.transform.rotation.w=1.; tf.transform.translation.z=z
            transforms.append(tf)
        static.publish(TFMessage(transforms=transforms))
        map_pub=node.create_publisher(OccupancyGrid,NAMESPACE+'/map',transient)
        grid=OccupancyGrid(); grid.header.frame_id='map'; grid.header.stamp=node.get_clock().now().to_msg()
        grid.info.resolution=.04; grid.info.width=250; grid.info.height=250
        grid.info.origin.position.x=-3.; grid.info.origin.position.y=-5.; grid.info.origin.orientation.w=1.
        grid.data=[0]*(250*250); map_pub.publish(grid)
        grids=deque(maxlen=8)
        cost_sub=node.create_subscription(OccupancyGrid,NAMESPACE+'/global_costmap/costmap',lambda m:grids.append(m),10)
        # Derive a C4 transport-only overlay from D3's public config generator.
        # Its source and original config remain read-only; no controller starts.
        native=paths['d3']/'experiments/competition_nav2'; sys.path.insert(0,str(native))
        import configure
        base=configure.candidate('rpp')
        params={k:deepcopy(base[k]) for k in ('planner_server','global_costmap')}
        params['planner_server']['ros__parameters']['use_sim_time']=False
        cm=params['global_costmap']['global_costmap']['ros__parameters']
        cm['use_sim_time']=False; cm['static_layer']['map_topic']=NAMESPACE+'/map'
        cm['obstacle_layer']['observation_sources']='c4'
        cm['obstacle_layer'].pop('scan')
        cm['obstacle_layer']['footprint_clearing_enabled']=False
        cm['obstacle_layer']['c4']=dict(topic=TOPIC,data_type='PointCloud2',marking=True,clearing=False,
            min_obstacle_height=-1.,max_obstacle_height=3.,obstacle_max_range=7.9,raytrace_max_range=8.,
            observation_persistence=0.,expected_update_rate=base['global_costmap']['global_costmap']['ros__parameters']['obstacle_layer']['scan']['expected_update_rate'])
        parameter_file=output/'params.yaml'; parameter_file.write_text(yaml.safe_dump({NAMESPACE.strip('/'):params}))
        evidence['original_d3_config_sha256']=hashlib.sha256(json.dumps(base,sort_keys=True).encode()).hexdigest()
        evidence['c4_overlay_sha256']=hashlib.sha256(parameter_file.read_bytes()).hexdigest()
        log=(output/'planner.log').open('w')
        argv=[str(Path(get_package_prefix('nav2_planner'))/'lib/nav2_planner/planner_server'),
            '--ros-args','-r','__ns:='+NAMESPACE,'--params-file',str(parameter_file),
            '-r','/tf:='+NAMESPACE+'/tf','-r','/tf_static:='+NAMESPACE+'/tf_static']
        planner=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT)
        evidence['planner_argv']=argv
        async def service(kind,name,request):
            client=node.create_client(kind,name)
            try:
                await wait_for(lambda:client.service_is_ready(),name,15)
                future=client.call_async(request)
                await wait_for(future.done,name+' response',15)
                return future.result()
            finally: node.destroy_client(client)
        for transition in (Transition.TRANSITION_CONFIGURE,Transition.TRANSITION_ACTIVATE):
            request=ChangeState.Request(); request.transition.id=transition
            response=await service(ChangeState,NAMESPACE+'/planner_server/change_state',request)
            assert response.success, 'LIFECYCLE_REJECTED'
        state=await service(GetState,NAMESPACE+'/planner_server/get_state',GetState.Request())
        assert state.current_state.id==3
        await wait_for(lambda:grids,'native costmap')
        names=['obstacle_layer.observation_sources','obstacle_layer.c4.marking','obstacle_layer.c4.clearing',
               'footprint','resolution','obstacle_layer.c4.expected_update_rate']
        request=GetParameters.Request(); request.names=names
        response=await service(GetParameters,NAMESPACE+'/global_costmap/global_costmap/get_parameters',request)
        evidence['effective_parameters']={k:dict(type=v.type,string=v.string_value,bool=v.bool_value,double=v.double_value) for k,v in zip(names,response.values)}
        assert response.values[0].string_value=='c4' and response.values[1].bool_value and not response.values[2].bool_value
        assert response.values[-1].double_value==.3
        def send(points):
            msg=PointCloud2(); msg.header.frame_id='review_lidar'; msg.header.stamp=node.get_clock().now().to_msg()
            msg.height=1; msg.width=len(points); msg.point_step=12; msg.row_step=12*len(points)
            msg.fields=[PointField(name=n,offset=i*4,datatype=PointField.FLOAT32,count=1) for i,n in enumerate('xyz')]
            msg.data=b''.join(struct.pack('<fff',*p) for p in points); msg.is_dense=True
            sender.publish(msg)
        returns=[[(6.,4.,0.),(6.02,4.02,0.)]]  # Generated far boundary; empty route, not invented free rays.
        async def continuous():
            while True:
                send(returns[0])
                await asyncio.sleep(.08)
        pump=asyncio.create_task(continuous())
        await wait_for(lambda:marker.published>0,'initial actual marking input',5)
        action=ActionClient(node,ComputePathToPose,NAMESPACE+'/compute_path_to_pose')
        await wait_for(action.server_is_ready,'planner action')
        async def plan():
            goal=ComputePathToPose.Goal(); goal.planner_id='GridBased'; goal.use_start=True
            for pose,x in ((goal.start,0.),(goal.goal,4.)):
                pose.header.frame_id='map'; pose.header.stamp=node.get_clock().now().to_msg()
                pose.pose.position.x=x; pose.pose.orientation.w=1.
            future=action.send_goal_async(goal); await wait_for(future.done,'path goal')
            handle=future.result(); assert handle.accepted
            future=handle.get_result_async(); await wait_for(future.done,'path result')
            value=future.result(); assert value.status==4, 'PLANNER_NOT_SUCCEEDED:'+str(value.status)
            return [[p.pose.position.x,p.pose.position.y] for p in value.result.path.poses]
        initial=await plan(); assert len(initial)>1
        def cells():
            g=grids[-1]; indices=[]
            for i,v in enumerate(g.data):
                x=g.info.origin.position.x+(i%g.info.width+.5)*g.info.resolution
                y=g.info.origin.position.y+(i//g.info.width+.5)*g.info.resolution
                if v>=99 and 1.6<x<2.4 and abs(y)<.4: indices.append(i)
            return indices
        before=cells(); assert not before
        evidence['cases'].append(dict(name='empty_generated_lane',status='PASS',path_points=len(initial),lethal_cells=len(before)))
        obstacle=[(1.72+i*.04,-.28+j*.04,0.) for i in range(15) for j in range(15)]
        # Keep actual owner identity graph fresh. Three inputs exercise the
        # pre-viewport-throttle hook; receipt/source expiry never restarts.
        with server(adapter.scene) as url:
            previous=adapter.delivered; returns[0]=obstacle
            await wait_for(lambda:adapter.delivered>previous and adapter.latest
                and adapter.latest.work.message.width==len(obstacle),'actual obstacle C4 delivery',5)
            raw=await asyncio.to_thread(fetch,url)
            snapshot=json.loads(raw)
            assert snapshot['obstacle_frame'] and snapshot['collision_assessment'], adapter.health()
            (output/'http-snapshot.json').write_bytes(raw)
            evidence['HTTP']='PASS'; evidence['http_sha256']=hashlib.sha256(raw).hexdigest()
        await wait_for(lambda:cells(),'native marking',5)
        marked=cells(); changed=await plan()
        assert max(abs(p[1]) for p in changed)>max(abs(p[1]) for p in initial)+.15
        evidence.update(ROS='PASS',core='PASS',marking='PASS',planner='PASS')
        evidence['cases'].append(dict(name='obstacle_appears',status='PASS',lethal_cells=len(marked),
            before_path_max_y=max(abs(p[1]) for p in initial),after_path_max_y=max(abs(p[1]) for p in changed)))
        (output/'paths.json').write_text(json.dumps(dict(initial=initial,obstacle=changed)))
        (output/'costmap.json').write_text(json.dumps(dict(width=grids[-1].info.width,height=grids[-1].info.height,
            resolution=grids[-1].info.resolution,marked_indices=marked,data=list(grids[-1].data))))
        returns[0]=[(6.,4.,0.),(6.02,4.02,0.)]
        await asyncio.sleep(.6)
        retained=await plan()
        assert cells() and max(abs(p[1]) for p in retained)>.15
        evidence['cases'].append(dict(name='obstacle_returns_removed',status='NOT_PROVEN',
            reason='NO_ORIGINAL_FREE_RAY_EVIDENCE',retained_lethal_cells=len(cells()),
            path_max_y=max(abs(p[1]) for p in retained)))
        pump.cancel()
        try: await pump
        except asyncio.CancelledError: pass
        send([]); await asyncio.sleep(.6)
        assert cells(), 'UNSUPPORTED_CLEARING_OCCURRED'
        evidence['cases'].append(dict(name='empty_returns_after_obstacle',status='NOT_PROVEN',
            reason='NO_ORIGINAL_FREE_RAY_EVIDENCE',retained_lethal_cells=len(cells())))
        assert adapter.health()['stale']
        assert adapter.scene.snapshot()['obstacle_frame'] is None
        evidence['cases'].append(dict(name='sensor_loss',status='PASS',scene_expired=True,native_cells_retained=True))
        old=accepted[-2]; delivered=adapter.delivered
        hub.reset(input_topic)
        ctx=replace(adapter.context,runtime_generation=2,map_generation=1,map_revision='c'*64,
            source_epoch=hub.observation_identity.epoch,clock_epoch='clock-2',tf_epoch='tf-2')
        adapter.rebind(ctx,replace(mapping,source_epoch=ctx.source_epoch,clock_epoch=ctx.clock_epoch))
        assert not adapter.offer_raw(*old)
        assert adapter.scene.snapshot()['obstacle_frame'] is None
        assert adapter.delivered==delivered
        published=marker.published
        send(obstacle)
        await wait_for(lambda:adapter.delivered>delivered,'new source core delivery')
        assert marker.published==published and adapter.error=='NATIVE_CONTEXT_RESET_REQUIRED'
        evidence['cases'].append(dict(name='map_source_change_and_old_packet',status='PASS',
            late_rejected=True,scene_invalidated=True,new_core_generation_accepted=True,
            new_native_publication_blocked=True,native_costmap_generation='RESET_REQUIRED_NOT_REUSED'))
        evidence['adapter_health']=adapter.health(); evidence['callback_errors']=callback_errors
        assert not callback_errors,callback_errors
        evidence['accepted_ROS_messages']=len(accepted); evidence['raw_publications']=marker.published
        assert len(accepted)>=2 and marker.published>0
        evidence['status']='PASS_WITH_EXPLICIT_UNPROVEN_BOUNDARIES'
        node.destroy_subscription(subscription); node.destroy_subscription(cost_sub)
    except Exception as exc:
        evidence['status']='FAIL'; evidence['error']=type(exc).__name__+':'+str(exc)
        evidence['traceback']=traceback.format_exc()
        raise
    finally:
        (output/'summary.json').write_text(json.dumps(evidence,indent=2)+'\n')
        if pump: pump.cancel()
        if port: port.close()
        if adapter: await adapter.close()
        if planner:
            planner.terminate()
            try: planner.wait(5)
            except subprocess.TimeoutExpired: planner.kill(); planner.wait(5)
        if log: log.close()
        executor.shutdown(); ros_thread.join(5); node.destroy_node(); rclpy.shutdown()


if __name__=='__main__':
    output=Path(sys.argv[1]); output.mkdir(parents=True,exist_ok=True)
    asyncio.run(main(output))
