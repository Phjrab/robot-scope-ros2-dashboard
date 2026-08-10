#!/usr/bin/env bash
set -uo pipefail

# A ROS 2 participant cannot be retargeted after CycloneDDS starts.  Keep the
# control bridge fail-closed, and give the dashboard supervisor a side-effect
# free readiness probe, until the dedicated Go2 link is genuinely usable.
GO2_INTERFACE="${ROBOT_SCOPE_GO2_INTERFACE:-eno1}"
GO2_INTERFACE_CIDR="${ROBOT_SCOPE_GO2_INTERFACE_CIDR:-192.168.123.99/24}"
POLL_SECONDS="${ROBOT_SCOPE_GO2_INTERFACE_POLL_SECONDS:-2}"

usage() {
  echo "usage: $0 [--check|--wait [--notify PID]]" >&2
}

if [[ ! "$GO2_INTERFACE" =~ ^[A-Za-z0-9_.:@-]{1,64}$ ]]; then
  echo "[Robot Scope] invalid Go2 interface label" >&2
  exit 2
fi
if [[ ! "$GO2_INTERFACE_CIDR" =~ ^192\.168\.123\.[0-9]{1,3}/(24|25|26|27|28|29|30|31|32)$ ]]; then
  echo "[Robot Scope] invalid Go2 interface CIDR" >&2
  exit 2
fi
if [[ ! "$POLL_SECONDS" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
  echo "[Robot Scope] invalid Go2 interface poll interval" >&2
  exit 2
fi

MODE="${1:---wait}"
NOTIFY_PID=""
if [[ "$MODE" == "--wait" && "$#" -eq 3 && "${2:-}" == "--notify" ]]; then
  NOTIFY_PID="${3:-}"
  if [[ ! "$NOTIFY_PID" =~ ^[1-9][0-9]*$ ]]; then
    echo "[Robot Scope] invalid readiness notification PID" >&2
    exit 2
  fi
elif [[ "$#" -gt 1 ]]; then
  usage
  exit 2
fi
if [[ "$MODE" != "--check" && "$MODE" != "--wait" ]]; then
  usage
  exit 2
fi

IP_BIN="$(command -v ip 2>/dev/null || true)"
if [[ -z "$IP_BIN" ]]; then
  echo "[Robot Scope] ip command is unavailable" >&2
  exit 2
fi

interface_ready() {
  local link_line
  link_line="$("$IP_BIN" -o link show dev "$GO2_INTERFACE" 2>/dev/null)" || return 1
  [[ "$link_line" == *"LOWER_UP"* ]] || return 1

  "$IP_BIN" -o -4 addr show dev "$GO2_INTERFACE" scope global 2>/dev/null \
    | awk -v expected="$GO2_INTERFACE_CIDR" '$4 == expected { found = 1 } END { exit found ? 0 : 1 }'
}

if [[ "$MODE" == "--check" ]]; then
  interface_ready
  exit $?
fi

sleep_pid=""
stopping=0
stop_waiting() {
  stopping=1
  if [[ -n "$sleep_pid" ]]; then
    kill -TERM "$sleep_pid" 2>/dev/null || true
  fi
}
trap stop_waiting TERM INT HUP

announce_ready() {
  echo "[Robot Scope] Go2 interface ready | iface=$GO2_INTERFACE | address=$GO2_INTERFACE_CIDR"
  if [[ -n "$NOTIFY_PID" ]]; then
    kill -USR1 "$NOTIFY_PID" 2>/dev/null || return 3
  fi
}

if interface_ready; then
  announce_ready
  exit $?
fi

echo "[Robot Scope] waiting for Go2 interface | iface=$GO2_INTERFACE | address=$GO2_INTERFACE_CIDR"
while ! interface_ready; do
  sleep "$POLL_SECONDS" &
  sleep_pid=$!
  wait "$sleep_pid" 2>/dev/null || true
  sleep_pid=""
  if [[ "$stopping" -eq 1 ]]; then
    exit 143
  fi
done
announce_ready
