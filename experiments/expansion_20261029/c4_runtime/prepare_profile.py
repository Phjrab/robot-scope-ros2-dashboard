"""Generate review-only parameters. D3 supplies a conservative envelope radius."""
import argparse
from pathlib import Path
import yaml
from robot_dashboard.obstacle_runtime_adapter.nav2 import launch_parameters


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, default=Path("config/nav2_params_go2_humble.yaml"))
    p.add_argument("--envelope-radius-m", type=float, required=True)
    p.add_argument("--padding-m", type=float, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    data = launch_parameters(yaml.safe_load(a.base.read_text()), envelope_radius_m=a.envelope_radius_m,
                             safety_padding_m=a.padding_m)
    with a.output.open("x") as stream:
        yaml.safe_dump(data, stream, sort_keys=False)
    print("SYNTHETIC_PROFILE_GENERATED; native effective readback NOT_RUN")


if __name__ == "__main__":
    main()
