#!/usr/bin/env python3
"""Read-only onboard host inventory and bounded stationary workload sampling.

Reports contain selected facts, never environment dumps or process arguments.
Unavailable GPU/BSP observations remain null/NOT_RUN; Ubuntu alone does not
establish JetPack compatibility. This tool does not start workloads or services.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA = "robot-scope.onboard-diagnostics"
PACKAGE_PATTERNS = ("nvidia-l4t-*", "nvidia-jetpack", "cuda-*", "libnvinfer*", "tensorrt*", "libcudnn*")
SERVICE_PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "MainPID", "NRestarts", "User")
FIXED_SERVICES = ("robot-scope.service", "robot-scope-control-bridge.service", "robot-scope-realsense-camera.service")
MODULES = ("numpy", "rclpy", "cv2", "tensorrt", "pyrealsense2")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path, limit: int = 65536) -> str | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return None
        return raw.decode("utf-8", errors="replace").replace("\x00", " ").strip()
    except OSError:
        return None


def numeric(path: Path) -> float | None:
    try:
        value = float(read_text(path) or "")
        return value if value == value and abs(value) != float("inf") else None
    except ValueError:
        return None


def probe(command: Sequence[str], runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    try:
        result = runner(list(command), capture_output=True, text=True, timeout=8, check=False)
        return {"status": "PASS" if result.returncode == 0 else "NOT_RUN", "exit_code": result.returncode,
                "output": result.stdout[:65536] if result.returncode == 0 else ""}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "NOT_RUN", "reason": type(exc).__name__, "output": ""}


def python_modules() -> dict[str, Any]:
    values: dict[str, Any] = {"executable": sys.executable, "version": platform.python_version()}
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            values[name] = {"status": "PASS", "path": getattr(module, "__file__", None),
                            "version": str(getattr(module, "__version__", "unreported"))[:120]}
        except Exception as exc:
            # Import errors often include environment/search-path text. Keep
            # only their type, while recording the interpreter that was used.
            values[name] = {"status": "NOT_RUN", "reason": type(exc).__name__}
    return values


def resource_snapshot(*, root: Path = Path("/"), disk_path: Path | None = None) -> dict[str, Any]:
    memory: dict[str, int] = {}
    for line in (read_text(root / "proc/meminfo") or "").splitlines():
        match = re.fullmatch(r"(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB", line)
        if match:
            memory[match[1]] = int(match[2]) * 1024
    cpu_line = next((line for line in (read_text(root / "proc/stat") or "").splitlines() if line.startswith("cpu ")), "")
    try:
        ticks = [int(value) for value in cpu_line.split()[1:9]]
        cpu = {"total": sum(ticks), "idle": ticks[3] + ticks[4]} if len(ticks) == 8 else None
    except ValueError:
        cpu = None
    temperatures = []
    for zone in sorted((root / "sys/class/thermal").glob("thermal_zone*")):
        raw = numeric(zone / "temp")
        if raw is not None and -50000 <= raw <= 150000:
            temperatures.append({"sensor": read_text(zone / "type", 256) or zone.name, "celsius": raw / 1000})
    gpu_paths = [root / "sys/devices" / path / "load" for path in (
        "gpu.0", "17000000.gpu", "platform/gpu.0", "platform/17000000.gpu", "platform/bus@0/17000000.gpu")]
    gpu_paths.extend(sorted((root / "sys/class/devfreq").glob("*gpu*/load")))
    gpu_load = next((value for path in gpu_paths if (value := numeric(path)) is not None and 0 <= value <= 1000), None)
    oom = None
    for line in (read_text(root / "proc/vmstat") or "").splitlines():
        if re.fullmatch(r"oom_kill \d+", line):
            oom = int(line.split()[1])
    try:
        disk = shutil.disk_usage(disk_path or root)
        disk_value = {"total_bytes": disk.total, "free_bytes": disk.free}
    except OSError:
        disk_value = None
    return {"timestamp": timestamp(), "memory_bytes": memory, "cpu_ticks": cpu,
            "gpu_percent": None if gpu_load is None else gpu_load / 10,
            "temperatures": temperatures, "disk": disk_value, "oom_kill_count": oom}


def snapshot(*, root: Path = Path("/"), runner: Callable[..., Any] = subprocess.run,
             disk_path: Path | None = None, include_imports: bool = True) -> dict[str, Any]:
    os_values = {}
    for line in (read_text(root / "etc/os-release") or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"ID", "VERSION_ID", "PRETTY_NAME"}:
            os_values[key] = value.strip('"')
    # dpkg-query returns 1 when a requested optional glob has no match, even
    # while other package observations succeeded. Retain only validated rows.
    try:
        result = runner(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${db:Status-Status}\n", *PACKAGE_PATTERNS],
                        capture_output=True, text=True, timeout=8, check=False)
        rows = [line for line in result.stdout[:65536].splitlines()
                if re.fullmatch(r"[a-z0-9][a-z0-9+.:_-]*\t[^\s]{1,160}\tinstalled", line)]
        packages = {"status": "PASS" if rows else "NOT_RUN", "installed": rows,
                    "missing_optional_packages_do_not_establish_platform_failure": True}
    except (OSError, subprocess.SubprocessError):
        packages = {"status": "NOT_RUN", "installed": []}
    services = probe(["systemctl", "show", *FIXED_SERVICES,
                      *(f"--property={name}" for name in SERVICE_PROPERTIES)], runner)
    manufacturers = probe(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"], runner)
    units = [line.split()[0] for line in manufacturers.pop("output", "").splitlines()
             if line.split() and re.search(r"unitree|sport|dog|robot|hesai|realsense|dds|camera", line, re.I)]
    manufacturers["units"] = units[:128]
    processes = probe(["ps", "-eo", "user=,pid=,comm="], runner)
    processes["output"] = "\n".join(
        line for line in processes["output"].splitlines()
        if re.search(r"unitree|sport|dog|robot|hesai|realsense|dds|camera|fast.?lio|lio_mapping|AiServer|gstreamer", line, re.I)
    )[:65536]
    usb = []
    for device in sorted((root / "sys/bus/usb/devices").glob("*")):
        vendor, product = read_text(device / "idVendor", 16), read_text(device / "idProduct", 16)
        if vendor and product:
            usb.append({"device": device.name, "vendor_id": vendor, "product_id": product,
                        "manufacturer": read_text(device / "manufacturer", 256),
                        "product": read_text(device / "product", 256),
                        "serial": read_text(device / "serial", 256)})
    video_ids = [{"path": str(path), "target": str(path.resolve())}
                 for path in sorted((root / "dev/v4l/by-id").glob("*"))][:64]
    return {"schema": SCHEMA, "schema_version": 1, "generated_at": timestamp(), "hardware_side_effects": False,
            "platform": {"hostname": socket.gethostname(), "architecture": platform.machine(),
                         "kernel": platform.release(), "ubuntu": os_values,
                         "l4t_release": read_text(root / "etc/nv_tegra_release", 4096),
                         "device_tree_model": read_text(root / "proc/device-tree/model", 4096),
                         "device_tree_compatible": read_text(root / "proc/device-tree/compatible", 4096),
                         "nvidia_packages": packages},
            "python": python_modules() if include_imports else {"status": "NOT_RUN"},
            "network_addresses": probe(["ip", "-j", "address", "show"], runner),
            "network_routes": probe(["ip", "-j", "route", "show"], runner),
            # ss exposes owner name/PID where permitted, never process argv.
            "listening_ports": probe(["ss", "-H", "-lntup"], runner),
            "robot_scope_services": services, "candidate_manufacturer_services": manufacturers,
            "candidate_runtime_processes": processes,
            "usb": usb[:128], "video_by_id": video_ids,
            "resources": resource_snapshot(root=root, disk_path=disk_path),
            "external_jetson_off": "NOT_RUN", "cold_boot": "NOT_RUN"}


def runtime_sample(port: int) -> dict[str, Any]:
    result = {}
    for name, endpoint in (("health", "/api/v1/health"), ("cameras", "/api/v1/cameras"), ("topics", "/api/v1/topics")):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{endpoint}", timeout=2) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("oversize")
            value = json.loads(raw)
            if name == "health":
                result[name] = {key: value.get(key) for key in
                                ("agent_ready", "robot_online", "ros_interface_ready", "hostname")}
            else:
                entries = value.get(name, value.get("sources", [])) if isinstance(value, dict) else []
                result[name] = [{key: item.get(key) for key in
                                 ("id", "name", "state", "live", "hz", "age_s", "jitter_ms", "fps", "frames",
                                  "receive_fps", "last_complete_jpeg_age_s", "frames_received", "restart_count",
                                  "source_timestamp_age_s", "source_age_s", "timestamp_age_s", "last_message_age_s")
                                 if key in item} for item in entries[:128] if isinstance(item, dict)]
                if name == "topics":
                    for item in result[name]:
                        item["age_semantics"] = "callback receipt age_s; source timestamp age only when separately provided"
                    result["ros_source_latency"] = "NOT_RUN"
        except Exception as exc:
            result[name] = {"status": "NOT_RUN", "reason": type(exc).__name__}
    return result


def cpu_percent(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> float | None:
    if not previous or not current:
        return None
    total = current["total"] - previous["total"]
    idle = current["idle"] - previous["idle"]
    return round(100 * (total - idle) / total, 2) if total > 0 and 0 <= idle <= total else None


def summarize(samples: list[dict[str, Any]], elapsed: float, requested: float) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        return [row[key] for row in samples if isinstance(row.get(key), (int, float))]
    cpu, gpu = values("cpu_percent"), values("gpu_percent")
    temperatures = [zone["celsius"] for row in samples for zone in row["temperatures"]]
    available = [row["memory_bytes"]["MemAvailable"] for row in samples if "MemAvailable" in row["memory_bytes"]]
    swap = [row["memory_bytes"]["SwapTotal"] - row["memory_bytes"]["SwapFree"] for row in samples
            if {"SwapTotal", "SwapFree"} <= row["memory_bytes"].keys()]
    oom = values("oom_kill_count")
    return {"requested_seconds": requested, "observed_seconds": round(elapsed, 2), "samples": len(samples),
            "duration_complete": elapsed >= requested, "cpu_max_percent": max(cpu) if cpu else None,
            "gpu_max_percent": max(gpu) if gpu else None,
            "temperature_max_c": max(temperatures) if temperatures else None,
            "memory_min_available_bytes": min(available) if available else None,
            "swap_max_used_bytes": max(swap) if swap else None,
            "oom_kill_increase": max(oom) - min(oom) if oom else None,
            "throttling": "NOT_RUN", "external_jetson_off": "NOT_RUN", "cold_boot": "NOT_RUN",
            "acceptance": "NOT_RUN", "note": "Measurements alone do not prove required functions or physical isolation."}


def private_output(path: Path):
    if not path.is_absolute() or path == Path("/"):
        raise ValueError("output must be an absolute non-root path")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("output path must not contain symlinks")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "sample"))
    parser.add_argument("--output", type=Path, required=True, help="new private JSON/JSONL file, never overwritten")
    parser.add_argument("--disk-path", type=Path, default=Path.home())
    parser.add_argument("--duration-seconds", type=float, default=1800)
    parser.add_argument("--interval-seconds", type=float, default=10)
    parser.add_argument("--dashboard-port", type=int, default=8088)
    args = parser.parse_args(argv)
    if not (1 <= args.duration_seconds <= 7200 and 1 <= args.interval_seconds <= 60 and 1 <= args.dashboard_port <= 65535):
        parser.error("duration 1-7200, interval 1-60 and TCP port 1-65535 are required")
    try:
        with private_output(args.output) as stream:
            if args.command == "snapshot":
                json.dump(snapshot(disk_path=args.disk_path), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            else:
                started = time.monotonic()
                rows = []
                previous = None
                while True:
                    row = resource_snapshot(disk_path=args.disk_path)
                    row["cpu_percent"] = cpu_percent(previous, row["cpu_ticks"])
                    previous = row["cpu_ticks"]
                    row["runtime"] = runtime_sample(args.dashboard_port)
                    rows.append(row)
                    stream.write(json.dumps({"sample": row}, ensure_ascii=False) + "\n")
                    stream.flush()
                    remaining = args.duration_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        break
                    time.sleep(min(args.interval_seconds, remaining))
                stream.write(json.dumps({"summary": summarize(rows, time.monotonic() - started, args.duration_seconds)}) + "\n")
        print(f"Private diagnostic report: {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Diagnostic report failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
