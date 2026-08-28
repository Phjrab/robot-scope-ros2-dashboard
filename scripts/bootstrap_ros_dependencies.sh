#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
MANIFEST="$PROJECT_DIR/config/ros_dependencies_humble.json"
MODE=""
ACTION="dry-run"
WORKSPACE_ROOT="${ROBOT_SCOPE_WORKSPACE_ROOT:-$HOME}"
LIVOX_SDK_PREFIX_VALUE="${ROBOT_SCOPE_LIVOX_SDK_PREFIX:-}"
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_ros_dependencies.sh --mode MODE [OPTIONS]

Clone and build the pinned ROS 2 source dependencies used by Robot Scope.
The default is a side-effect-free dry run.

Modes:
  observer       Dashboard only; no vendor ROS source workspace
  go2            Unitree messages and CycloneDDS integration
  go2-control    Same source dependencies as go2
  go2-xt16       Unitree + Hesai + Livox messages + FAST-LIO
  go2-nav        Full go2-xt16 stack used by Navigation

Options:
  --manifest PATH              Distro-specific pinned dependency manifest
  --dry-run                  Print the exact operations (default)
  --apply                    Clone and build dependencies
  --workspace-root PATH      Parent for unitree_ros2 and ws/ (default: $HOME)
  --skip-build               Verify/clone pinned sources without colcon builds
  -h, --help                 Show this help

Existing repositories are never reset or upgraded. They must have the expected
origin, pinned commit, and no tracked modifications or the command fails.
EOF
}

die() {
  echo "[Robot Scope bootstrap] ERROR: $*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --mode)
      (($# >= 2)) || die "--mode requires a value"
      MODE="$2"
      shift 2
      ;;
    --workspace-root)
      (($# >= 2)) || die "--workspace-root requires a value"
      WORKSPACE_ROOT="$2"
      shift 2
      ;;
    --manifest)
      (($# >= 2)) || die "--manifest requires a value"
      MANIFEST="$2"
      shift 2
      ;;
    --dry-run)
      ACTION="dry-run"
      shift
      ;;
    --apply)
      ACTION="apply"
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

case "$MODE" in
  observer|go2|go2-control|go2-xt16|go2-nav) ;;
  "") die "--mode is required" ;;
  *) die "unsupported mode: $MODE" ;;
esac

[[ -f "$MANIFEST" ]] || die "dependency manifest is missing: $MANIFEST"
command -v python3 >/dev/null || die "python3 is required"

ROS_DISTRO_NAME="$(python3 - "$MANIFEST" <<'PY'
import json
import pathlib
import re
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")).get("ros_distro", "")
if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
    raise SystemExit("invalid ros_distro in dependency manifest")
print(value)
PY
)"
ROS_SETUP="/opt/ros/$ROS_DISTRO_NAME/setup.bash"
if [[ "$MODE" != "observer" && "$ROS_DISTRO_NAME" != "humble" ]]; then
  die "vendor Go2/XT16 source bootstrap is supported only with ROS 2 Humble"
fi

