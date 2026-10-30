"""Exact read-only updated owner exports, loaded in a separate interpreter."""
import hashlib
import os
from pathlib import Path
import subprocess
from experiments.expansion_20261029.c4_runtime.round2.dependencies import PREFIXES, REPO

PINS = {
    'c1': 'e0bc9cf8ba8bd22b406a287e1a9ef867a0cd367b',
    'c3': 'e394b090221c555cf0649021d132163596c19fe2',
    'd2': '7313f0a31c00ae87ae216b84ca41a23804e91917',
    'd3': '356d0a036eb62d546e159e12a0691d7f5ea278f6',
}


def load():
    import robot_dashboard
    root = Path(os.environ['C4_ROS_DEP_ROOT']).resolve()
    paths = {}
    for role, sha in PINS.items():
        export = root / f'{role}-{sha}'
        tree = subprocess.check_output(['git','ls-tree','-r',sha,'--',*PREFIXES[role]],cwd=REPO,text=True)
        if not tree.strip():
            raise RuntimeError('PINNED_TREE_MISSING:'+role)
        for row in tree.splitlines():
            info,name=row.split('\t'); path=export/name; raw=path.read_bytes()
            actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if actual!=info.split()[2] or path.stat().st_mode & 0o222:
                raise RuntimeError('DEPENDENCY_HASH_OR_READONLY_MISMATCH:'+name)
        paths[role]=export
        if role!='c3': robot_dashboard.__path__.append(str(export/'robot_dashboard'))
    for role,prefix in [('d2','robot_dashboard/relocalization'),('c1','robot_dashboard/pcd_editing')]:
        if subprocess.check_output(['git','diff','--name-only',PINS[role],'HEAD','--',prefix],cwd=REPO,text=True).strip():
            raise RuntimeError('COMMON_DEPENDENCY_DIFF:'+prefix)
    return paths


if __name__=='__main__':
    root=Path(os.environ['C4_ROS_DEP_ROOT']).resolve()
    if root==REPO or REPO in root.parents: raise ValueError('EXTERNAL_EXPORT_REQUIRED')
    root.mkdir(parents=True,exist_ok=True)
    for role,sha in PINS.items():
        dest=root/f'{role}-{sha}'
        if dest.exists(): continue
        raw=subprocess.check_output(['git','archive',sha],cwd=REPO)
        dest.mkdir()
        subprocess.run(['tar','-xf','-','-C',str(dest)],input=raw,check=True)
        subprocess.run(['chmod','-R','a-w',str(dest)],check=True)
    print(load())
