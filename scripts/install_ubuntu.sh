#!/usr/bin/env bash
set -euo pipefail

# Platform-aware, noninteractive bootstrap for an existing Robot Scope clone.
# The default action is a read-only dry run. --apply is the mutation gate;
# privileged package/service changes require a second, explicit opt-in.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DEFAULT_PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

MODE="observer"
PROJECT_DIR="$DEFAULT_PROJECT_DIR"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/robot-scope"
ENV_FILE=""
OS_RELEASE_FILE="/etc/os-release"
ACTION="--dry-run"
SKIP_PYTHON_DEPS=0
JSON_DOCTOR=0
INSTALL_SYSTEM_PACKAGES=0
INSTALL_SERVICE=0
SERVICE_TEMP_DIR=""
APT_SOURCE_TEMP_DIR=""

usage() {
  cat <<'EOF'
usage: install_ubuntu.sh [OPTIONS]

Bootstrap Robot Scope on Ubuntu 22.04/Humble or Ubuntu 24.04/Jazzy.
The Jazzy platform currently supports observer mode only. Jetson is optional.
The default is a read-only dry run. Run this installer as the target user,
never as root. Privileged actions use sudo only with an explicit opt-in.

Options:
  --mode MODE                  observer | go2 | go2-control | go2-xt16 | go2-nav
                               (default: observer)
  --project-dir DIR            existing Robot Scope checkout
  --config-dir DIR             private configuration directory
  --env-file FILE              general environment file
                               (default: CONFIG_DIR/robot-scope.env)
  --os-release FILE            os-release file used by the doctor
  --apply                      create missing user files/venv and dependencies
  --dry-run                    print and probe without changing files (default)
  --install-system-packages    with --apply, install manifest apt packages and
                               the checksum-verified official ROS apt source
  --install-service            with --apply, render/verify/install systemd units
                               without enabling or starting them
  --skip-python-deps           do not invoke pip during --apply
  --json-doctor                emit the final doctor report as JSON
  -h, --help                   show this help

Mode contract:
  observer     Web dashboard and standard ROS 2 observation.
  go2          observer + Unitree/CycloneDDS host integration.
  go2-control  go2 + signed fail-closed motion bridge prerequisites.
  go2-xt16     go2 + Hesai, XT16 bridge, FAST-LIO and map-save prerequisites.
  go2-nav      go2-control + go2-xt16 + Nav2 prerequisites.

go2-control/go2-nav --apply explicitly configures the signed bridge (including
a private key) but never enables or starts a service, arms the robot, or sends
motion.
ROBOT_SCOPE_WORKSPACE_ROOT in robot-scope.env must be absolute; blank
uses the target user's HOME for bootstrap, diagnostics, and runtime services.

The systemd option never installs lifecycle sudoers or the robot-side XT16
relay. It does install the fixed, root-owned robot-scope-dashboard SSH helper,
but its exact-command sudoers policy remains a separate administrator step.
The dashboard unit reads robot-scope.env and optional control.env; the control
bridge unit (control/nav modes) requires both files.
Robot-side RealSense relay env/service installation is also a separate reviewed
operation. This installer never writes deployment IPs or credentials into the
repository and never enables or starts that relay.
EOF
}

die() {
  echo "[Robot Scope installer] $*" >&2
  exit 2
}

print_command() {
  printf '[dry-run]'
  printf ' %q' "$@"
  printf '\n'
}

