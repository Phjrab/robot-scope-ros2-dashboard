"""Small reproducible SYNTHETIC benchmark; never writes assets to the checkout."""

import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import numpy as np
from experiments.expansion_20261029.d1_multimap.generate import fixture
from robot_dashboard.multimap_core import solve, export, source_key
from robot_dashboard.relocalization.experimental_se3 import inverse


def main():
    report = {
        "evidence_kind": "SYNTHETIC",
        "device": "DEVICE_NOT_RUN",
        "real_maps": "INPUT_REQUIRED",
        "runs": [],
    }
    with tempfile.TemporaryDirectory(prefix="d1-reproduce-") as temporary:
        root = Path(temporary)
        sources, resolver, truth = fixture(root, 1200, partial=True)
        keys = [source_key(s) for s in sources]
        for count in (2, 3):
            request = dict(
                request_id=f"demo{count}",
                sources=sources[:count],
                anchor_source_key=keys[0],
                mode="seeded",
                initial_guesses=[
                    dict(
                        target=keys[i],
                        source=keys[j],
                        T=(inverse(truth[i]) @ truth[j]).tolist(),
                    )
                    for i in range(count)
                    for j in range(i + 1, count)
                ],
            )
            start = time.process_time()
            proposal = solve(request, resolver)
            proposal["occupancy_surface"] = dict(
                name="synthetic_obstacle_band", z_min=0.3, z_max=2, resolution=0.1
            )
            manifest = export(proposal, 1, resolver, root / "outputs")
            errors = [
                float(
                    np.linalg.norm(
                        np.array(e["T"]) - truth[keys.index(e["source_key"])]
                    )
                )
                for e in proposal["T_fused_source"]
            ]
            report["runs"].append(
                dict(
                    maps=count,
                    status=proposal["status"],
                    elapsed_ms=proposal["elapsed_ms"],
                    cpu_seconds=time.process_time() - start,
                    max_matrix_error=max(errors),
                    full_export_points=manifest["point_count"],
                    occupancy=manifest["occupancy"],
                    max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                )
            )
        request_path = root / "request.json"
        request_path.write_text(json.dumps(request))
        resolver_path = root / "resolver.json"
        resolver_path.write_text(
            json.dumps({s["map_id"]: str(resolver(s)) for s in sources})
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "robot_dashboard.multimap_core",
                str(request_path),
                "--resolver",
                str(resolver_path),
                "--proposal",
                str(root / "proposal.json"),
            ],
            check=True,
            capture_output=True,
        )
        report["cli"] = "PASS"
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
