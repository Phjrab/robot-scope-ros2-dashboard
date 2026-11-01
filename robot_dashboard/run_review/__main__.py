"""Import local records and produce private browser bundles + allowlisted summaries."""

import argparse
from pathlib import Path

from .dependencies import c1_validator
from .io import read_json, write_new
from .review import load_run
from .summary import compare, markdown, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--compare-manifest")
    validators = parser.add_mutually_exclusive_group()
    validators.add_argument("--deps", type=Path)
    validators.add_argument("--installed-contracts", action="store_true",
                            help="Use I0's installed C1 contract, pinned in SOURCE_LOCK.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate = c1_validator(args.deps) if args.deps else None
    if args.installed_contracts:
        from robot_dashboard.expansion_contracts import ScenePacket
        validate = ScenePacket.from_dict
    run = load_run(args.root, read_json(args.root, args.manifest), validator=validate)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(args.output / "review.private.json", run)
    public = summary(run)
    write_new(args.output / "summary.json", public)
    write_new(args.output / "summary.md", markdown(public))
    if args.compare_manifest:
        second = load_run(
            args.root, read_json(args.root, args.compare_manifest), validator=validate
        )
        write_new(args.output / "compare.private.json", second)
        comparison = compare(run, second)
        write_new(args.output / "comparison.json", comparison)
        write_new(args.output / "comparison.md", markdown(comparison))
    print("REPLAY outputs written; private bundles are not Git artifacts.")


if __name__ == "__main__":
    main()
