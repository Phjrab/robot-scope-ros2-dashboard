"""Loopback-only synthetic hardware + real C0 ASGI/UI; never a device server."""
import faulthandler,signal,os
faulthandler.enable()
faulthandler.register(signal.SIGUSR1,all_threads=True)
from source_guard import checked_root
REPO, SNAPSHOT_ID = checked_root()
import asyncio
import copy
import json
import socket
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import numpy as np
from robot_dashboard.application.anchor_proposal import imu_matrix
from robot_dashboard.api.routers.operational_navigation import router
from robot_dashboard.api.routers.fastlio_observation import router as observation_router
from robot_dashboard.application.global_observation import GlobalObservationCoordinator
from robot_dashboard.application.navigation_initialization_proposal import NavigationInitializationProposals
from robot_dashboard.relocalization.experimental_se3 import from_translation_rpy
from robot_dashboard.ros.observation_identity import ObservationIdentity
from test_observation_subscription_evidence import evidence, CLOUD_TYPE, POSE_TYPE
from test_navigation_proposal_handoff import ProposalHandoffTests
from test_navigation_initialization_proposal import ProposalTests
from synthetic_ambiguity import install_runner, draft_for_fixture

HERE=Path(__file__).resolve().parent
events=[]
fixture=None

def log_event(item):
    item={**item,'monotonic_ns':time.monotonic_ns()}
    events.append(item)
    directory=os.environ.get('PRIOR_OUTPUT_DIR')
    if directory:
        with (Path(directory)/'server-events.jsonl').open('a') as stream:stream.write(json.dumps(item)+'\n')

class Fixture:
    def __init__(self):
        self.case=ProposalHandoffTests(); self.case.setUp()
        self.source=ProposalTests(); self.source.setUp()
        self.solver_variant='one'; install_runner(self)
        self.manager=self.case.manager
        self.session=self.case.session
        self.runtime=self.source.runtime
        self.runtime.operational_navigation=self.manager
        self.runtime.fastlio_observation=self.session
        self.session.runtime=self.runtime
        self.case.case.calibration['T_nav_map_from_localization_map']=from_translation_rpy([2.,-.5,.7],[.12,-.08,.3]).tolist()
        self.case.case.calibration['T_imu_base']=from_translation_rpy([.25,-.1,.4],[.02,.03,-.15]).tolist()
        self.case.case.write_calibration()
        self.manager.select_pair(self.case.case.pair_fixture())
        self.session._status['started_monotonic_s']=time.monotonic()-.1
        self.owner=GlobalObservationCoordinator(self.case.case.catalog,self.runtime.agent,self.source.runner)
        self.runtime.global_observation=self.owner
        self.runtime._navigation_initialization_proposals=NavigationInitializationProposals(self.runtime)
        self.executor_calls=[]
        real_start=self.runtime._navigation_initialization_proposals.start
        def observed_start(*args,**kwargs):
            try:asyncio.get_running_loop();has_loop=True
            except RuntimeError:has_loop=False
            self.executor_calls.append({'operation':'proposal.start','thread_id':threading.get_ident(),'thread_name':threading.current_thread().name,'has_running_loop':has_loop})
            log_event({'executor_observation':self.executor_calls[-1]})
            return real_start(*args,**kwargs)
        self.runtime._navigation_initialization_proposals.start=observed_start
        self.runtime.navigation=SimpleNamespace(start_task=None,view=lambda:{'pipeline':{'state':'idle'},'session_mode':'idle'})
        self.patcher=patch('robot_dashboard.application.ownership_readback.ownership_readback',return_value={'busy_components':['fastlio_observation'],'unknown_components':[]})
        self.patcher.start()
        self.lock=threading.RLock(); self.stopped=threading.Event(); self.freeze=False; self.drop=False
        self.fail_status=False
        self.stamp=12345; self.pose_identity=ObservationIdentity(); self.cloud_identity=ObservationIdentity()
        self.original_pose=copy.deepcopy(self.runtime.agent.pose)
        self.original_cloud=copy.deepcopy(self.runtime.agent.cloud)
        self.emit()
        self.runtime.agent.pose_snapshot=lambda:self.sample('pose')
        self.runtime.agent.pointcloud_binary_snapshot=lambda:self.sample('cloud')
        self.runtime.agent.observation_pose_near=lambda observation,**kwargs:self.sample('pose')
        outer=self
        class Service:
            def status(self):return copy.deepcopy(outer.session._status)
            def dispatch(self,command):
                if command!='stop':raise RuntimeError('OFFLINE_START_FORBIDDEN')
                log_event({'fixture_service_dispatch':command,'dispatch_thread_id':threading.get_ident()})
                with outer.session._lock:
                    outer.session._status={'state':'STOPPED','active':False,'busy':False,'session_id':None,'job_pending':False}
        self.session.service=Service()
        self.thread=threading.Thread(target=self.pump,daemon=True);self.thread.start()
    def emit(self):
        with self.lock:
            self.stamp+=1;now=time.monotonic()
            for key,identity,typ,original in [('pose',self.pose_identity,POSE_TYPE,self.original_pose),('cloud',self.cloud_identity,CLOUD_TYPE,self.original_cloud)]:
                sample=copy.deepcopy(original)
                sample['observation']=identity.observe(topic=sample['topic'],frame='camera_init',stamp_ns=self.stamp,received=now,publisher_count=1,observation_context=evidence(sample['topic'],typ,at=now))
                setattr(self.runtime.agent,key,sample)
            with self.session._lock:self.session._updated_at=now
    def sample(self,key):
        with self.lock:return copy.deepcopy(getattr(self.runtime.agent,key))
    def pump(self):
        while not self.stopped.wait(.025):
            if not self.freeze:self.emit()
    def close(self):
        self.stopped.set();self.thread.join(2)
        if getattr(self,'mock_runtime',None):self.mock_runtime.close()
        self.manager.close_handoff_monitor();self.owner.close();self.patcher.stop()
        self.source.doCleanups();self.case.doCleanups()
    def context(self):
        state=self.manager.status(); pair=state['pair']; draft=draft_for_fixture(self,pair)
        return {'maps':[self.case.case.localization,self.case.case.navigation], 'map':self.case.case.navigation,
            'navigation':{'pipeline':{'state':'idle'},'goal':{'state':'idle'}}, 'synthetic':True, 'fixture_draft':draft,'snapshot_id':SNAPSHOT_ID}

