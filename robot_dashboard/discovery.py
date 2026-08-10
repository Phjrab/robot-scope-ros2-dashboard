"""Bounded local-network discovery and supported robot metadata.

The browser can select a robot *type*, but it cannot provide a subnet, an
interface, or probe targets.  All scan scope is derived from directly attached
RFC1918/link-local IPv4 interfaces on the dashboard host and is capped at one
/24.  This keeps the feature useful in a classroom LAN without turning the web
API into an arbitrary network scanner.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence


LOCAL_IPV4_RANGES = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
)
IGNORED_INTERFACE_PREFIXES = (
    "br-",
    "docker",
    "dummy",
    "lxc",
    "tailscale",
    "tap",
    "tun",
    "veth",
    "virbr",
    "vmnet",
    "wg",
)
HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?\.)*"
    r"[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?\.?"
)
PING_TIME_RE = re.compile(r"\btime[=<]([0-9]+(?:\.[0-9]+)?)\s*ms\b")


ROBOT_TYPES: Dict[str, Dict[str, Any]] = {
    "go2": {
        "id": "go2",
        "label": "Unitree Go2",
        "description": "Unitree Go2 본체와 전용 유선 네트워크를 탐색합니다.",
        "connection_kind": "robot",
        "profile_id": "go2",
        "known_ips": ("192.168.123.161",),
        "hostname_hints": ("go2", "unitree"),
        "model": {
            "kind": "robot-model-lite",
            "asset_url": "/static/assets/go2/go2-official-lite.json",
            "urdf_url": None,
            "label": "Unitree Go2 official-derived model",
            "fidelity": "official-derived",
        },
    },
    "turtlebot": {
        "id": "turtlebot",
        "label": "TurtleBot",
        "description": "같은 로컬 네트워크의 TurtleBot ROS 2 컴퓨터를 탐색합니다.",
        "connection_kind": "robot",
        "profile_id": "turtlebot",
        "known_ips": (),
        "hostname_hints": ("turtlebot", "turtlebot3", "tb3", "burger", "waffle"),
        "model": {
            "kind": "robot-model-lite",
            "asset_url": "/static/assets/turtlebot/turtlebot3-burger-official-lite.json",
            "urdf_url": (
                "/static/assets/turtlebot/source/turtlebot3_description/urdf/"
                "turtlebot3_burger.urdf"
            ),
            "label": "Official ROBOTIS TurtleBot3 Burger model",
            "fidelity": "official-derived",
        },
    },
    "so-101": {
        "id": "so-101",
        "label": "SO-101",
        "description": (
            "SO-101은 일반적으로 USB/serial 장치입니다. 네트워크에서는 팔 자체가 아니라 "
            "팔이 연결된 ROS 2 컨트롤러 호스트를 탐색합니다."
        ),
        "connection_kind": "controller_host",
        "notice": "검색 결과의 IP와 hostname은 SO-101 팔이 연결된 ROS 컨트롤러 컴퓨터입니다.",
        "profile_id": "so-101",
        "known_ips": (),
        "hostname_hints": ("so101", "so-101", "lerobot"),
        "model": {
            "kind": "robot-model-lite",
            "asset_url": "/static/assets/so101/so101-official-lite.json",
            "urdf_url": "/static/assets/so101/source/SO101/so101_new_calib.urdf",
            "label": "Official TheRobotStudio SO-101 model",
            "fidelity": "official-derived",
        },
    },
}


class DiscoveryError(RuntimeError):
    """Base class for safe discovery errors exposed by the API."""


class UnknownRobotType(DiscoveryError):
    pass


class DiscoveryUnavailable(DiscoveryError):
    pass


class DiscoveryBusy(DiscoveryError):
    pass


def is_local_robot_ipv4(value: str) -> bool:
    """Return whether *value* is a selectable, non-special local IPv4 host."""

    try:
        address = ipaddress.IPv4Address(str(value).strip())
    except ipaddress.AddressValueError:
        return False
    if address.is_loopback or address.is_multicast or address.is_unspecified:
        return False
    return any(address in network for network in LOCAL_IPV4_RANGES)


def normalize_hostname(value: str | None) -> str:
    """Normalize a display hostname while rejecting control characters/HTML."""

    hostname = str(value or "").strip().rstrip(".").lower()
    if not hostname:
        return ""
    if not HOSTNAME_RE.fullmatch(hostname):
        raise ValueError("hostname 형식이 올바르지 않습니다.")
    return hostname


def robot_type_definition(robot_type: str) -> Dict[str, Any]:
    key = str(robot_type).strip().lower()
    definition = ROBOT_TYPES.get(key)
    if definition is None:
        raise UnknownRobotType("지원하지 않는 로봇 유형입니다.")
    return copy.deepcopy(definition)


def public_robot_types() -> list[Dict[str, Any]]:
    """Return catalog fields safe and useful to the browser."""

    result = []
    for key in ROBOT_TYPES:
        definition = robot_type_definition(key)
        definition.pop("known_ips", None)
        definition.pop("hostname_hints", None)
        result.append(definition)
    return result


def infer_robot_type(profile: Mapping[str, Any]) -> str:
    """Resolve startup type, preferring the profile's explicit safe ID."""

    if "robot_type" in profile:
        explicit = str(profile.get("robot_type", "")).strip().lower().replace("_", "-")
        aliases = {"so101": "so-101", "turtlebot3": "turtlebot", "generic": ""}
        explicit = aliases.get(explicit, explicit)
        return explicit if explicit in ROBOT_TYPES else ""

    name = str(profile.get("name", "")).lower()
    if "go2" in name or "unitree" in name:
        return "go2"
    if "turtle" in name:
        return "turtlebot"
    if "so-101" in name or "so101" in name:
        return "so-101"
    return ""


