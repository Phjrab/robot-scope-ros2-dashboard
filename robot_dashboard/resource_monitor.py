"""Demand-driven, read-only Linux/Jetson resource measurements.

One sampler belongs to one application runtime. Requests within an interval
share the same measurement, so extra tabs cannot shorten the delta window.
There are no sensor subscriptions, subprocesses, shell commands or sysfs writes.
"""

from __future__ import annotations

import math
import os
import platform
import re
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable


def read_text(path: Path, limit: int = 65536) -> str | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        return raw.decode("utf-8", errors="replace").replace("\0", "").strip() if len(raw) <= limit else None
    except OSError:
        return None


def number(path: Path) -> float | None:
    try:
        value = float(read_text(path, 256) or "")
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def utilization(previous: tuple[int, int] | None, current: tuple[int, int]) -> float | None:
    if previous is None:
        return None
    total, idle = current[0] - previous[0], current[1] - previous[1]
    return round(100 * (total - idle) / total, 2) if total > 0 and 0 <= idle <= total else None


def delta(previous: float | None, current: float | None, elapsed: float | None) -> float | None:
    if previous is None or current is None or elapsed is None or elapsed <= 0 or current < previous:
        return None
    return round((current - previous) / elapsed, 3)


def finite(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


class ResourceMonitor:
    def __init__(self, *, root: Path = Path("/"), interval_s: float = 1.0,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self.root = root
        self.interval_s = max(0.5, interval_s)
        self._clock, self._wall_clock = clock, wall_clock
        self._lock = threading.Lock()
        self._last_at: float | None = None
        self._cached: dict[str, Any] | None = None
        self._cpu: dict[str, tuple[int, int]] = {}
        self._network: dict[str, dict[str, float | None]] = {}
        self._processes: dict[int, tuple[int, int]] = {}
        self._oom: int | None = None
        self._sequence = 0
        self._tick_hz = os.sysconf("SC_CLK_TCK")
        self._page_size = os.sysconf("SC_PAGE_SIZE")
        self.host = {
            "hostname": socket.gethostname(), "architecture": platform.machine(),
            "model": read_text(root / "proc/device-tree/model", 1024) or "Linux host",
            "l4t": read_text(root / "etc/nv_tegra_release", 1024),
            "scope": "웹 서버가 실행되는 호스트 · 센서별 자원 사용량은 분리 추정하지 않음",
        }

    def _read_cpu(self) -> dict[str, tuple[int, int]]:
        result = {}
        for line in (read_text(self.root / "proc/stat") or "").splitlines():
            fields = line.split()
            if fields and re.fullmatch(r"cpu\d*", fields[0]):
                try:
                    ticks = [int(value) for value in fields[1:9]]
                    if len(ticks) >= 4 and all(value >= 0 for value in ticks):
                        result[fields[0]] = (sum(ticks), ticks[3] + (ticks[4] if len(ticks) > 4 else 0))
                except ValueError:
                    continue
        return result

    def _memory(self) -> dict[str, Any]:
        values = {}
        for line in (read_text(self.root / "proc/meminfo") or "").splitlines():
            match = re.fullmatch(r"(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB", line)
            if match:
                values[match[1]] = int(match[2]) * 1024
        total, available = values.get("MemTotal"), values.get("MemAvailable")
        used = total - available if total and available is not None and 0 <= available <= total else None
        swap_total, swap_free = values.get("SwapTotal"), values.get("SwapFree")
        swap_used = swap_total - swap_free if swap_total is not None and swap_free is not None and 0 <= swap_free <= swap_total else None
        return {"total_bytes": total, "available_bytes": available, "used_bytes": used,
                "percent": round(used / total * 100, 2) if used is not None else None,
                "swap_total_bytes": swap_total, "swap_used_bytes": swap_used}

    def _gpu(self) -> dict[str, Any]:
        paths = [self.root / "sys/devices" / path / "load" for path in (
            "gpu.0", "17000000.gpu", "platform/gpu.0", "platform/17000000.gpu", "platform/bus@0/17000000.gpu")]
        devices = sorted((self.root / "sys/class/devfreq").glob("*gpu*"))[:8]
        paths.extend(device / "device/load" for device in devices)
        load = next((v for p in paths if (v := number(p)) is not None and 0 <= v <= 1000), None)
        frequency = next((v for p in devices if (v := number(p / "cur_freq")) is not None and v >= 0), None)
        return {"percent": load / 10 if load is not None else None,
                "frequency_mhz": frequency / 1e6 if frequency is not None else None,
                "source": "Jetson sysfs load (0–1000)" if load is not None else None}

    def _thermal(self) -> list[dict[str, Any]]:
        result = []
        for zone in sorted((self.root / "sys/class/thermal").glob("thermal_zone*"))[:32]:
            temperature = number(zone / "temp")
            if temperature is None or not -50000 <= temperature <= 150000:
                continue
            trips = []
            for path in sorted(zone.glob("trip_point_*_type"))[:16]:
                kind = read_text(path, 128)
                value = number(path.with_name(path.name.replace("_type", "_temp")))
                if kind in {"passive", "hot", "critical"} and value is not None and value > 0:
                    trips.append({"type": kind, "celsius": value / 1000})
            result.append({"name": read_text(zone / "type", 128) or zone.name,
                           "celsius": temperature / 1000, "trips": trips})
        return result

    def _power(self) -> dict[str, Any]:
        rails = []
        for device in sorted((self.root / "sys/class/hwmon").glob("hwmon*"))[:32]:
            if read_text(device / "name", 128) != "ina3221":
                continue
            for label_file in sorted(device.glob("in*_label"))[:16]:
                match = re.fullmatch(r"in(\d+)_label", label_file.name)
                if not match:
                    continue
                label = read_text(label_file, 128)
                voltage = number(device / f"in{match[1]}_input")
                current = number(device / f"curr{match[1]}_input")
                if label and voltage is not None and current is not None and voltage >= 0 and current >= 0:
                    rails.append({"name": label, "watts": round(voltage * current / 1e6, 3)})
        total = next((rail["watts"] for rail in rails if rail["name"] in {"VDD_IN", "POM_5V_IN"}), None)
        return {"watts": total, "rails": rails, "source": "INA3221 voltage × current" if rails else None}

    def _read_network(self) -> dict[str, dict[str, Any]]:
        result = {}
        # sysfs works even when /proc/net/dev is in a container namespace.
        for interface in sorted((self.root / "sys/class/net").glob("*"))[:64]:
            if interface.name == "lo":
                continue
            counters = {name: number(interface / "statistics" / name) for name in
                        ("rx_bytes", "tx_bytes", "rx_dropped", "tx_dropped", "rx_errors", "tx_errors")}
            speed = number(interface / "speed")
            result[interface.name] = {
                **counters, "physical": (interface / "device").exists(),
                "state": read_text(interface / "operstate", 32),
                "speed_mbps": speed if speed is not None and speed > 0 else None,
            }
        return result

    def _process_snapshot(self, elapsed: float | None) -> dict[str, Any]:
        result, current = [], {}
        paths = sorted((self.root / "proc").glob("[0-9]*"), key=lambda p: int(p.name))
        for path in paths[:512]:
            raw = read_text(path / "stat", 4096)
            if not raw or ") " not in raw:
                continue
            try:
                name = raw[raw.index("(") + 1:raw.rindex(")")][:80]
                fields = raw[raw.rindex(")") + 2:].split()
                ticks, start, rss = int(fields[11]) + int(fields[12]), int(fields[19]), int(fields[21])
                pid = int(path.name)
            except (ValueError, IndexError):
                continue
            current[pid] = (start, ticks)
            previous = self._processes.get(pid)
            rate = delta(previous[1] if previous and previous[0] == start else None, ticks, elapsed)
            result.append({"pid": pid, "name": name, "cpu_percent": round(rate / self._tick_hz * 100, 2) if rate is not None else None,
                           "rss_bytes": max(0, rss) * self._page_size})
        self._processes = current
        result.sort(key=lambda row: (row["cpu_percent"] or 0, row["rss_bytes"]), reverse=True)
        return {"items": result[:12], "observed": len(result), "truncated": len(paths) > 512,
                "scope": "서버에서 보이는 PID 범위 · CPU 100% = 코어 1개 · RSS는 공유 메모리 포함"}

    def _pressure(self) -> dict[str, Any]:
        values = {}
        for kind in ("cpu", "memory", "io"):
            match = re.search(r"^some avg10=([\d.]+)", read_text(self.root / f"proc/pressure/{kind}") or "", re.M)
            values[kind] = float(match[1]) if match and 0 <= float(match[1]) <= 100 else None
        return values

    @staticmethod
    def _sensors(agent: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"cameras": [], "topics": [], "cameras_available": False, "topics_available": False}
        if agent is None:
            return result
        try:
            catalog = agent.cameras_snapshot()
            for row in catalog.get("sources", [])[:12]:
                result["cameras"].append({
                    "id": str(row.get("id", ""))[:128], "label": str(row.get("label", "카메라"))[:128],
                    "state": str(row.get("state", "waiting"))[:32], "live": row.get("live") is True,
                    "width": finite(row.get("width")), "height": finite(row.get("height")),
                    "fps": finite(row.get("fps")),
                    # Both catalog FPS fields are measured by frame counters.
                    "receive_fps": finite(row.get("receive_fps", row.get("fps"))),
                    "age_s": finite(row.get("last_complete_jpeg_age_s", row.get("age_s"))),
                    "bitrate_mbps": finite(row.get("receive_bitrate_mbps")),
                })
            result["cameras_available"] = True
        except Exception:
            # Sensor observability must not prevent host measurements.
            pass
        try:
            for row in agent.topics_snapshot():
                if row.get("category") not in {"camera", "pointcloud", "imu", "odometry", "occupancy_grid"}:
                    continue
                result["topics"].append({
                    "name": str(row.get("name", ""))[:256], "category": row.get("category"),
                    "state": str(row.get("state", "waiting"))[:32], "selected": row.get("selected") is True,
                    "hz": finite(row.get("hz")), "age_s": finite(row.get("age_s")),
                    "jitter_ms": finite(row.get("jitter_ms")),
                })
                if len(result["topics"]) >= 64:
                    break
            result["topics_available"] = True
        except Exception:
            pass
        return result

    def snapshot(self, agent: Any = None) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            if self._last_at is not None and self._cached is not None and 0 <= now - self._last_at < self.interval_s:
                return self._cached
            elapsed = now - self._last_at if self._last_at is not None and now > self._last_at else None
            cpu = self._read_cpu()
            cores = []
            for name, ticks in cpu.items():
                if name == "cpu":
                    continue
                directory = self.root / "sys/devices/system/cpu" / name
                online = read_text(directory / "online", 32) != "0"
                freq = number(directory / "cpufreq/scaling_cur_freq")
                cores.append({"name": name, "online": online,
                              "percent": utilization(self._cpu.get(name), ticks) if online else None,
                              "frequency_mhz": freq / 1000 if freq is not None else None})
            cpu_percent = utilization(self._cpu.get("cpu"), cpu["cpu"]) if "cpu" in cpu else None
            self._cpu = cpu
            network = self._read_network()
            interfaces = []
            for name, counters in network.items():
                previous = self._network.get(name, {})
                rates = {key: delta(previous.get(key), counters[key], elapsed) for key in
                         ("rx_bytes", "tx_bytes", "rx_dropped", "tx_dropped", "rx_errors", "tx_errors")}
                rx, tx = rates.pop("rx_bytes"), rates.pop("tx_bytes")
                interfaces.append({"name": name, **counters, **rates, "rx_bytes_s": rx, "tx_bytes_s": tx,
                                   "link_percent": round(max(rx, tx) * 8 / (counters["speed_mbps"] * 1e6) * 100, 2)
                                   if rx is not None and tx is not None and counters["speed_mbps"] else None})
            self._network = network
            physical = [row for row in interfaces if row["physical"] and row["state"] in {"up", "unknown"}]
            def total_rate(key: str) -> float | None:
                return round(sum(row[key] for row in physical), 3) if physical and all(row[key] is not None for row in physical) else None
            oom_match = re.search(r"^oom_kill (\d+)$", read_text(self.root / "proc/vmstat") or "", re.M)
            oom = int(oom_match[1]) if oom_match else None
            oom_delta = oom - self._oom if oom is not None and self._oom is not None and oom >= self._oom else None
            self._oom = oom
            self._sequence += 1
            self._cached = {
                "schema": "robot-scope.resources.v1", "seq": self._sequence,
                "timestamp_ms": round(self._wall_clock() * 1000), "sample_interval_s": elapsed,
                "poll_interval_s": self.interval_s, "host": self.host,
                "cpu": {"percent": cpu_percent, "cores": cores,
                        "max_core_percent": max((row["percent"] for row in cores if row["percent"] is not None), default=None)},
                "gpu": self._gpu(), "memory": self._memory(), "thermal": self._thermal(), "power": self._power(),
                "network": {"interfaces": interfaces, "rx_bytes_s": total_rate("rx_bytes_s"), "tx_bytes_s": total_rate("tx_bytes_s"),
                            "source": "sysfs · 물리 인터페이스 합계 · 가상 인터페이스 별도"},
                "pressure": self._pressure(), "oom_kill_count": oom, "oom_kill_delta": oom_delta,
                "processes": self._process_snapshot(elapsed), "sensors": self._sensors(agent),
            }
            self._last_at = now
            return self._cached