@asynccontextmanager
async def lifespan(app):
    yield
    if fixture:await asyncio.to_thread(fixture.close)

app=FastAPI(lifespan=lifespan)
app.include_router(router);app.include_router(observation_router)

@app.middleware('http')
async def record(request,call_next):
    if request.url.path.startswith(('/api/','/__fixture/')):
        item={'method':request.method,'path':request.url.path,'asgi_thread_id':threading.get_ident()}
        if request.method=='POST':
            try:item['body']=await request.json()
            except ValueError:item['body']='INVALID_JSON'
        log_event(item)
        if fixture and fixture.fail_status and request.method=='GET' and request.url.path.endswith('/preparation-inputs'):
            fixture.fail_status=False;return JSONResponse({'detail':'SYNTHETIC_STATUS_READ_FAILURE'},status_code=503)
        if request.url.path.startswith('/api/') and request.method!='GET' and not (request.url.path.endswith('/initialization-proposals') or request.url.path.endswith('/confirm-geometry') or request.url.path.endswith('/fastlio/stop') or request.url.path.endswith('/operational-3d/match')):
            return JSONResponse({'detail':'OFFLINE_COMMAND_FORBIDDEN'},status_code=409)
    response=await call_next(request)
    if fixture and fixture.drop and request.url.path.endswith('/confirm-geometry') and response.status_code==200:
        fixture.drop=False
        return JSONResponse({'detail':'SYNTHETIC_RESPONSE_LOSS_AFTER_REAL_CONFIRM'},status_code=503)
    return response

@app.post('/__fixture/reset')
async def reset():
    global fixture
    if fixture:
        async with fixture.runtime.pipeline_coordination_lock:await asyncio.to_thread(fixture.close)
    events.clear();fixture=Fixture();app.state.runtime=fixture.runtime
    return await asyncio.to_thread(fixture.context)

@app.get('/__fixture/context')
async def context():
    async with fixture.runtime.pipeline_coordination_lock:
        return await asyncio.to_thread(fixture.context)

def collect_result(current):
    state=current.manager.status()
    with current.session._lock:
        receipts={key:current.session.handoff_receipt(key) for key in list(current.session._handoff_receipts)}
    return {'events':copy.deepcopy(events),'state':state,'executor_calls':copy.deepcopy(current.executor_calls),
        'stop_receipts':receipts,'synthetic_only':True,
        'proposals':{key:current.runtime._navigation_initialization_proposals.get(key) for key in list(current.runtime._navigation_initialization_proposals._records)},
        'solver_calls':current.source.runner.calls,'synthetic_observation':getattr(current,'synthetic_observation',None),
        'thread_ids':current.runner_thread_ids,'snapshot_id':SNAPSHOT_ID}

@app.get('/__fixture/result')
async def result():
    # Match the actual proposal HTTP boundary. Calling owner.get concurrently
    # with manager.confirm outside this lock manufactures a lock inversion.
    async with fixture.runtime.pipeline_coordination_lock:
        return await asyncio.to_thread(collect_result,fixture)

