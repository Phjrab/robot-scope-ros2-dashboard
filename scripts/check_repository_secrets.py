#!/usr/bin/env python3
"""Fail CI when a tracked source file contains a likely credential.

This is deliberately a narrow, dependency-free safety net.  It scans only
tracked, text-like files and reports a rule name plus file/line, never the
matched value itself.  It complements—not replaces—review and secret storage
outside the repository.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".env",
        ".example",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".service",
        ".sh",
        ".sudoers",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
SECRET_RULES = {
    "private-key": re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    "gitlab-token": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,255}\b"),
    "robot-scope-control-key": re.compile(
        r"\bROBOT_SCOPE_CONTROL_BRIDGE_KEY\s*=\s*['\"]?[0-9a-fA-F]{64,}"
    ),
}


def _tracked_paths() -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        ROOT / value.decode("utf-8", "surrogateescape")
        for value in completed.stdout.split(b"\0")
        if value
    ]


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        "AGENTS.md",
        "LICENSE",
        "README.md",
    }


def find_secret_like_values() -> list[tuple[str, str, int]]:
    findings: list[tuple[str, str, int]] = []
    for path in _tracked_paths():
        if not _is_text_candidate(path) or not path.is_file():
            continue
        if path.stat().st_size > MAX_TEXT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in SECRET_RULES.items():
                if pattern.search(line):
                    findings.append((rule, relative, line_number))
    return findings


def main() -> int:
    findings = find_secret_like_values()
    if not findings:
        print("tracked-source secret scan passed")
        return 0
    for rule, path, line in findings:
        print(f"secret-scan:{rule}:{path}:{line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
