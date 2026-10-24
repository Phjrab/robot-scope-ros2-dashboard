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


def inputs_ready(
    pose: dict, cloud: dict, started: float, *, now: float | None = None
) -> bool:
    """Readiness means current inputs, never map registration or body accuracy."""
    try:
        now = time.monotonic() if now is None else now
        if (
            pose.get("state") != "ok"
            or pose["topic"] != "/Odometry"
            or pose["frame_id"] != "camera_init"
            or pose["child_frame_id"] != "body"
            or cloud["topic"] != "/cloud_registered"
            or cloud["frame_id"] != "camera_init"
            or cloud.get("units") != "m"
            or not cloud.get("sent_points", 0) > 0
            or started <= 0
        ):
            return False
        for sample in (pose, cloud):
            observation = sample["observation"]
            received = observation["received_monotonic_s"]
            graph = observation["subscription_evidence"]["graph"]
            graph_at = graph.get("observed_monotonic_s")
            if (
                type(received) not in (int, float)
                or not math.isfinite(received)
                or not 0 <= now - received <= 1
                or received < started
                or graph.get("state") != "ok"
                or graph.get("endpoint_count") != 1
                or type(graph_at) not in (int, float)
                or not math.isfinite(graph_at)
                or not 0 <= now - graph_at <= 3
                or graph.get("reported_publisher_count") != 1
            ):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False
