"""Export already-fetched exact Git objects outside the repository, read-only."""
import argparse
from pathlib import Path
import subprocess
from .dependencies import PINS, REPO


def prepare(root):
    root = root.resolve()
    if root == REPO or REPO in root.parents:
        raise ValueError('DEPENDENCIES_MUST_BE_EXTERNAL')
    root.mkdir(parents=True, exist_ok=True)
    for role, sha in PINS.items():
        dest=root/f'{role}-{sha}'
        if dest.exists():
            continue
        archive=subprocess.check_output(['git','archive',sha],cwd=REPO)
        dest.mkdir()
        subprocess.run(['tar','-xf','-','-C',str(dest)],input=archive,check=True)
        subprocess.run(['chmod','-R','a-w',str(dest)],check=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    prepare(parser.parse_args().root)