cleanup_service_temp() {
  if [[ -n "$SERVICE_TEMP_DIR" && -d "$SERVICE_TEMP_DIR" ]]; then
    rm -f -- \
      "$SERVICE_TEMP_DIR/robot-scope.service" \
      "$SERVICE_TEMP_DIR/robot-scope-control-bridge.service" \
      "$SERVICE_TEMP_DIR/robot-scope-dashboard-operator.port"
    rmdir -- "$SERVICE_TEMP_DIR" 2>/dev/null || true
  fi
  if [[ -n "$APT_SOURCE_TEMP_DIR" && -d "$APT_SOURCE_TEMP_DIR" ]]; then
    rm -f -- "$APT_SOURCE_TEMP_DIR/ros2-apt-source.deb"
    rmdir -- "$APT_SOURCE_TEMP_DIR" 2>/dev/null || true
  fi
}
trap cleanup_service_temp EXIT

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ "$#" -ge 2 ]] || die "--mode requires a value"
      MODE="$2"
      shift 2
      ;;
    --project-dir)
      [[ "$#" -ge 2 ]] || die "--project-dir requires a value"
      PROJECT_DIR="$2"
      shift 2
      ;;
    --config-dir)
      [[ "$#" -ge 2 ]] || die "--config-dir requires a value"
      CONFIG_DIR="$2"
      shift 2
      ;;
    --env-file)
      [[ "$#" -ge 2 ]] || die "--env-file requires a value"
      ENV_FILE="$2"
      shift 2
      ;;
    --os-release)
      [[ "$#" -ge 2 ]] || die "--os-release requires a value"
      OS_RELEASE_FILE="$2"
      shift 2
      ;;
    --apply)
      ACTION="--apply"
      shift
      ;;
    --dry-run)
      ACTION="--dry-run"
      shift
      ;;
    --install-system-packages)
      INSTALL_SYSTEM_PACKAGES=1
      shift
      ;;
    --install-service)
      INSTALL_SERVICE=1
      shift
      ;;
    --skip-python-deps)
      SKIP_PYTHON_DEPS=1
      shift
      ;;
    --json-doctor)
      JSON_DOCTOR=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$MODE" in
  observer|go2|go2-control|go2-xt16|go2-nav) ;;
  *) die "unsupported mode: $MODE" ;;
esac

[[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]] || die "project directory does not exist"
PROJECT_DIR="$(cd -- "$PROJECT_DIR" && pwd -P)"
[[ -n "$CONFIG_DIR" && "$CONFIG_DIR" != "/" ]] || die "unsafe configuration directory"
if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="$CONFIG_DIR/robot-scope.env"
fi
[[ -n "$ENV_FILE" && "$ENV_FILE" != "/" ]] || die "unsafe environment file path"
ENV_DIR="$(dirname -- "$ENV_FILE")"
CONTROL_ENV_FILE="$ENV_DIR/control.env"

REQUIREMENTS="$PROJECT_DIR/requirements.txt"
ENV_TEMPLATE="$PROJECT_DIR/deploy/robot-scope.env.example"
DOCTOR="$PROJECT_DIR/scripts/robot_scope_doctor.py"
EXTERNAL_BOOTSTRAP="$PROJECT_DIR/scripts/bootstrap_ros_dependencies.sh"
VENV_DIR="$PROJECT_DIR/.venv"
OPERATOR_SOURCE="$PROJECT_DIR/scripts/robot_scope_dashboard_service.py"

[[ -f "$REQUIREMENTS" ]] || die "requirements.txt is missing from the project"
[[ -f "$ENV_TEMPLATE" ]] || die "deploy/robot-scope.env.example is missing"
[[ -f "$DOCTOR" ]] || die "scripts/robot_scope_doctor.py is missing"
[[ -x "$EXTERNAL_BOOTSTRAP" ]] || die "pinned dependency bootstrap is missing or not executable"
if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
  [[ -x "$OPERATOR_SOURCE" ]] || die "dashboard SSH operator helper is missing or not executable"
fi
command -v python3 >/dev/null 2>&1 || die "python3 is required"

os_id="$(awk -F= '$1 == "ID" {value=$2; gsub(/^["'"'"']|["'"'"']$/, "", value); print tolower(value); exit}' "$OS_RELEASE_FILE" 2>/dev/null || true)"
os_version="$(awk -F= '$1 == "VERSION_ID" {value=$2; gsub(/^["'"'"']|["'"'"']$/, "", value); print value; exit}' "$OS_RELEASE_FILE" 2>/dev/null || true)"
case "$os_id:$os_version" in
  ubuntu:22.04)
    ROS_DISTRO_NAME="humble"
    UBUNTU_CODENAME="jammy"
    ;;
  ubuntu:24.04)
    ROS_DISTRO_NAME="jazzy"
    UBUNTU_CODENAME="noble"
    [[ "$MODE" == "observer" ]] || \
      die "Ubuntu 24.04 / ROS 2 Jazzy currently supports observer mode only"
    ;;
  *)
    ROS_DISTRO_NAME="${ROS_DISTRO:-humble}"
    case "$ROS_DISTRO_NAME" in
      humble) UBUNTU_CODENAME="jammy" ;;
      jazzy) UBUNTU_CODENAME="noble" ;;
      *) die "unsupported ROS_DISTRO for installation planning: $ROS_DISTRO_NAME" ;;
    esac
    ;;
