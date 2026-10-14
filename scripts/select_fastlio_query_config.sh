#!/usr/bin/env bash
# Pure configuration selection. Does not launch ROS or alter DDS/network state.
robot_scope_fastlio_query_config() {
  local profile="$1" opt_in="$2" requested="$3"
  local selected="${requested:-fastlio_xt16.yaml}"
  if [[ "$profile" == "go2-onboard" ]]; then
    case "$opt_in" in
      1)
        selected="fastlio_xt16_d2_relocalization.yaml"
        if [[ -n "$requested" && "$requested" != "$selected" ]]; then
          echo "[Robot Scope] onboard D2 requires the fixed dense FAST-LIO config" >&2
          return 2
        fi
        ;;
      0|"") ;;
      *)
        echo "[Robot Scope] invalid onboard D2 relocalization opt-in" >&2
        return 2
        ;;
    esac
  fi
  case "$selected" in
    fastlio_xt16.yaml|fastlio_xt16_d2_relocalization.yaml) printf '%s\n' "$selected" ;;
    *) echo "[Robot Scope] FAST-LIO config selection is not allowlisted" >&2; return 2 ;;
  esac
}