def _default_command_runner(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class LocalRobotDiscovery:
    """Discover responsive hosts on a single bounded, directly attached LAN."""

    CACHE_TTL_S = 15.0
    FAILURE_BACKOFF_S = 3.0
    MAX_ACTIVE_HOSTS = 256
    MAX_RESULTS = 256
    MAX_WORKERS = 32
    MAX_SCAN_SECONDS = 12.0
    MAX_RESOLVE_SECONDS = 4.0
    VALID_NEIGHBOR_STATES = {"REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT", "NOARP"}

    def __init__(
        self,
        *,
        command_runner: Callable[[Sequence[str], float], subprocess.CompletedProcess[str]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._run_command = command_runner or _default_command_runner
        self._clock = clock
        self._condition = threading.Condition()
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._inflight: set[str] = set()
        self._last_failure: Dict[str, tuple[float, str]] = {}

    def discover(self, robot_type: str) -> Dict[str, Any]:
        definition = robot_type_definition(robot_type)
        key = definition["id"]
        now = self._clock()
        with self._condition:
            cached = self._cache.get(key)
            if cached and now - cached[0] < self.CACHE_TTL_S:
                return self._cached_copy(cached[1])
            # Never make duplicate API requests occupy asyncio's default
            # worker pool while waiting for a long ICMP sweep.  One global
            # scan at a time is enough for this single-user dashboard.
            if self._inflight:
                raise DiscoveryBusy("다른 로컬 네트워크 검색이 이미 진행 중입니다.")
            failure = self._last_failure.get(key)
            if failure and now - failure[0] < self.FAILURE_BACKOFF_S:
                raise DiscoveryBusy("잠시 후 로컬 네트워크 검색을 다시 시도해 주세요.")
            self._inflight.add(key)

        try:
            result = self._scan(definition)
        except DiscoveryError as exc:
            with self._condition:
                self._last_failure[key] = (self._clock(), str(exc))
            raise
        except Exception as exc:
            message = f"로컬 네트워크 검색 실패: {type(exc).__name__}"
            with self._condition:
                self._last_failure[key] = (self._clock(), message)
            raise DiscoveryUnavailable(message) from exc
        else:
            with self._condition:
                self._cache[key] = (self._clock(), copy.deepcopy(result))
                self._last_failure.pop(key, None)
            return result
        finally:
            with self._condition:
                self._inflight.discard(key)
                self._condition.notify_all()

    def validate_target(self, robot_type: str, address_text: str) -> str:
        """Require a selected target to be on a directly attached safe LAN."""

        robot_type_definition(robot_type)
        if not is_local_robot_ipv4(address_text):
            raise ValueError("로봇 대상은 로컬 RFC1918 또는 link-local IPv4 주소여야 합니다.")
        address = ipaddress.IPv4Address(str(address_text).strip())
        interfaces = self._local_interfaces()
        matching = [interface for interface in interfaces if address in interface["_network"]]
        if not matching:
            raise ValueError("선택한 IP가 Jetson의 직접 연결된 로컬 네트워크에 없습니다.")
        if any(
            address == ipaddress.IPv4Address(interface["address"])
            or address == interface["_network"].network_address
            or address == interface["_network"].broadcast_address
            for interface in matching
        ):
            raise ValueError("Jetson 자체 IP 또는 network/broadcast 주소는 로봇 대상으로 사용할 수 없습니다.")
        return str(address)

    @staticmethod
    def _cached_copy(value: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(value)
        result["cached"] = True
        return result

    def _json_command(self, command: Sequence[str], timeout: float = 1.5) -> Any:
        try:
            result = self._run_command(command, timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0 or len(result.stdout) > 2_000_000:
            return None
        try:
            return json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _interface_allowed(name: str) -> bool:
        lowered = name.strip().lower()
        return bool(lowered) and lowered != "lo" and not lowered.startswith(IGNORED_INTERFACE_PREFIXES)

    def _local_interfaces(self) -> list[Dict[str, Any]]:
        payload = self._json_command(("ip", "-j", "-4", "addr", "show", "up"))
        if not isinstance(payload, list):
            raise DiscoveryUnavailable("활성화된 로컬 IPv4 인터페이스를 확인할 수 없습니다.")
        interfaces: list[Dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("ifname", ""))
            if not self._interface_allowed(name):
                continue
            for address_item in item.get("addr_info", []):
                if not isinstance(address_item, dict) or address_item.get("family") != "inet":
                    continue
                address_text = str(address_item.get("local", ""))
                if not is_local_robot_ipv4(address_text):
                    continue
                try:
                    prefix = int(address_item.get("prefixlen", 32))
                    interface = ipaddress.IPv4Interface(f"{address_text}/{prefix}")
                except (ValueError, ipaddress.AddressValueError):
                    continue
                interfaces.append(
                    {
                        "name": name,
                        "address": str(interface.ip),
                        "network": str(interface.network),
                        "_network": interface.network,
                    }
                )
        # One interface can have multiple addresses; stable ordering also makes
        # the selected active scan scope predictable and testable.
        interfaces.sort(key=lambda row: (row["name"], ipaddress.IPv4Address(row["address"])))
        if not interfaces:
            raise DiscoveryUnavailable("탐색 가능한 RFC1918 또는 link-local IPv4 인터페이스가 없습니다.")
        return interfaces

    def _default_interface(self) -> str:
        payload = self._json_command(("ip", "-j", "-4", "route", "show", "default"))
        if not isinstance(payload, list):
            return ""
        for item in payload:
            if isinstance(item, dict) and self._interface_allowed(str(item.get("dev", ""))):
                return str(item["dev"])
        return ""

    def _neighbors(self, interfaces: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
        payload = self._json_command(("ip", "-j", "-4", "neigh", "show"))
        if not isinstance(payload, list):
            return {}
        allowed = {str(item["name"]): item for item in interfaces}
        own_addresses = {str(item["address"]) for item in interfaces}
        neighbors: Dict[str, Dict[str, Any]] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            device = str(item.get("dev", ""))
            address_text = str(item.get("dst", ""))
            state_value = item.get("state", "")
            states = {str(value).upper() for value in state_value} if isinstance(state_value, list) else {
                value for value in str(state_value).upper().split(",") if value
            }
            interface = allowed.get(device)
            if (
                interface is None
                or address_text in own_addresses
                or not states.intersection(self.VALID_NEIGHBOR_STATES)
                or not is_local_robot_ipv4(address_text)
            ):
                continue
            address = ipaddress.IPv4Address(address_text)
            if address not in interface["_network"]:
                continue
            neighbors[str(address)] = {"interface": device, "source": "neighbor"}
        return neighbors

    def _mdns_hosts(self, interfaces: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
        try:
            result = self._run_command(
                ("avahi-browse", "--all", "--terminate", "--resolve", "--parsable"),
                2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0 or len(result.stdout) > 2_000_000:
            return {}
        by_name = {str(item["name"]): item for item in interfaces}
        own_addresses = {str(item["address"]) for item in interfaces}
        hosts: Dict[str, Dict[str, Any]] = {}
        for line in result.stdout.splitlines():
            fields = line.split(";")
            # Resolved Avahi records are: =;iface;protocol;name;type;domain;
            # hostname;address;port;txt...
            if len(fields) < 9 or fields[0] != "=" or fields[2] != "IPv4":
                continue
            device, hostname, address_text = fields[1], fields[6], fields[7]
            interface = by_name.get(device)
            if interface is None or address_text in own_addresses or not is_local_robot_ipv4(address_text):
                continue
            address = ipaddress.IPv4Address(address_text)
            if address not in interface["_network"]:
                continue
            try:
                normalized = normalize_hostname(hostname)
            except ValueError:
                normalized = ""
            row = hosts.setdefault(str(address), {"interface": device, "source": "mdns"})
            if normalized:
                row["hostname"] = normalized
        return hosts

    @staticmethod
    def _scan_network(interface: Mapping[str, Any]) -> ipaddress.IPv4Network:
        network = interface["_network"]
        # A /8 or /16 interface never authorizes a broad sweep.  Only the /24
        # containing the dashboard address is active-scanned.
        if network.prefixlen < 24:
            return ipaddress.ip_network(f"{interface['address']}/24", strict=False)
        return network

    def _select_scan_interface(
        self,
        interfaces: Sequence[Mapping[str, Any]],
        definition: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        for known in definition.get("known_ips", ()):
            address = ipaddress.IPv4Address(known)
            for interface in interfaces:
                if address in interface["_network"]:
                    return interface
        default_name = self._default_interface()
        return next((item for item in interfaces if item["name"] == default_name), interfaces[0])

    def _probe(self, address: str) -> float | None:
        started = self._clock()
        try:
            result = self._run_command(("ping", "-n", "-c", "1", "-W", "1", address), 1.35)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        match = PING_TIME_RE.search(result.stdout)
        if match:
            return round(float(match.group(1)), 2)
        return round(max(0.0, self._clock() - started) * 1000.0, 2)

    def _probe_many(self, addresses: Sequence[str]) -> Dict[str, float]:
        if not addresses:
            return {}
        executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="robot-scan")
        futures: Dict[Future[float | None], str] = {
            executor.submit(self._probe, address): address
            for address in addresses[: self.MAX_ACTIVE_HOSTS]
        }
        responsive: Dict[str, float] = {}
        try:
            for future in as_completed(futures, timeout=self.MAX_SCAN_SECONDS):
                address = futures[future]
                try:
                    latency = future.result()
                except Exception:
                    latency = None
                if latency is not None:
                    responsive[address] = latency
        except TimeoutError:
            pass
        finally:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
        return responsive

    def _resolve_hostname(self, address: str) -> str:
        try:
            result = self._run_command(("getent", "hosts", address), 0.8)
        except (OSError, subprocess.SubprocessError):
            return ""
        if result.returncode != 0 or not result.stdout:
            return ""
        fields = result.stdout.splitlines()[0].split()
        if len(fields) < 2:
            return ""
        try:
            return normalize_hostname(fields[1])
        except ValueError:
            return ""

    def _resolve_many(self, addresses: Iterable[str]) -> Dict[str, str]:
        values = list(addresses)[: self.MAX_RESULTS]
        if not values:
            return {}
        executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="robot-dns")
        futures: Dict[Future[str], str] = {
            executor.submit(self._resolve_hostname, address): address for address in values
        }
        resolved: Dict[str, str] = {}
        try:
            for future in as_completed(futures, timeout=self.MAX_RESOLVE_SECONDS):
                address = futures[future]
                try:
                    hostname = future.result()
                except Exception:
                    hostname = ""
                if hostname:
                    resolved[address] = hostname
        except TimeoutError:
            pass
        finally:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
        return resolved

    @staticmethod
    def _candidate_match(
        definition: Mapping[str, Any],
        address: str,
        hostname: str,
        sources: set[str],
    ) -> tuple[float, str]:
        if address in definition.get("known_ips", ()):
            return 0.99, "제조사 기본 IP 주소와 일치합니다."
        lowered = hostname.lower()
        if lowered and any(hint in lowered for hint in definition.get("hostname_hints", ())):
            if definition["id"] == "so-101":
                return 0.85, "SO-101 명칭과 일치하는 ROS 컨트롤러 hostname입니다."
            return 0.85, "선택한 로봇 유형의 hostname 패턴과 일치합니다."
        if "mdns" in sources:
            reason = "mDNS로 발견된 같은 로컬 네트워크 호스트입니다."
            confidence = 0.45
        elif "neighbor" in sources:
            reason = "Jetson의 로컬 neighbor table에 있는 응답 가능 호스트입니다."
            confidence = 0.35
        else:
            reason = "같은 로컬 네트워크에서 ping에 응답한 미확인 호스트입니다."
            confidence = 0.2
        if definition["id"] == "so-101":
            reason += " SO-101 팔 자체가 아니라 USB/serial 연결을 제공하는 컨트롤러 후보입니다."
        return confidence, reason

    def _scan(self, definition: Mapping[str, Any]) -> Dict[str, Any]:
        interfaces = self._local_interfaces()
        scan_interface = self._select_scan_interface(interfaces, definition)
        scan_network = self._scan_network(scan_interface)
        own_addresses = {str(item["address"]) for item in interfaces}
        neighbor_rows = self._neighbors(interfaces)
        mdns_rows = self._mdns_hosts(interfaces)

        priority: list[str] = []
        sources: Dict[str, set[str]] = {}
        interface_by_ip: Dict[str, str] = {}
        mdns_names: Dict[str, str] = {}

        def add(address_text: str, source: str, device: str = "", hostname: str = "") -> None:
            if address_text in own_addresses or not is_local_robot_ipv4(address_text):
                return
            address = ipaddress.IPv4Address(address_text)
            if address not in scan_network or (device and device != scan_interface["name"]):
                return
            normalized = str(address)
            if normalized not in sources:
                priority.append(normalized)
                sources[normalized] = set()
            sources[normalized].add(source)
            interface_by_ip[normalized] = str(scan_interface["name"])
            if hostname:
                mdns_names[normalized] = hostname

        for known in definition.get("known_ips", ()):
            add(known, "known")
        for address, row in mdns_rows.items():
            add(address, "mdns", str(row.get("interface", "")), str(row.get("hostname", "")))
        for address, row in neighbor_rows.items():
            add(address, "neighbor", str(row.get("interface", "")))
        for address in scan_network.hosts():
            if len(priority) >= self.MAX_ACTIVE_HOSTS:
                break
            add(str(address), "active_scan", str(scan_interface["name"]))

        responsive = self._probe_many(priority)
        unresolved = [address for address in responsive if address not in mdns_names]
        hostnames = self._resolve_many(unresolved)
        hostnames.update(mdns_names)

        candidates = []
        for address, latency in responsive.items():
            hostname = hostnames.get(address, "")
            confidence, reason = self._candidate_match(
                definition,
                address,
                hostname,
                sources.get(address, set()),
            )
            candidates.append(
                {
                    "ip": address,
                    "hostname": hostname,
                    "interface": interface_by_ip.get(address, ""),
                    "latency_ms": latency,
                    "confidence": confidence,
                    "reason": reason,
                }
            )
        candidates.sort(
            key=lambda row: (-row["confidence"], ipaddress.IPv4Address(row["ip"]))
        )
        public_interfaces = [
            {"name": item["name"], "address": item["address"], "network": item["network"]}
            for item in interfaces
        ]
        return {
            "robot_type": definition["id"],
            "connection_kind": definition["connection_kind"],
            "notice": definition.get("notice", ""),
            "candidates": candidates[: self.MAX_RESULTS],
            "interfaces": public_interfaces,
            "scan_scope": {
                "interface": scan_interface["name"],
                "network": str(scan_network),
                "host_limit": self.MAX_ACTIVE_HOSTS,
            },
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "cached": False,
        }


__all__ = [
    "DiscoveryBusy",
    "DiscoveryError",
    "DiscoveryUnavailable",
    "LocalRobotDiscovery",
    "UnknownRobotType",
    "infer_robot_type",
    "is_local_robot_ipv4",
    "normalize_hostname",
    "public_robot_types",
    "robot_type_definition",
]