if [[ "$WORKSPACE_ROOT" != /* ]]; then
  WORKSPACE_ROOT="$(pwd -P)/$WORKSPACE_ROOT"
fi
WORKSPACE_ROOT="${WORKSPACE_ROOT%/}"
[[ -n "$WORKSPACE_ROOT" && "$WORKSPACE_ROOT" != "/" ]] || die "unsafe workspace root"
case "$LIVOX_SDK_PREFIX_VALUE" in
  "") LIVOX_SDK_PREFIX="$WORKSPACE_ROOT/ws/livox/sdk2_install" ;;
  /*) LIVOX_SDK_PREFIX="${LIVOX_SDK_PREFIX_VALUE%/}" ;;
  *) die "ROBOT_SCOPE_LIVOX_SDK_PREFIX must be blank or absolute" ;;
esac
[[ -n "$LIVOX_SDK_PREFIX" && "$LIVOX_SDK_PREFIX" != "/" ]] || \
  die "unsafe Livox-SDK2 prefix"
if [[ "$MODE" == "go2-xt16" || "$MODE" == "go2-nav" ]]; then
  if [[ "$WORKSPACE_ROOT" =~ [[:space:]] || "$LIVOX_SDK_PREFIX" =~ [[:space:]] ]]; then
    die "XT16 workspace and Livox-SDK2 paths cannot contain whitespace"
  fi
fi

echo "[Robot Scope bootstrap] mode=$MODE action=$ACTION root=$WORKSPACE_ROOT"

if [[ "$MODE" == "observer" ]]; then
  echo "[Robot Scope bootstrap] observer mode has no vendor source dependencies"
  exit 0
fi

if [[ "$ACTION" == "apply" ]]; then
  [[ "$EUID" -ne 0 ]] || die "run source builds as the target non-root user, not root"
  command -v git >/dev/null || die "git is required"
  command -v colcon >/dev/null || die "colcon is required"
  command -v cmake >/dev/null || die "cmake is required"
  [[ -f "$ROS_SETUP" ]] || die "ROS 2 $ROS_DISTRO_NAME is not installed"
fi

print_command() {
  printf '[dry-run]'
  printf ' %q' "$@"
  printf '\n'
}

run() {
  if [[ "$ACTION" == "dry-run" ]]; then
    print_command "$@"
  else
    "$@"
  fi
}

dependency_field() {
  local name="$1" field="$2"
  python3 - "$MANIFEST" "$name" "$field" <<'PY'
import json
import pathlib
import sys

manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
item = manifest["repositories"][sys.argv[2]]
value = item[sys.argv[3]]
if isinstance(value, bool):
    print("1" if value else "0")
else:
    print(value)
PY
}

verify_existing_repository() {
  local name="$1" url="$2" commit="$3" target="$4" recursive="$5"
  [[ -d "$target/.git" ]] || die "$name target exists but is not a Git repository: $target"
  local actual_url actual_commit dirty
  actual_url="$(git -C "$target" remote get-url origin 2>/dev/null || true)"
  [[ "$actual_url" == "$url" || "${actual_url%.git}" == "${url%.git}" ]] || \
    die "$name origin mismatch: $actual_url"
  actual_commit="$(git -C "$target" rev-parse HEAD)"
  [[ "$actual_commit" == "$commit" ]] || \
    die "$name is at $actual_commit; expected pinned $commit (no automatic reset is performed)"
  dirty="$(git -C "$target" status --porcelain=v1 --untracked-files=no)"
  [[ -z "$dirty" ]] || die "$name has tracked local modifications"
  if [[ "$recursive" == "1" ]]; then
    git -C "$target" submodule status --recursive | grep -Eq '^[+-U]' && \
      die "$name has an uninitialized or mismatched submodule"
  fi
  echo "[Robot Scope bootstrap] verified $name @ $commit"
}

install_repository() {
  local name="$1"
  local url commit relative recursive
  url="$(dependency_field "$name" url)"
  commit="$(dependency_field "$name" commit)"
  relative="$(dependency_field "$name" target)"
  recursive="$(dependency_field "$name" recursive)"
  local target="$WORKSPACE_ROOT/$relative"

  if [[ -e "$target" ]]; then
    if [[ "$ACTION" == "dry-run" ]]; then
      print_command git -C "$target" verify-pinned-origin-and-commit "$commit"
    else
      verify_existing_repository "$name" "$url" "$commit" "$target" "$recursive"
    fi
    return
  fi

  run mkdir -p "$(dirname -- "$target")"
  if [[ "$recursive" == "1" ]]; then
    run git clone --recurse-submodules -- "$url" "$target"
  else
    run git clone -- "$url" "$target"
  fi
  run git -C "$target" checkout --detach "$commit"
  if [[ "$recursive" == "1" ]]; then
    run git -C "$target" submodule update --init --recursive
  fi
}

run_with_setups() {
  local workdir="$1"
  shift
  local setup_count="$1"
  shift
  local setups=("${@:1:setup_count}")
  shift "$setup_count"
  local command=("$@")

  if [[ "$ACTION" == "dry-run" ]]; then
    printf '[dry-run] cd %q &&' "$workdir"
    local setup
    for setup in "${setups[@]}"; do
      printf ' source %q &&' "$setup"
    done
    printf ' exec'
    printf ' %q' "${command[@]}"
    printf '\n'
    return
  fi

  local setup
  for setup in "${setups[@]}"; do
    [[ -f "$setup" ]] || die "required setup file is missing: $setup"
  done
  [[ -d "$workdir" ]] || die "workspace is missing: $workdir"
  /usr/bin/bash --noprofile --norc -c '
    set -euo pipefail
    workdir="$1"
    shift
    setup_count="$1"
    shift
    set +u
    for ((index=0; index<setup_count; index++)); do
      source "$1"
      shift
    done
    set -u
    cd "$workdir"
    exec "$@"
  ' robot-scope-bootstrap "$workdir" "$setup_count" "${setups[@]}" "${command[@]}"
}

install_repository unitree_ros2

if [[ "$MODE" == "go2-xt16" || "$MODE" == "go2-nav" ]]; then
  install_repository hesai_ros2
  install_repository livox_sdk2
  install_repository livox_ros_driver2
  install_repository fast_lio
fi

if [[ "$SKIP_BUILD" == "1" ]]; then
  echo "[Robot Scope bootstrap] source verification complete; builds skipped"
  exit 0
fi

run_with_setups \
  "$WORKSPACE_ROOT/unitree_ros2/cyclonedds_ws" 1 \
  "$ROS_SETUP" \
  colcon build --symlink-install

if [[ "$MODE" == "go2-xt16" || "$MODE" == "go2-nav" ]]; then
  XT16_BRIDGE_PACKAGE="$PROJECT_DIR/ros2/robot_scope_xt16_bridge"
  XT16_BRIDGE_BUILD_ROOT="$PROJECT_DIR/workspaces/ws/xt16_bridge_ws"
  run mkdir -p "$XT16_BRIDGE_BUILD_ROOT"
  run_with_setups \
    "$PROJECT_DIR" 2 \
    "$ROS_SETUP" \
    "$WORKSPACE_ROOT/unitree_ros2/cyclonedds_ws/install/setup.bash" \
    colcon \
      --log-base "$XT16_BRIDGE_BUILD_ROOT/log" \
      build \
      --base-paths "$XT16_BRIDGE_PACKAGE" \
      --build-base "$XT16_BRIDGE_BUILD_ROOT/build" \
      --install-base "$XT16_BRIDGE_BUILD_ROOT/install" \
      --merge-install \
      --cmake-args -DCMAKE_BUILD_TYPE=Release

  LIVOX_SDK_SOURCE="$WORKSPACE_ROOT/ws/livox/Livox-SDK2"
  LIVOX_SDK_BUILD="$WORKSPACE_ROOT/ws/livox/sdk2_build"
  LIVOX_SDK_LIBRARY_PATH="$LIVOX_SDK_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

  run cmake \
    -S "$LIVOX_SDK_SOURCE" \
    -B "$LIVOX_SDK_BUILD" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$LIVOX_SDK_PREFIX" \
    -DCMAKE_INSTALL_LIBDIR=lib
  run cmake --build "$LIVOX_SDK_BUILD" --parallel
  run cmake --install "$LIVOX_SDK_BUILD"
  if [[ "$ACTION" == "apply" ]]; then
    [[ -f "$LIVOX_SDK_PREFIX/lib/liblivox_lidar_sdk_shared.so" ]] || \
      die "Livox-SDK2 shared library was not installed into the private prefix"
    [[ -f "$LIVOX_SDK_PREFIX/include/livox_lidar_api.h" ]] || \
      die "Livox-SDK2 headers were not installed into the private prefix"
  fi

  run_with_setups \
    "$WORKSPACE_ROOT/ws/hesai_ws" 2 \
    "$ROS_SETUP" \
    "$WORKSPACE_ROOT/unitree_ros2/cyclonedds_ws/install/setup.bash" \
    colcon build --symlink-install

  run_with_setups \
    "$WORKSPACE_ROOT/ws/livox/ws_livox/src/livox_ros_driver2" 1 \
    "$ROS_SETUP" \
    /usr/bin/env \
      "CMAKE_LIBRARY_PATH=$LIVOX_SDK_PREFIX/lib" \
      "CMAKE_INCLUDE_PATH=$LIVOX_SDK_PREFIX/include" \
      "LD_LIBRARY_PATH=$LIVOX_SDK_LIBRARY_PATH" \
      /usr/bin/bash ./build.sh humble

  run_with_setups \
    "$WORKSPACE_ROOT/ws/fastlio_ws" 2 \
    "$ROS_SETUP" \
    "$WORKSPACE_ROOT/ws/livox/ws_livox/install/setup.bash" \
    /usr/bin/env \
      "LD_LIBRARY_PATH=$LIVOX_SDK_LIBRARY_PATH" \
      colcon build --symlink-install
fi

echo "[Robot Scope bootstrap] pinned ROS dependencies are ready"
