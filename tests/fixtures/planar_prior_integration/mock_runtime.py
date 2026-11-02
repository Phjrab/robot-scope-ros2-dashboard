"""Explicit synthetic Nav2/ROS boundary with real manager/localizer/receipt gates.

No navigation coordinator start, ROS callback, publisher, or Nav2 node runs.
The HTTP INITIAL POSE bridge and receipt transport are synthetic. The manager
candidate check, localizer reseed/start_matching and receipt waiters are real.
"""
import asyncio,copy,time
import numpy as np
from fastapi import Request
from fastapi.responses import JSONResponse
from robot_dashboard.relocalization.operational import load_bundle
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.ros.initial_pose_receipt import operational_initial_pose_context,wait_initial_pose_receipt,wait_match_receipt

class MockRuntime:
    def __init__(self,fixture,events):
        self.f=fixture;self.events=events;self.engine=None;self.view_state={'pipeline':{'state':'idle'},'goal':{'state':'idle'}}
    def close(self):
        if self.engine:self.engine.close()
    def health(self,*_):
        if not self.engine:return {}
        self.engine.last_pose_receipt=time.monotonic()
        source=copy.deepcopy(self.engine.status());source.update(runtime_instance_generation=self.instance,fresh=True)
        for name in ('accepted_initial_pose','estimated_pose'):
            if source.get(name):source[name]['runtime_instance_generation']=self.instance
        return {'fresh':True,'age_s':0.,'process_generation':123,'runtime_instance_generation':self.instance,'operational_3d':source}
    def start(self):
        f=self.f;pair=f.manager.status()['pair'];nav=pair['navigation_2d']
        f.manager.preflight(nav['map_id'],nav['revision'])
        directory=f.case.case.job_directory()
        f.manager.snapshot_for_job(nav['map_id'],nav['revision'],directory)
        self.engine=load_bundle(directory/'nav2_params.yaml')
        assert self.engine.seed is None and self.engine.correction is None
        self.engine.current_odom=np.eye(4);self.engine.stopped_since=time.monotonic()-3;self.engine.last_pose_receipt=time.monotonic()
        self.instance=f'123:{time.monotonic_ns()}'
        self.view_state={'pipeline':{'state':'running','job_id':directory.name},'map':{'id':nav['map_id'],'revision':nav['revision']},'goal':{'state':'idle'},'localization_session':{'active':False}}
        f.case.case.jobs.snapshot=lambda:copy.deepcopy(self.view_state)
        f.runtime.navigation.view=lambda:copy.deepcopy(self.view_state)
        f.runtime.agent._navigation_runtime_health_snapshot=self.health
        f.runtime.agent.navigation_start_operational_match=self.match
        self.events.append({'fixture_boundary':'MOCK_NAV2_START','job_id':directory.name})
        return self.state()
    def state(self):
        return {**copy.deepcopy(self.view_state),'operational_localization':self.health().get('operational_3d')}
    def initial(self,body):
        if not self.engine:raise ValueError('MOCK_RUNTIME_REQUIRED')
        f=self.f;pose=body['pose'];nav=self.view_state['map']
        if (body['map_id'],body['map_revision'])!=(nav['id'],nav['revision']):raise ValueError('MAP_CHANGED')
        f.manager.check_initial_pose(nav['id'],nav['revision'],pose)
        context=operational_initial_pose_context(self.health())
        self.engine.reseed(from_translation_rpy([pose['x'],pose['y'],0.],[0.,0.,pose['yaw']]),stamp_ns=123)
        self.engine.initial_pose_receipt={'accepted':True,'stamp_ns':'123','reason':'WAITING_EXPLICIT_MAP_MATCH','localization_generation':self.engine.generation}
        wait_initial_pose_receipt(self.health,context,123)
        self.events.append({'fixture_boundary':'SYNTHETIC_INITIALPOSE_TRANSPORT','body':copy.deepcopy(body),'real_reseed':True,'real_receipt_waiter':True})
        return {'accepted':True,'navigation':self.state()}
    def match(self,**body):
        source=self.health()['operational_3d']
        for key in ('map_id','map_revision','bundle_generation','localization_generation'):
            if body[key]!=source[key]:raise ValueError('MOCK_MATCH_CONTEXT_CHANGED')
        context=operational_initial_pose_context(self.health())
        self.engine.start_matching(body['initial_pose_stamp_ns'])
        self.engine.match_receipt={'accepted':True,'request_id':'synthetic-match-1','localization_generation':self.engine.generation,'reason':'WAITING_MAP_CORRECTION'}
        receipt=wait_match_receipt(self.health,context,'synthetic-match-1',self.engine.generation)
        self.events.append({'fixture_boundary':'SYNTHETIC_MATCH_TRANSPORT','body':copy.deepcopy(body),'real_start_matching':True,'real_receipt_waiter':True})
        return receipt

def install(app,get_fixture,events):
    @app.post('/__fixture/mock-nav2/start')
    async def start():
        f=get_fixture();f.mock_runtime=MockRuntime(f,events)
        try:
            async with f.runtime.pipeline_coordination_lock:return await asyncio.to_thread(f.mock_runtime.start)
        except ValueError as e:return JSONResponse({'detail':str(e)},status_code=409)
    @app.get('/__fixture/mock-nav2/state')
    async def state():return get_fixture().mock_runtime.state()
    @app.post('/__fixture/mock-nav2/initial-pose')
    async def initial(request:Request):
        body=await request.json()
        try:
            f=get_fixture()
            async with f.runtime.pipeline_coordination_lock:return await asyncio.to_thread(f.mock_runtime.initial,body)
        except ValueError as e:return JSONResponse({'detail':str(e)},status_code=409)
