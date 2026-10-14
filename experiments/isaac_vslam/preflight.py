#!/usr/bin/env python3
"""Passive Linux inventory. Never opens a camera, joins ROS or changes the host."""
import datetime
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess

SAFE_ENV = {'ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY', 'RMW_IMPLEMENTATION',
            'CYCLONEDDS_URI', 'ROS_DISTRO', 'ROBOT_SCOPE_MAPPING_PROFILE'}


def command(args, timeout=15):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'status': 'NOT_OBSERVED', 'reason': str(e)}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def process_inventory():
    rows = []
    denied = 0
    for p in Path('/proc').glob('[0-9]*'):
        try:
            env = dict(item.split('=', 1) for item in (p / 'environ').read_bytes()
                       .decode(errors='replace').split('\0') if '=' in item)
        except OSError:
            env = {}
            denied += 1
        devices = []
        try:
            for fd in (p / 'fd').iterdir():
                try:
                    target = os.readlink(fd)
                    if target.startswith(('/dev/video', '/dev/bus/usb', '/dev/hidraw')):
                        devices.append(target)
                except OSError:
                    pass
        except OSError:
            pass
        safe = {k: v for k, v in env.items() if k in SAFE_ENV}
        comm = read(p / 'comm')
        if safe or devices or (comm and any(x in comm for x in
                ('python', 'docker', 'colcon', 'ninja', 'cc1', 'fastlio', 'laser', 'record'))):
            try:
                cwd = os.readlink(p / 'cwd')
                # Only executable and script argument; never dump command lines/secrets.
                args = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
                executable = args[0]
                script = next((a for a in args[1:3] if a.endswith('.py')), None)
            except OSError:
                cwd = executable = script = None
            rows.append({'pid': int(p.name), 'comm': comm, 'cwd': cwd,
                         'executable': executable, 'script': script,
                         'safe_environment': safe, 'open_devices': sorted(set(devices))})
    return {'processes': rows, 'unreadable_environments': denied,
            'scope': 'Permission-limited observation; empty device list is not proof of vacancy.'}


def main():
    out = {'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'host': os.uname().nodename, 'platform': list(os.uname()),
           'os': read('/etc/os-release'), 'l4t': read('/etc/nv_tegra_release'),
           'meminfo': read('/proc/meminfo'), 'cpu_online': read('/sys/devices/system/cpu/online'),
           'loadavg': read('/proc/loadavg'), 'processes': process_inventory()}
    disk = shutil.disk_usage('/home')
    out['disk'] = dict(zip(('total', 'used', 'free'), disk))
    out['space_floor_bytes'] = max(10 * 1024**3, disk.total // 10)
    out['space_gate'] = disk.free >= out['space_floor_bytes']
    out['usb'] = [{k: read(p / k) for k in ('product', 'manufacturer', 'serial', 'speed',
                                         'idVendor', 'idProduct', 'busnum', 'devnum')}
                  for p in Path('/sys/bus/usb/devices').glob('*') if (p / 'idVendor').exists()]
    out['thermal'] = [{'type': read(p / 'type'), 'millidegrees_c': read(p / 'temp')}
                      for p in Path('/sys/class/thermal').glob('thermal_zone*')]
    commands = {
        'packages': ['dpkg-query', '-W', '-f=${db:Status-Abbrev}\t${Package}\t${Version}\n',
                     'nvidia-l4t-*', 'cuda-*', 'libcud*', 'nvidia-container*',
                     'docker*', '*realsense*'],
        'docker': ['docker', 'info', '--format',
                   'version={{.ServerVersion}} runtime_names={{range $k,$v := .Runtimes}}{{$k}} {{end}} default={{.DefaultRuntime}}'],
        'containers': ['docker', 'ps', '-a', '--format', '{{.ID}} {{.Names}} {{.Image}} {{.Status}}'],
        'images': ['docker', 'image', 'ls', '--digests', '--no-trunc'],
        'power_mode': ['nvpmodel', '-q'],
        'nics': ['ip', '-br', 'addr'],
        'usb_tree': ['lsusb', '-t'],
        'services': ['systemctl', 'show', 'robot-scope.service',
                     'robot-scope-realsense-camera.service', 'robot-scope-control-bridge.service',
                     'enable-typec-host.service', '-p', 'Id', '-p', 'MainPID', '-p', 'NRestarts',
                     '-p', 'ActiveState', '-p', 'InvocationID'],
        'cpu': ['ps', '-eo', 'pid,ppid,user,pcpu,pmem,comm', '--sort=-pcpu'],
        'udp_sockets': ['ss', '-ulnp'],
    }
    out['commands'] = {k: command(v) for k, v in commands.items()}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
