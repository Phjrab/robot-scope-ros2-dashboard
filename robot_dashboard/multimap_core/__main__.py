"""Trusted local CLI. Resolver paths are never accepted by an HTTP endpoint."""

import argparse
import json
from pathlib import Path
from . import solve, export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument(
        "--resolver",
        type=Path,
        required=True,
        help="private map_id -> full-source path JSON",
    )
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--export-root", type=Path)
    args = parser.parse_args()
    mapping = json.loads(args.resolver.read_text())
    request = json.loads(args.request.read_text())
    proposal = solve(request, lambda d: Path(mapping[d["map_id"]]))
    with args.proposal.open("x") as f:
        json.dump(proposal, f, indent=2, allow_nan=False)
    if args.export_root:
        result = export(
            proposal,
            proposal["proposal_revision"],
            lambda d: Path(mapping[d["map_id"]]),
            args.export_root,
        )
        print(json.dumps(result, allow_nan=False))
    else:
        print(proposal["status"])
    return 0 if proposal["status"] == "SOLVED_CANDIDATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