esac
DEPENDENCY_MANIFEST="$PROJECT_DIR/config/ros_dependencies_${ROS_DISTRO_NAME}.json"
[[ -f "$DEPENDENCY_MANIFEST" ]] || \
  die "pinned dependency manifest is missing: $DEPENDENCY_MANIFEST"

literal_env_value() {
  local key="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    return 0
  fi
  python3 - "$ENV_FILE" "$key" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", key):
    raise SystemExit("invalid requested environment key")
value = ""
for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[7:].lstrip()
    if not line.startswith(key + "="):
        continue
    candidate = line.split("=", 1)[1].strip()
    if candidate[:1] in {"'", '"'}:
        if len(candidate) < 2 or candidate[-1] != candidate[0]:
            raise SystemExit(f"unterminated workspace root on line {number}")
        candidate = candidate[1:-1]
    value = candidate
if "\x00" in value or "\n" in value or "\r" in value:
    raise SystemExit("workspace root contains control characters")
print(value)
PY
}

WORKSPACE_ROOT_VALUE="$(literal_env_value ROBOT_SCOPE_WORKSPACE_ROOT)"
case "$WORKSPACE_ROOT_VALUE" in
  "") WORKSPACE_ROOT="$HOME" ;;
  /*) WORKSPACE_ROOT="$WORKSPACE_ROOT_VALUE" ;;
  *) die "ROBOT_SCOPE_WORKSPACE_ROOT must be blank or absolute" ;;
esac
[[ -n "$WORKSPACE_ROOT" && "$WORKSPACE_ROOT" != "/" ]] || die "unsafe workspace root"

LIVOX_SDK_PREFIX_VALUE="$(literal_env_value ROBOT_SCOPE_LIVOX_SDK_PREFIX)"
case "$LIVOX_SDK_PREFIX_VALUE" in
  "") LIVOX_SDK_PREFIX="$WORKSPACE_ROOT/ws/livox/sdk2_install" ;;
  /*) LIVOX_SDK_PREFIX="$LIVOX_SDK_PREFIX_VALUE" ;;
  *) die "ROBOT_SCOPE_LIVOX_SDK_PREFIX must be blank or absolute" ;;
esac
[[ -n "$LIVOX_SDK_PREFIX" && "$LIVOX_SDK_PREFIX" != "/" ]] || die "unsafe Livox SDK prefix"

ROBOT_SCOPE_PORT_VALUE="$(literal_env_value ROBOT_SCOPE_PORT)"
if [[ -z "$ROBOT_SCOPE_PORT_VALUE" ]]; then
  ROBOT_SCOPE_PORT_VALUE="8088"
fi
[[ "$ROBOT_SCOPE_PORT_VALUE" =~ ^[1-9][0-9]{0,4}$ ]] || \
  die "ROBOT_SCOPE_PORT must be an integer from 1 to 65535"
((10#$ROBOT_SCOPE_PORT_VALUE <= 65535)) || \
  die "ROBOT_SCOPE_PORT must be an integer from 1 to 65535"

ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE="$(literal_env_value ROBOT_SCOPE_DASHBOARD_ADDRESS)"
if [[ -n "$ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE" ]]; then
  if ! ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE="$(python3 - "$ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError:
    raise SystemExit(1)
networks = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
)
if (
    address.version != 4
    or not any(address in network for network in networks)
    or address.is_loopback
    or address.is_multicast
    or address.is_unspecified
):
    raise SystemExit(1)
print(address)
PY
)"; then
    die "ROBOT_SCOPE_DASHBOARD_ADDRESS must be an explicit private or link-local host IPv4"
  fi
fi

APT_PACKAGES=()
while IFS= read -r package; do
  [[ -n "$package" ]] && APT_PACKAGES+=("$package")
done < <(python3 - "$DEPENDENCY_MANIFEST" "$MODE" "$ROS_DISTRO_NAME" "$UBUNTU_CODENAME" <<'PY'
import json
import pathlib
import re
import sys

manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
mode = sys.argv[2]
ros_distro = sys.argv[3]
ubuntu_codename = sys.argv[4]
if manifest.get("ros_distro") != ros_distro or manifest.get("ubuntu_codename") != ubuntu_codename:
    raise SystemExit(
        f"dependency manifest does not match ROS {ros_distro} on Ubuntu {ubuntu_codename}"
    )
groups = ["base", "ros"]
if mode != "observer":
    groups.append("camera")
if mode == "go2-nav":
    groups.append("navigation")
packages = []
for group in groups:
    values = manifest.get("apt_groups", {}).get(group)
    if not isinstance(values, list):
        raise SystemExit(f"dependency manifest apt group is missing: {group}")
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", value):
            raise SystemExit(f"invalid apt package in manifest group {group}")
        if value not in packages:
            packages.append(value)
print("\n".join(packages))
PY
)
[[ "${#APT_PACKAGES[@]}" -gt 0 ]] || die "dependency manifest selected no apt packages"

ROS_APT_SOURCE=()
while IFS= read -r value; do
  ROS_APT_SOURCE+=("$value")
done < <(python3 - "$DEPENDENCY_MANIFEST" "$UBUNTU_CODENAME" <<'PY'
import json
import pathlib
import re
import sys

source = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")).get("ros_apt_source", {})
ubuntu_codename = sys.argv[2]
version = source.get("version", "")
url = source.get("url", "")
sha256 = source.get("sha256", "")
if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version):
    raise SystemExit("invalid ROS apt source version in dependency manifest")
if not isinstance(url, str) or not url.startswith("https://github.com/ros-infrastructure/ros-apt-source/releases/"):
    raise SystemExit("invalid ROS apt source URL in dependency manifest")
if not url.endswith(f".{ubuntu_codename}_all.deb"):
    raise SystemExit(f"ROS apt source URL does not match Ubuntu {ubuntu_codename}")
if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
    raise SystemExit("invalid ROS apt source SHA-256 in dependency manifest")
print(version)
print(url)
print(sha256)
PY
)
[[ "${#ROS_APT_SOURCE[@]}" -eq 3 ]] || die "ROS apt source metadata is incomplete"
ROS_APT_SOURCE_VERSION="${ROS_APT_SOURCE[0]}"
ROS_APT_SOURCE_URL="${ROS_APT_SOURCE[1]}"
ROS_APT_SOURCE_SHA256="${ROS_APT_SOURCE[2]}"

package_guidance() {
  printf '%s' "${APT_PACKAGES[0]}"
  local package
  for package in "${APT_PACKAGES[@]:1}"; do
    printf ' %s' "$package"
  done
  printf '\n'
}

plan_system_packages() {
  echo "[Robot Scope installer] would enable Ubuntu Universe"
  print_command sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get update
  print_command sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get install --yes \
    ca-certificates curl gnupg lsb-release software-properties-common
  print_command sudo /usr/bin/add-apt-repository --yes universe
  print_command curl --fail --location --proto =https --tlsv1.2 \
    --output "/tmp/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${UBUNTU_CODENAME}_all.deb" \
    "$ROS_APT_SOURCE_URL"
  echo "[Robot Scope installer] would verify ROS apt source SHA-256: $ROS_APT_SOURCE_SHA256"
  print_command sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get install --yes \
    "/tmp/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${UBUNTU_CODENAME}_all.deb"
  print_command sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get update
  print_command sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get install --yes \
    "${APT_PACKAGES[@]}"
}

sudo_apt() {
  sudo /usr/bin/env DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get "$@"
}

install_system_packages() {
  command -v sudo >/dev/null 2>&1 || die "sudo is required for system package installation"
  sudo -v
  sudo_apt update
  sudo_apt install --yes \
    ca-certificates curl gnupg lsb-release software-properties-common
  sudo /usr/bin/add-apt-repository --yes universe
  sudo_apt update

  command -v curl >/dev/null 2>&1 || die "curl installation failed"
  command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
  local apt_source_deb actual_sha256
  APT_SOURCE_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/robot-scope-ros-apt.XXXXXX")"
  apt_source_deb="$APT_SOURCE_TEMP_DIR/ros2-apt-source.deb"
  curl --fail --location --proto '=https' --tlsv1.2 \
    --output "$apt_source_deb" "$ROS_APT_SOURCE_URL"
  actual_sha256="$(sha256sum "$apt_source_deb" | awk '{print $1}')"
  if [[ "$actual_sha256" != "$ROS_APT_SOURCE_SHA256" ]]; then
    die "ROS apt source checksum mismatch"
  fi
  sudo_apt install --yes "$apt_source_deb"
  rm -f -- "$apt_source_deb"
  rmdir -- "$APT_SOURCE_TEMP_DIR" 2>/dev/null || true
  APT_SOURCE_TEMP_DIR=""
  sudo_apt update

  sudo_apt install --yes "${APT_PACKAGES[@]}"
}

doctor_command=(
  python3 "$DOCTOR"
  --mode "$MODE"
  --project-dir "$PROJECT_DIR"
  --env-file "$ENV_FILE"
  --os-release "$OS_RELEASE_FILE"
  --allow-hardware-offline
)
if [[ "$JSON_DOCTOR" -eq 1 ]]; then
  doctor_command+=(--json)
fi

if [[ "$ACTION" == "--dry-run" ]]; then
  echo "[Robot Scope installer] DRY RUN (no files or services will be changed)"
  echo "[Robot Scope installer] mode=$MODE"
  echo "[Robot Scope installer] project=$PROJECT_DIR"
  echo "[Robot Scope installer] environment=$ENV_FILE"
  echo "[Robot Scope installer] workspace-root=$WORKSPACE_ROOT"
  echo "[Robot Scope installer] livox-sdk-prefix=$LIVOX_SDK_PREFIX"
  echo "[Robot Scope installer] platform=Ubuntu ${os_version:-unknown} / ROS 2 $ROS_DISTRO_NAME"
  echo "[Robot Scope installer] supported=Ubuntu 22.04/Humble (all modes); Ubuntu 24.04/Jazzy (observer); x86_64/arm64"
  echo "[Robot Scope installer] Ubuntu package guidance: $(package_guidance)"
  if [[ "$INSTALL_SYSTEM_PACKAGES" -eq 1 ]]; then
    plan_system_packages
  else
    echo "[Robot Scope installer] system packages are check-only (use --install-system-packages with --apply)"
  fi
  if [[ -e "$ENV_FILE" ]]; then
    echo "[Robot Scope installer] preserve existing environment file: $ENV_FILE"
  else
    echo "[Robot Scope installer] would create private environment file: $ENV_FILE"
  fi
  if [[ "$MODE" == "go2-control" || "$MODE" == "go2-nav" ]]; then
    if [[ -e "$CONTROL_ENV_FILE" ]]; then
      echo "[Robot Scope installer] preserve existing control secret file: $CONTROL_ENV_FILE"
    else
      echo "[Robot Scope installer] would generate private control secret file: $CONTROL_ENV_FILE"
    fi
  fi
  if [[ -e "$VENV_DIR" ]]; then
    echo "[Robot Scope installer] preserve and reuse existing venv: $VENV_DIR"
  else
    echo "[Robot Scope installer] would create system-site-packages venv: $VENV_DIR"
  fi
  if [[ "$SKIP_PYTHON_DEPS" -eq 1 ]]; then
    echo "[Robot Scope installer] would skip Python dependency installation"
  else
    echo "[Robot Scope installer] would install pinned-range Python requirements"
  fi
  if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
    echo "[Robot Scope installer] would render and verify robot-scope.service"
    if [[ "$MODE" == "go2-control" || "$MODE" == "go2-nav" ]]; then
      echo "[Robot Scope installer] would render and verify robot-scope-control-bridge.service"
    fi
    print_command sudo install -o root -g root -m 0644 \
      generated.service /etc/systemd/system/
    print_command sudo install -o root -g root -m 0755 \
      "$OPERATOR_SOURCE" /usr/local/bin/robot-scope-dashboard
    echo "[Robot Scope installer] would install root-owned operator port: $ROBOT_SCOPE_PORT_VALUE"
    if [[ -n "$ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE" ]]; then
      echo "[Robot Scope installer] would install root-owned operator address: $ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE"
    else
      echo "[Robot Scope installer] would install automatic dashboard address selection"
    fi
    print_command sudo systemctl daemon-reload
    echo "[Robot Scope installer] would leave Robot Scope services disabled and stopped"
  else
    echo "[Robot Scope installer] systemd service installation is disabled"
  fi
  ROBOT_SCOPE_LIVOX_SDK_PREFIX="$LIVOX_SDK_PREFIX" \
    "$EXTERNAL_BOOTSTRAP" --mode "$MODE" --manifest "$DEPENDENCY_MANIFEST" \
      --dry-run --workspace-root "$WORKSPACE_ROOT"
  doctor_status=0
  ROBOT_SCOPE_WORKSPACE_ROOT="$WORKSPACE_ROOT" \
    ROBOT_SCOPE_LIVOX_SDK_PREFIX="$LIVOX_SDK_PREFIX" \
    "${doctor_command[@]}" || doctor_status=$?
  echo "[Robot Scope installer] current doctor status=$doctor_status (dry-run remains read-only)"
  exit 0
fi

[[ "$(uname -s)" == "Linux" ]] || die "--apply is supported only on Ubuntu Linux"
[[ "$EUID" -ne 0 ]] || die "run --apply as the target non-root user, not root"
case "$(uname -m)" in
  x86_64|amd64|aarch64|arm64) ;;
  *) die "--apply supports only x86_64 or arm64" ;;
esac

if [[ "$OS_RELEASE_FILE" != "/etc/os-release" ]]; then
  actual_os_id="$(awk -F= '$1 == "ID" {value=$2; gsub(/^"|"$/, "", value); print tolower(value); exit}' /etc/os-release 2>/dev/null || true)"
  actual_os_version="$(awk -F= '$1 == "VERSION_ID" {value=$2; gsub(/^"|"$/, "", value); print value; exit}' /etc/os-release 2>/dev/null || true)"
  [[ "$actual_os_id:$actual_os_version" == "$os_id:$os_version" ]] || \
    die "--apply os-release override must match the running host"
fi

case "$os_id:$os_version:$ROS_DISTRO_NAME" in
  ubuntu:22.04:humble|ubuntu:24.04:jazzy) ;;
  *) die "--apply requires Ubuntu 22.04/Humble or Ubuntu 24.04/Jazzy" ;;
esac

if [[ "$INSTALL_SYSTEM_PACKAGES" -eq 1 ]]; then
  install_system_packages
elif [[ ! -f "/opt/ros/$ROS_DISTRO_NAME/setup.bash" ]]; then
  die "ROS 2 $ROS_DISTRO_NAME is missing; rerun with --install-system-packages"
fi

if [[ -L "$ENV_DIR" ]]; then
  die "refusing symlink environment directory: $ENV_DIR"
fi
mkdir -p -- "$ENV_DIR"
chmod 700 -- "$ENV_DIR"

if [[ -L "$ENV_FILE" ]]; then
  die "refusing symlink environment file: $ENV_FILE"
elif [[ -e "$ENV_FILE" && ! -f "$ENV_FILE" ]]; then
  die "environment path exists but is not a regular file: $ENV_FILE"
elif [[ -f "$ENV_FILE" ]]; then
  echo "[Robot Scope installer] preserving existing environment file: $ENV_FILE"
else
  install -m 600 -- "$ENV_TEMPLATE" "$ENV_FILE"
  echo "[Robot Scope installer] created private environment template: $ENV_FILE"
fi

if [[ "$MODE" == "go2-control" || "$MODE" == "go2-nav" ]]; then
  if [[ -L "$CONTROL_ENV_FILE" ]]; then
    die "refusing symlink control environment file: $CONTROL_ENV_FILE"
  elif [[ -e "$CONTROL_ENV_FILE" && ! -f "$CONTROL_ENV_FILE" ]]; then
    die "control environment path exists but is not a regular file"
  elif [[ -f "$CONTROL_ENV_FILE" ]]; then
    echo "[Robot Scope installer] preserving existing control secret file: $CONTROL_ENV_FILE"
  else
    control_key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    (
      umask 077
      set -C
      printf 'ROBOT_SCOPE_CONTROL_ENABLED=1\nROBOT_SCOPE_CONTROL_BRIDGE_KEY=%s\n' \
        "$control_key" > "$CONTROL_ENV_FILE"
    ) || die "control secret file appeared concurrently; preserving it"
    unset control_key
    chmod 600 -- "$CONTROL_ENV_FILE"
    echo "[Robot Scope installer] generated private control secret file: $CONTROL_ENV_FILE"
  fi
fi

ROBOT_SCOPE_LIVOX_SDK_PREFIX="$LIVOX_SDK_PREFIX" \
  "$EXTERNAL_BOOTSTRAP" --mode "$MODE" --manifest "$DEPENDENCY_MANIFEST" \
    --apply --workspace-root "$WORKSPACE_ROOT"

if [[ -L "$VENV_DIR" ]]; then
  die "refusing symlink virtual environment: $VENV_DIR"
elif [[ -e "$VENV_DIR" && ! -x "$VENV_DIR/bin/python" ]]; then
  die "existing .venv is not a usable Python virtual environment; preserving it"
elif [[ ! -e "$VENV_DIR" ]]; then
  python3 -m venv --system-site-packages "$VENV_DIR"
  echo "[Robot Scope installer] created virtual environment: $VENV_DIR"
else
  echo "[Robot Scope installer] reusing virtual environment: $VENV_DIR"
fi

if [[ "$SKIP_PYTHON_DEPS" -eq 0 ]]; then
  "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"
else
  echo "[Robot Scope installer] skipped Python dependencies by request"
fi

doctor_command[0]="$VENV_DIR/bin/python"
ROBOT_SCOPE_WORKSPACE_ROOT="$WORKSPACE_ROOT" \
  ROBOT_SCOPE_LIVOX_SDK_PREFIX="$LIVOX_SDK_PREFIX" \
  "${doctor_command[@]}"

safe_systemd_path() {
  [[ "$1" =~ ^/[A-Za-z0-9_./:@,+-]+$ ]]
}

install_services() {
  command -v sudo >/dev/null 2>&1 || die "sudo is required for systemd installation"
  local service_user dashboard_exec operator_target operator_port_target
  service_user="$(id -un)"
  [[ "$service_user" =~ ^[A-Za-z_][A-Za-z0-9_-]{0,63}$ ]] || \
    die "current username cannot be rendered safely into a systemd unit"
  safe_systemd_path "$HOME" || die "HOME path contains unsupported systemd characters"
  safe_systemd_path "$PROJECT_DIR" || die "project path contains unsupported systemd characters"
  safe_systemd_path "$ENV_FILE" || die "environment path contains unsupported systemd characters"
  safe_systemd_path "$CONTROL_ENV_FILE" || die "control env path contains unsupported systemd characters"

  if [[ "$MODE" == "observer" ]]; then
    dashboard_exec="$PROJECT_DIR/scripts/run_generic.sh"
  else
    dashboard_exec="$PROJECT_DIR/scripts/run_go2_dashboard_supervisor.py"
  fi
  [[ -x "$dashboard_exec" ]] || die "dashboard service executable is missing"
  operator_target="/usr/local/bin/robot-scope-dashboard"
  operator_port_target="/etc/robot-scope-dashboard-operator.port"
  operator_address_target="/etc/robot-scope-dashboard-operator.address"
  [[ -x "$OPERATOR_SOURCE" ]] || die "dashboard SSH operator helper is missing or not executable"
  if [[ -e "$operator_target" || -L "$operator_target" ]]; then
    [[ -f "$operator_target" && ! -L "$operator_target" ]] || \
      die "refusing non-regular dashboard SSH operator helper: $operator_target"
    [[ "$(stat -c '%u:%g:%a' -- "$operator_target" 2>/dev/null || true)" == "0:0:755" ]] || \
      die "refusing unmanaged dashboard SSH operator helper: $operator_target"
  fi
  if [[ -e "$operator_port_target" || -L "$operator_port_target" ]]; then
    [[ -f "$operator_port_target" && ! -L "$operator_port_target" ]] || \
      die "refusing non-regular dashboard operator port config: $operator_port_target"
    [[ "$(stat -c '%u:%g:%a' -- "$operator_port_target" 2>/dev/null || true)" == "0:0:644" ]] || \
      die "refusing unmanaged dashboard operator port config: $operator_port_target"
  fi
  if [[ -e "$operator_address_target" || -L "$operator_address_target" ]]; then
    [[ -f "$operator_address_target" && ! -L "$operator_address_target" ]] || \
      die "refusing non-regular dashboard operator address config: $operator_address_target"
    [[ "$(stat -c '%u:%g:%a' -- "$operator_address_target" 2>/dev/null || true)" == "0:0:644" ]] || \
      die "refusing unmanaged dashboard operator address config: $operator_address_target"
  fi

  SERVICE_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/robot-scope-units.XXXXXX")"
  local operator_port_source="$SERVICE_TEMP_DIR/robot-scope-dashboard-operator.port"
  printf '%s\n' "$ROBOT_SCOPE_PORT_VALUE" > "$operator_port_source"
  chmod 0644 -- "$operator_port_source"
  local operator_address_source="$SERVICE_TEMP_DIR/robot-scope-dashboard-operator.address"
  printf '%s\n' "$ROBOT_SCOPE_DASHBOARD_ADDRESS_VALUE" > "$operator_address_source"
  chmod 0644 -- "$operator_address_source"
  local dashboard_unit="$SERVICE_TEMP_DIR/robot-scope.service"
  {
    printf '%s\n' \
      '[Unit]' \
      'Description=Robot Scope ROS 2 dashboard' \
      'Wants=network-online.target' \
      'After=network-online.target' \
      '' \
      '[Service]' \
      'Type=simple' \
      "User=$service_user" \
      "WorkingDirectory=$PROJECT_DIR" \
      "EnvironmentFile=-$ENV_FILE" \
      "EnvironmentFile=-$CONTROL_ENV_FILE" \
      "ExecStart=$dashboard_exec" \
      'Restart=on-failure' \
      'RestartSec=3' \
      'KillMode=mixed' \
      "Environment=HOME=$HOME" \
      'Environment=PYTHONUNBUFFERED=1' \
      '' \
      '[Install]' \
      'WantedBy=multi-user.target'
  } > "$dashboard_unit"

  local units=("$dashboard_unit")
  local unit_names=("robot-scope.service")
  if [[ "$MODE" == "go2-control" || "$MODE" == "go2-nav" ]]; then
    local bridge_exec="$PROJECT_DIR/scripts/run_go2_control_bridge_supervisor.sh"
    [[ -x "$bridge_exec" ]] || die "control bridge service executable is missing"
    [[ -f "$CONTROL_ENV_FILE" ]] || die "control bridge requires control.env"
    local bridge_unit="$SERVICE_TEMP_DIR/robot-scope-control-bridge.service"
    {
      printf '%s\n' \
        '[Unit]' \
        'Description=Robot Scope Go2 control safety bridge' \
        'Wants=network-online.target' \
        'After=network-online.target' \
        'StartLimitIntervalSec=60' \
        'StartLimitBurst=5' \
        '' \
        '[Service]' \
        'Type=simple' \
        "User=$service_user" \
        "WorkingDirectory=$PROJECT_DIR" \
        "EnvironmentFile=$ENV_FILE" \
        "EnvironmentFile=$CONTROL_ENV_FILE" \
        "ExecStart=$bridge_exec" \
        'Restart=on-failure' \
        'RestartSec=3' \
        'KillSignal=SIGINT' \
        'TimeoutStopSec=2' \
        'KillMode=control-group' \
        "Environment=HOME=$HOME" \
        'Environment=PYTHONUNBUFFERED=1' \
        '' \
        '[Install]' \
        'WantedBy=multi-user.target'
    } > "$bridge_unit"
    units+=("$bridge_unit")
    unit_names+=("robot-scope-control-bridge.service")
  fi

  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "${units[@]}"
  else
    echo "[Robot Scope installer] warning: systemd-analyze unavailable; unit verification skipped" >&2
  fi
  local index
  for ((index=0; index<${#units[@]}; index++)); do
    local target="/etc/systemd/system/${unit_names[$index]}"
    if [[ -e "$target" || -L "$target" ]]; then
      if [[ -f "$target" && ! -L "$target" ]] && cmp -s -- "${units[$index]}" "$target"; then
        echo "[Robot Scope installer] preserving identical installed unit: $target"
      else
        die "refusing to overwrite existing systemd unit: $target"
      fi
    else
      sudo install -o root -g root -m 0644 -- "${units[$index]}" "$target"
    fi
  done
  sudo install -o root -g root -m 0755 -- "$OPERATOR_SOURCE" "$operator_target"
  sudo install -o root -g root -m 0644 -- "$operator_port_source" "$operator_port_target"
  sudo install -o root -g root -m 0644 -- "$operator_address_source" "$operator_address_target"
  sudo systemctl daemon-reload
  echo "[Robot Scope installer] installed without enabling: ${unit_names[*]}"
  echo "[Robot Scope installer] installed SSH operator helper: $operator_target"
  echo "[Robot Scope installer] operator sudoers remains a separate explicit admin step"
  echo "[Robot Scope installer] existing enablement was unchanged; start explicitly when needed"
}

if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
  install_services
fi

echo "[Robot Scope installer] installation checks passed for mode=$MODE"
