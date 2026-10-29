"""Export already-fetched exact commits to new read-only directories.

Fetch the SHAs in pins.json explicitly before running. No checkout/index changes,
network calls, or counterpart copies into the C1 source tree are performed here.
"""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--parent", type=Path, default=Path("/tmp"))
    args = p.parse_args()
    root = Path(tempfile.mkdtemp(prefix="c1-round2-deps-", dir=args.parent))
    pins = json.loads(Path(__file__).with_name("pins.json").read_text())
    for role, sha in pins.items():
        subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], check=True)
        target = root / role
        target.mkdir()
        archive = root / (role + ".tar")
        with archive.open("wb") as f:
            subprocess.run(["git", "archive", sha], stdout=f, check=True)
        subprocess.run(["tar", "-xf", str(archive), "-C", str(target)], check=True)
        archive.unlink()
        (target / ".c1-dependency-sha").write_text(sha + "\n")
        for path in target.rglob("*"):
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
        target.chmod(0o555)
    (root / "pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    print(root)


if __name__ == "__main__":
    main()