def apply_change(mode):
    if mode=='lose-confirm-response':fixture.drop=True
    elif mode=='odom-drift':
        fixture.original_pose['position']['x']+=.04;fixture.emit()
    elif mode=='odom-drift-server-policy':
        # Synthetic input only: align .18 m drift with the .08 m duplicate
        # separation in localization-map X. Projection preserves the duplicate
        # group while placing only its second member outside the .25 m policy.
        delta=imu_matrix(fixture.original_pose)[:3,:3] @ fixture.source.runner.pose[:3,:3].T @ np.array([.18,0.,0.])
        for axis,value in zip(('x','y','z'),delta):fixture.original_pose['position'][axis]+=float(value)
        log_event({'fixture_input':mode,'localization_delta_m':[.18,0.,0.],'odom_delta_m':delta.tolist()})
        fixture.emit()
    elif mode=='source-epoch':fixture.pose_identity=ObservationIdentity();fixture.emit()
    elif mode=='freeze-source':fixture.freeze=True
    elif mode=='reject-candidate':fixture.source.runner.override=True
    elif mode in ('one','zero','multiple','bad-quality','truncated','unique-in','unique-out','unknown-quality','missing-metadata','tampered-metadata','legacy','handoff-out','multiple-roll','duplicate-in','duplicate-bad-marker','duplicate-current-drift'):
        fixture.solver_variant=mode
    elif mode=='expire-prior':
        for record in fixture.runtime._navigation_initialization_proposals._records.values():
            if record.get('prior_anchor'):record['prior_anchor']['expires_monotonic_s']=time.monotonic()-1
    elif mode=='generation':fixture.manager.select_pair(fixture.case.case.pair_fixture())
    elif mode=='calibration':
        fixture.case.case.calibration['evidence']='CHANGED_SYNTHETIC_CALIBRATION';fixture.case.case.write_calibration()
    elif mode=='map-revision':fixture.case.case.pcd.write_bytes(fixture.case.case.pcd.read_bytes()+b'changed')
    elif mode=='session':fixture.session._status['session_id']='b'*32
    elif mode=='fail-next-status':fixture.fail_status=True
    else:return JSONResponse({'detail':'unknown fixture control'},status_code=400)
    return {'synthetic':mode}

@app.post('/__fixture/change/{mode}')
async def change(mode):
    async with fixture.runtime.pipeline_coordination_lock:
        return await asyncio.to_thread(apply_change,mode)

@app.get('/exercise')
async def exercise():
    return HTMLResponse('''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/styles.css">
<h1>OFFLINE SYNTHETIC — 실장비 아님</h1><label>3D 위치추정 지도<select id="cloud"></select></label><label>2D 경로 지도<select id="grid"></select></label><article id="host"></article>
<script type="module">
import {initializeNavigationPreparation} from '/features/navigation/preparation.js';
const ctx=await (await fetch('/__fixture/context')).json();window.actions=[];window.fixtureDraft=structuredClone(ctx.fixture_draft);
window.changeFixtureDraft=(patch)=>{window.fixtureDraft={...window.fixtureDraft,...patch};window.preparation.draftChanged();};
const grid=document.querySelector('#grid');grid.add(new Option(ctx.map.name,ctx.map.id));
window.preparation=initializeNavigationPreparation({host:document.querySelector('#host'),map3dSelect:document.querySelector('#cloud'),map2dSelect:grid,
api:async(path,options={})=>{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});const v=await response.json();if(!response.ok)throw new Error(v.detail);return v;},
context:()=>ctx,onChange:()=>{},getOperatorDraft:()=>window.fixtureDraft,actions:Object.fromEntries(['start','initial','goal','refresh'].map(key=>[key,()=>window.actions.push(key)]))});
window.preparation.render();await window.preparation.refresh(true);window.mounted=true;
</script>''')

from mock_runtime import install as install_mock_runtime
install_mock_runtime(app,lambda:fixture,events)
@app.get('/')
async def full_app():return HTMLResponse((REPO/'robot_dashboard/static/index.html').read_text())
app.mount('/static',StaticFiles(directory=REPO/'robot_dashboard/static'),name='app-static')
app.mount('/',StaticFiles(directory=REPO/'robot_dashboard/static'),name='static')

if __name__=='__main__':
    original_connect=socket.socket.connect
    def loopback_only(sock,address):
        if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
            raise RuntimeError('OFFLINE_EXTERNAL_CONNECT_FORBIDDEN')
        return original_connect(sock,address)
    def no_process(*args,**kwargs):raise RuntimeError('OFFLINE_SUBPROCESS_FORBIDDEN')
    socket.socket.connect=loopback_only;subprocess.Popen=no_process
    uvicorn.run(app,host='127.0.0.1',port=4397,log_level='warning')
