"""Reproduce the previous C1 CI import failure without removing local packages.

Use the same interpreter, cwd and locale for before/after. Blocking optional
httpx packages is fault injection matching the remote installed package list.
The separate remote base/branch logs are the actual runner evidence.
"""

import builtins
import json
import locale
import subprocess
import sys

OLD = "54629c793ad4ae0ea88127f00ed1b7f8805fc4e2"
BASE = "f469155c2b0c505f3e472e878f75029d7b8d39df"
original_import = builtins.__import__


def no_optional_httpx(name, *args, **kwargs):
    if name.split(".")[0] in {"httpx", "httpx2"}:
        raise ModuleNotFoundError(name)
    return original_import(name, *args, **kwargs)


builtins.__import__ = no_optional_httpx
path = "tests/expansion_c1/test_services.py"
base = subprocess.run(["git", "cat-file", "-e", BASE + ":" + path], capture_output=True)
assert base.returncode != 0
old = subprocess.check_output(["git", "show", OLD + ":" + path], text=True)
try:
    exec(compile(old, path, "exec"), {"__name__": "c1_old_ci_reproducer"})
except RuntimeError as exc:
    assert "httpx2" in str(exc)
    old_error = str(exc).splitlines()[0]
else:
    raise AssertionError("old optional dependency failure did not reproduce")
# Same path/interpreter/locale, new import succeeds; no skip or assertion removed.
exec(
    compile(open(path, encoding="utf-8").read(), path, "exec"),
    {"__name__": "c1_fixed_ci_reproducer"},
)
print(
    json.dumps(
        {
            "python": sys.version.split()[0],
            "filesystem_encoding": sys.getfilesystemencoding(),
            "locale": locale.setlocale(locale.LC_ALL, None),
            "base_test": "ABSENT",
            "old": "FAIL: " + old_error,
            "current": "PASS",
        },
        ensure_ascii=True,
    )
)
