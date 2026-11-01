"""Fixed, bounded systemd observation service. Never controls robot motion."""

from __future__ import annotations

import math
import subprocess
import time
from typing import Any

SERVICE = "robot-scope-observation.service"
LIMIT_SECONDS = 1800
PROPERTIES = (
    "Id",
    "LoadState",
    "ActiveState",
    "SubState",
    "InvocationID",
    "MainPID",
    "Result",
    "RuntimeMaxUSec",
    "ActiveEnterTimestampMonotonic",
    "KillMode",
    "Job",
)
SHOW = (
    "/usr/bin/systemctl",
    "show",
    SERVICE,
    "--no-pager",
    "--property=" + ",".join(PROPERTIES),
)
COMMANDS = {
    action: ("/usr/bin/sudo", "-n", "/usr/bin/systemctl", "--no-block", action, SERVICE)
    for action in ("start", "stop")
}


class ObservationServiceError(RuntimeError):
    pass


def run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=False,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=4.0,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )


def parse_status(text: str, *, now: float | None = None) -> dict[str, Any]:
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if values.get("LoadState") == "not-found":
        return dict(
            state="UNAVAILABLE",
            active=False,
            busy=False,
            session_id=None,
            reason="관측 서비스 설치가 필요합니다.",
            remaining_s=None,
        )
    if values.get("Id") != SERVICE or values.get("LoadState") != "loaded":
        raise ObservationServiceError("관측 서비스 상태를 확인할 수 없습니다.")
    # Do not accept an unbounded or differently-owned service with this name.
    if (
        values.get("RuntimeMaxUSec") not in {"30min", "1800000000", "30min 0s"}
        or values.get("KillMode") != "control-group"
    ):
        raise ObservationServiceError(
            "관측 서비스의 실행 제한 또는 종료 설정이 다릅니다."
        )
    state = values.get("ActiveState")
    active = state in {"active", "activating", "deactivating", "reloading"}
    if state not in {
        "active",
        "activating",
        "deactivating",
        "reloading",
        "inactive",
        "failed",
    }:
        raise ObservationServiceError("관측 서비스 상태가 불명확합니다.")
    invocation = values.get("InvocationID", "")
    if active and (
        len(invocation) != 32 or any(c not in "0123456789abcdef" for c in invocation)
    ):
        raise ObservationServiceError("관측 실행 식별자가 없습니다.")
    try:
        started = int(values.get("ActiveEnterTimestampMonotonic", "0")) / 1_000_000
    except ValueError as exc:
        raise ObservationServiceError("관측 시작 시각이 잘못되었습니다.") from exc
    remaining = (
        max(0.0, LIMIT_SECONDS - ((time.monotonic() if now is None else now) - started))
        if active and started > 0
        else None
    )
    job_pending = values.get("Job", "").split(" ")[0] not in {"", "0"}
    return dict(
        state={
            "active": "WAITING_INPUTS",
            "activating": "STARTING",
            "deactivating": "STOPPING",
            "reloading": "STARTING",
            "inactive": "STOPPED",
            "failed": "FAILED",
        }[state],
        active=active,
        busy=active or job_pending,
        job_pending=job_pending,
        session_id=invocation or None,
        started_monotonic_s=started,
        remaining_s=remaining,
        reason=""
        if state != "failed"
        else "관측기가 종료됐습니다. 실행 제한 또는 시작 조건을 확인하세요.",
        result=values.get("Result", ""),
    )


class ObservationService:
    def __init__(self, runner=run) -> None:
        self._run = runner

    def status(self) -> dict[str, Any]:
        result = self._run(SHOW)
        # Missing units may return nonzero with a complete LoadState response.
        if result.returncode and "LoadState=not-found" not in result.stdout:
            raise ObservationServiceError("관측 서비스 상태 조회에 실패했습니다.")
        return parse_status(result.stdout)

    def dispatch(self, action: str) -> None:
        if action not in COMMANDS:
            raise ObservationServiceError("지원하지 않는 관측 동작입니다.")
        try:
            result = self._run(COMMANDS[action])
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ObservationServiceError(
                "관측 요청 결과가 불명확합니다. 상태를 다시 확인합니다."
            ) from exc
        if result.returncode:
            raise ObservationServiceError(
                "관측 서비스 요청이 거절됐습니다. 설치·실행 권한을 확인하세요."
            )


def inspect_inputs(pose: dict, cloud: dict, started: float, *, now: float | None = None):
    """One pure readiness predicate shared by admission and diagnostics."""
    now = time.monotonic() if now is None else now
    failures = []
    def missing():
        if 'INPUT_MISSING_OR_INVALID' not in failures:
            failures.append('INPUT_MISSING_OR_INVALID')
    def check(condition, code):
        try:
            if not condition():
                failures.append(code)
        except (AttributeError, KeyError, TypeError, ValueError):
            failures.append(code)
            missing()
    check(lambda: pose.get('state') == 'ok', 'POSE_STATE')
    check(lambda: pose['topic'] == '/Odometry', 'POSE_TOPIC')
    check(lambda: pose['frame_id'] == 'camera_init', 'POSE_FRAME')
    check(lambda: pose['child_frame_id'] == 'body', 'POSE_CHILD_FRAME')
    check(lambda: cloud['topic'] == '/cloud_registered', 'CLOUD_TOPIC')
    check(lambda: cloud['frame_id'] == 'camera_init', 'CLOUD_FRAME')
    check(lambda: cloud.get('units') == 'm', 'CLOUD_UNITS')
    check(lambda: cloud.get('sent_points', 0) > 0, 'CLOUD_POINTS')
    check(lambda: not started <= 0, 'SESSION_START')
    for sample, prefix in ((pose, 'POSE'), (cloud, 'CLOUD')):
        def receipt_ok():
            received = sample['observation']['received_monotonic_s']
            return (type(received) in (int, float) and math.isfinite(received)
                    and 0 <= now - received <= 1 and not received < started)
        def graph_ok():
            graph = sample['observation']['subscription_evidence']['graph']
            graph_at = graph.get('observed_monotonic_s')
            return (graph.get('state') == 'ok' and graph.get('endpoint_count') == 1
                    and type(graph_at) in (int, float) and math.isfinite(graph_at)
                    and 0 <= now - graph_at <= 3 and graph.get('reported_publisher_count') == 1)
        check(receipt_ok, prefix + '_RECEIPT')
        check(graph_ok, prefix + '_GRAPH')
    return {'ready': not failures, 'failures': failures}


def inputs_ready(pose: dict, cloud: dict, started: float, *, now: float | None = None) -> bool:
    """Readiness means current inputs, never map registration or body accuracy."""
    return inspect_inputs(pose, cloud, started, now=now)["ready"]
