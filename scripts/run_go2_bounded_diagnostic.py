#!/usr/bin/env python3
"""Repair of the 2026-11-15 field probe. Default: offline plan, no ROS/network.

Live mode requires fresh explicit supervision flags. Fixed 0.20 m/s, 3 seconds,
0.15 m displacement, .30 s sample age, .15 rad tilt-change bounds; dashboard
watchdogs and native safety policy are unchanged. Vendor position is diagnostic
evidence, not physical travel truth. Never automatically retries or rearms.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import threading
import time
import urllib.request

from field_trial_evidence import Journal, json_value, stop_and_finalize, write_json

ORIGIN = 'http://127.0.0.1:8088'


class DiagnosticError(RuntimeError):
    """Fixed diagnostic reason safe for the local evidence file."""


def call(path, body=None):
    request = urllib.request.Request(ORIGIN + '/api/v1/' + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        headers={'Origin': ORIGIN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


class Samples:
    def __init__(self, journal):
        self.journal = journal
        self.latest = None
        self.error = None
        self.phase = 'settle'
        self.lock = threading.Lock()

    def observe(self, message):
        try:
            row = json_value({'t': time.monotonic(), 'phase': self.phase,
                'position': list(message.position), 'velocity': list(message.velocity),
                'rpy': list(message.imu_state.rpy)})
            if any(len(row[key]) != 3 for key in ('position', 'velocity', 'rpy')):
                raise DiagnosticError('invalid vector length')
            self.journal.append(row)
            with self.lock:
                self.latest = row
        except Exception as exc:
            with self.lock:
                self.error = type(exc).__name__

    def current(self, max_age=.30):
        with self.lock:
            if self.error:
                raise DiagnosticError('telemetry/log failure: ' + self.error)
            if self.latest is None or not 0 <= time.monotonic() - self.latest['t'] < max_age:
                raise DiagnosticError('motion telemetry stale')
            return self.latest


def manual_preflight(control, navigation):
    c = control['control']
    if c['estop_latched'] is not True or c['lease']['active'] is not False:
        raise DiagnosticError('manual probe requires STOP and no existing lease')
    if c['command']['deadman'] is not False or any(c['command'][k] != 0 for k in ('linear_x', 'linear_y', 'angular_z')):
        raise DiagnosticError('manual probe requires zero command')
    if navigation['pipeline']['state'] != 'idle' or navigation['goal']['state'] == 'active':
        raise DiagnosticError('manual probe requires idle navigation')


async def drive(samples, sent, state):
    import websockets
    state['stage'] = 'preflight'
    c, n = await asyncio.gather(asyncio.to_thread(call, 'control'), asyncio.to_thread(call, 'navigation'))
    state['preflight'] = {'control': c, 'navigation': n}
    manual_preflight(c, n)
    origin = samples.current(.2)
    # Once a mutation is attempted, every exit must request software STOP.
    state['stage'] = 'clear_stop_and_arm'
    state['control_attempted'] = True
    await asyncio.to_thread(call, 'control/estop/clear', {'confirmed': True})
    armed = await asyncio.to_thread(call, 'control/arm', {'input_source': 'keyboard'})
    token = armed['lease_id']  # never written to evidence
    limit = armed['control']['limits']['max_linear_x']
    if not isinstance(limit, (int, float)) or isinstance(limit, bool) or not math.isfinite(limit) or limit < .2:
        raise DiagnosticError('existing speed cap does not permit this fixed comparison')
    state['stage'] = 'bind_control'
    seq = 0
    async with websockets.connect(ORIGIN.replace('http:', 'ws:') + '/api/v1/ws/control', origin=ORIGIN) as ws:
        await ws.send(json.dumps({'type': 'bind', 'lease_id': token, 'client_time_ms': time.time()*1000}))
        ack = json.loads(await asyncio.wait_for(ws.recv(), 2))
        if ack.get('type') != 'bound':
            raise DiagnosticError('control bind failed')
        failure = []

        async def read_errors():
            try:
                async for raw in ws:
                    if json.loads(raw).get('type') == 'error':
                        failure.append('server rejected control')
                        return
                failure.append('control stream closed')
            except Exception:
                failure.append('control stream failed')

        receiver = asyncio.create_task(read_errors())
        try:
            for label, velocity, duration in [('settle', 0., 1.), ('v020', .2, 3.), ('settle', 0., 1.)]:
                state['stage'] = label
                samples.phase = label
                end, heartbeat = time.monotonic() + duration, 0.
                while time.monotonic() < end:
                    row = samples.current()
                    if failure:
                        raise DiagnosticError(failure[0])
                    if math.dist(row['position'][:2], origin['position'][:2]) >= .15:
                        return 'displacement_bound'
                    if max(abs(row['rpy'][i] - origin['rpy'][i]) for i in (0, 1)) > .15:
                        return 'tilt_change_bound'
                    seq += 1
                    await ws.send(json.dumps({'type': 'twist', 'lease_id': token, 'seq': seq,
                        'source': 'keyboard', 'deadman': velocity != 0., 'linear_x': velocity/limit,
                        'linear_y': 0., 'angular_z': 0., 'speed_scale': 1., 'client_time_ms': time.time()*1000}))
                    sent.append({'t': time.monotonic(), 'velocity': velocity})
                    now = time.monotonic()
                    if now - heartbeat > .4:
                        seq += 1
                        await ws.send(json.dumps({'type': 'heartbeat', 'lease_id': token,
                            'seq': seq, 'client_time_ms': time.time()*1000}))
                        heartbeat = now
                    await asyncio.sleep(.05)
            return 'time_bound'
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)


def live(output):
    # Imports and all device access occur only after explicit CLI admission.
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from unitree_go.msg import SportModeState
    output.mkdir(parents=True, exist_ok=False)
    journal = Journal(output / 'motion.jsonl')
    samples, done = Samples(journal), threading.Event()
    sent, state = [], {'control_attempted': False}
    node = thread = None
    initialized = False
    end = {'reason': 'startup_failed'}

    def stop_observer():
        done.set()
        if thread is not None:
            thread.join(2)
            if thread.is_alive():
                raise DiagnosticError('ROS observer did not stop')

    def destroy_node():
        if thread is not None and thread.is_alive():
            raise DiagnosticError('observer still using ROS node')
        if node is not None:
            node.destroy_node()

    def shutdown_ros():
        if initialized:
            rclpy.shutdown()

    def spin():
        try:
            while not done.is_set():
                rclpy.spin_once(node, timeout_sec=.03)
        except Exception as exc:
            samples.error = type(exc).__name__

    try:
        write_json(output / 'started.json', {'schema': 1, 'wall_time_ns': time.time_ns(),
            'velocity_mps': .2, 'drive_seconds': 3., 'max_displacement_m': .15})
        rclpy.init()
        initialized = True
        node = rclpy.create_node('robot_scope_bounded_probe_observer')
        node.create_subscription(SportModeState, '/sportmodestate', samples.observe,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        thread = threading.Thread(target=spin, daemon=True)
        thread.start()
        time.sleep(1)
        end = {'reason': asyncio.run(drive(samples, sent, state))}
    except (Exception, KeyboardInterrupt) as exc:
        # Exception text can contain transport details/tokens. Retain type only.
        end = {'reason': 'trial_error', 'error_type': type(exc).__name__,
               'stage': state.get('stage', 'startup'),
               'detail': str(exc) if isinstance(exc, DiagnosticError) else 'external failure; details omitted'}
    finally:
        cleanup = [('observer_stop', stop_observer), ('node_destroy', destroy_node),
                   ('ros_shutdown', shutdown_ros), ('journal_close', journal.close)]
        if state['control_attempted']:
            result = stop_and_finalize(
                lambda: call('control/stop', {'reason': 'bounded diagnostic ended'}),
                lambda: call('control'), cleanup,
                [(output / 'end.json', end), (output / 'sent.json', sent),
                 (output / 'preflight.json', state.get('preflight'))])
        else:
            result = {'control_attempted': False, 'errors': []}
            for name, action in [*cleanup,
                                 ('end.json', lambda: write_json(output / 'end.json', end)),
                                 ('preflight.json', lambda: write_json(output / 'preflight.json', state.get('preflight')))]:
                try:
                    action()
                except Exception as exc:
                    result['errors'].append(name + ':' + type(exc).__name__)
        try:
            write_json(output / 'final.json', result)
        except Exception as exc:
            result['errors'].append('final.json:' + type(exc).__name__)
        print(json.dumps({'output': str(output), 'end': end, 'stop_confirmed': result.get('stop_confirmed'),
                          'errors': result['errors']}))
    return 0 if result.get('stop_confirmed') and not result['errors'] and end['reason'] in ('time_bound', 'displacement_bound') else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-stopped', action='store_true')
    parser.add_argument('--confirm-supervision', action='store_true')
    parser.add_argument('--confirm-corridor-clear', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print('OFFLINE PLAN ONLY: fixed 0.20 m/s, 3 s, 0.15 m bound; no ROS/network access')
        return 0
    if not all((args.confirm_stopped, args.confirm_supervision, args.confirm_corridor_clear, args.output)):
        parser.error('live execution requires fresh stopped/supervision/corridor confirmations and a new output path')
    if sys.platform != 'linux':
        parser.error('live execution requires the robot Linux/ROS environment')
    return live(args.output)


if __name__ == '__main__':
    raise SystemExit(main())
