"""Exercise the real launcher's cleanup functions with isolated Linux children."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(sys.platform == 'linux', 'requires Linux process sessions and /proc')
class OrphanCleanupTests(unittest.TestCase):
    def test_reaped_leader_does_not_hide_live_child(self):
        source = (Path(__file__).resolve().parents[1] / 'scripts/start_wireless_mapping_humble.sh').read_text()
        functions = source[source.index('process_identity()'):source.index('remote_lifecycle()')]
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / 'ready'
            leader = subprocess.Popen([sys.executable, '-c',
                'import os,signal,time,sys; '
                'signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); '
                'pid=os.fork(); '
                'signal.signal(signal.SIGINT, signal.SIG_IGN) if pid == 0 else None; '
                'open(sys.argv[1], "w").write(str(os.getpid())) if pid == 0 else None; '
                'time.sleep(60)', str(ready)], start_new_session=True)
            try:
                identity = Path(f'/proc/{leader.pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists())
                os.kill(leader.pid, signal.SIGINT)
                leader.wait(timeout=5)
                command = functions + '\n' + f'''
LOCAL_PIDS=({leader.pid})
LOCAL_IDENTITIES=({identity})
local_group_alive 0 || exit 10
LOCAL_IDENTITIES=($(({identity} + 1000000000)))
local_group_alive 0 && exit 11
LOCAL_IDENTITIES=({identity})
stop_local_children TERM
wait_local_children 1 || {{ stop_local_children KILL; wait_local_children 1; }}
'''
                result = subprocess.run(['bash', '-c', command], capture_output=True, text=True, timeout=8)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                try:
                    os.killpg(leader.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                leader.wait(timeout=5)
