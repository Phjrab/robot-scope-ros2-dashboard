#!/usr/bin/env bash
set -euo pipefail

tool_path="$HOME/ws/hesai_ws/src/HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool_ptc/build/ptc_tool"

if [[ ! -x "$tool_path" ]]; then
  echo "PTC tool not found: $tool_path" >&2
  echo "See docs/troubleshooting.md to enable SET_DES_IP_AND_PORT and build tool_ptc." >&2
  exit 1
fi

exec "$tool_path" 192.168.123.20 9347
