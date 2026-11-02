"""Execute the real bridge entry point with no ROS or robot command transport."""
import ast
import os
import signal
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


def bridge_main():
    source = Path(__file__).resolve().parents[1] / 'robot_dashboard/go2_control_bridge.py'
    tree = ast.parse(source.read_text())
    entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    return compile(ast.Module(body=[entry], type_ignores=[]), str(source), 'exec')


class BridgeShutdownTests(unittest.TestCase):
    def run_entry(self, *, signal_during_init=False, spin_failure=False):
        events, handlers = [], {}
        state = {'alive': True, 'spin_count': 0, 'signal_exceptions': 0}

        def receive_signals():
            for signum in (signal.SIGINT, signal.SIGTERM):
                try:
                    handlers[signum](signum, None)
                except BaseException:
                    # CPython finalizers can swallow exceptions from a signal
                    # handler. The enclosing spin must still observe shutdown.
                    state['signal_exceptions'] += 1

        def install_signal(signum, handler):
            previous = handlers.get(signum, signal.SIG_DFL)
            handlers[signum] = handler
            return previous

        class Node:
            def __init__(self, *args, **kwargs):
                events.append('node_init')
                if signal_during_init:
                    receive_signals()

            def stop_safely(self):
                self.assert_context()
                events.append('stop_safely')

            def assert_context(self):
                if not state['alive']:
                    raise AssertionError('StopMove lost its ROS context')

            def destroy_node(self):
                events.append('destroy_node')

        class Executor:
            def __init__(self, **kwargs):
                pass

            def add_node(self, node):
                pass

            def spin(self):
                receive_signals()
                raise RuntimeError('unbounded spin continued after swallowed signal')

            def spin_once(self, *, timeout_sec):
                if timeout_sec > .1:
                    raise AssertionError('shutdown polling exceeded its bound')
                state['spin_count'] += 1
                if spin_failure:
                    raise RuntimeError('executor failure')
                receive_signals()

            def shutdown(self, *, timeout_sec):
                events.append('executor_shutdown')

        def context_shutdown():
            state['alive'] = False
            events.append('context_shutdown')

        namespace = dict(
            Any=Any, os=os,
            signal=SimpleNamespace(signal=install_signal, SIGINT=signal.SIGINT, SIGTERM=signal.SIGTERM),
            parse_args=lambda: SimpleNamespace(profile='unused', observation_only=False),
            load_profile=lambda _: {'control': {'enabled': True}},
            shared_key=lambda _: b'x' * 32,
            acquire_process_lock=lambda: SimpleNamespace(close=lambda: events.append('lock_closed')),
            control_transport_mode=lambda _: 'ros', CONTROL_TRANSPORT_ROS='ros', CONTROL_TRANSPORT_UDP='udp',
            ControlProtocolError=ValueError, ControlDatagramError=ValueError,
            SignalHandlerOptions=SimpleNamespace(NO=0),
            rclpy=SimpleNamespace(init=lambda **kw: None, ok=lambda: state['alive'], shutdown=context_shutdown),
            Go2ControlBridge=Node, MultiThreadedExecutor=Executor,
        )
        exec(bridge_main(), namespace)
        with patch.dict(os.environ, {'ROBOT_SCOPE_CONTROL_ENABLED': '1'}):
            if spin_failure:
                with self.assertRaisesRegex(RuntimeError, 'executor failure'):
                    namespace['main']()
            else:
                namespace['main']()
        self.assertEqual(events[-5:], [
            'stop_safely', 'executor_shutdown', 'destroy_node', 'context_shutdown', 'lock_closed',
        ])
        self.assertEqual(state['signal_exceptions'], 0)
        self.assertEqual(handlers[signal.SIGINT], signal.SIG_DFL)
        self.assertEqual(handlers[signal.SIGTERM], signal.SIG_DFL)
        return state

    def test_signal_inside_finalizer_boundary_leaves_spin_and_preserves_final_stop(self):
        self.assertEqual(self.run_entry()['spin_count'], 1)

    def test_signal_during_node_construction_does_not_enter_spin(self):
        self.assertEqual(self.run_entry(signal_during_init=True)['spin_count'], 0)

    def test_executor_failure_still_drains_stop_and_releases_ownership(self):
        self.run_entry(spin_failure=True)
