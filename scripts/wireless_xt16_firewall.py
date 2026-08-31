#!/usr/bin/env python3
"""Own the exact external-host firewall boundary for wireless XT16 mapping."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence


IPTABLES = "/usr/sbin/iptables"
IP = "/usr/sbin/ip"
CHAIN = "ROBOT_SCOPE_WIRELESS"
INTERFACE = "eno1"

_JUMP = ("INPUT", "-i", INTERFACE, "-j", CHAIN)
_RULES = (
    (
        CHAIN,
        "-p", "udp",
        "-s", "192.168.50.30/32",
        "-d", "192.168.50.10/32",
        "--sport", "46236",
        "--dport", "2368",
        "-j", "ACCEPT",
    ),
    (
        CHAIN,
        "-p", "udp",
        "-s", "192.168.50.30/32",
        "-d", "192.168.50.10/32",
        "--sport", "46020",
        "--dport", "46020",
        "-j", "ACCEPT",
    ),
    (CHAIN, "-p", "udp", "-d", "192.168.50.10/32", "--dport", "2368", "-j", "DROP"),
    (CHAIN, "-p", "udp", "-d", "192.168.50.10/32", "--dport", "46020", "-j", "DROP"),
    (CHAIN, "-j", "RETURN"),
)


class FirewallError(RuntimeError):
    pass


def _run(
    argv: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    command = tuple(argv)
    try:
        return runner(
            command,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8.0,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FirewallError("fixed firewall command failed") from exc


def _iptables(
    *arguments: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return _run((IPTABLES, "-w", "5", *arguments), runner=runner)


def _require_runtime(
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    if os.geteuid() != 0:
        raise FirewallError("root is required")
    version = _run((IPTABLES, "--version"), runner=runner)
    if version.returncode != 0 or "(legacy)" not in version.stdout:
        raise FirewallError("the reviewed iptables legacy backend is required")
    if _run((IP, "-o", "link", "show", "dev", INTERFACE), runner=runner).returncode != 0:
        raise FirewallError("the fixed external interface is unavailable")


def _chain_exists(
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> bool:
    inventory = _iptables("-S", runner=runner)
    if inventory.returncode != 0:
        raise FirewallError("firewall inventory is unavailable")
    return any(
        line.strip() == f"-N {CHAIN}" for line in inventory.stdout.splitlines()
    )


def status(
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> None:
    _require_runtime(runner)
    chain = _iptables("-S", CHAIN, runner=runner)
    if chain.returncode != 0:
        raise FirewallError("wireless firewall chain is absent")
    chain_lines = [line for line in chain.stdout.splitlines() if line.strip()]
    if len(chain_lines) != len(_RULES) + 1:
        raise FirewallError("wireless firewall chain has unexpected rules")
    for rule in _RULES:
        if _iptables("-C", *rule, runner=runner).returncode != 0:
            raise FirewallError("wireless firewall rule is missing")
    if _iptables("-C", *_JUMP, runner=runner).returncode != 0:
        raise FirewallError("wireless firewall INPUT jump is missing")
    all_rules = _iptables("-S", runner=runner)
    if all_rules.returncode != 0:
        raise FirewallError("firewall inventory is unavailable")
    references = sum(
        1 for line in all_rules.stdout.splitlines() if f"-j {CHAIN}" in line
    )
    if references != 1:
        raise FirewallError("wireless firewall chain ownership is ambiguous")


def install(
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> None:
    _require_runtime(runner)
    if _chain_exists(runner):
        status(runner=runner)
        return
    completed: list[tuple[str, ...]] = []
    try:
        if _iptables("-N", CHAIN, runner=runner).returncode != 0:
            raise FirewallError("wireless firewall chain creation failed")
        completed.append(("chain",))
        for rule in _RULES:
            if _iptables("-A", *rule, runner=runner).returncode != 0:
                raise FirewallError("wireless firewall rule installation failed")
            completed.append(rule)
        if _iptables("-I", *_JUMP, runner=runner).returncode != 0:
            raise FirewallError("wireless firewall INPUT jump installation failed")
        completed.append(_JUMP)
        status(runner=runner)
    except FirewallError:
        if completed and completed[-1] == _JUMP:
            _iptables("-D", *_JUMP, runner=runner)
        if completed:
            _iptables("-F", CHAIN, runner=runner)
            _iptables("-X", CHAIN, runner=runner)
        raise


def remove(
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> None:
    _require_runtime(runner)
    if not _chain_exists(runner):
        return
    status(runner=runner)
    for arguments in (("-D", *_JUMP), ("-F", CHAIN), ("-X", CHAIN)):
        if _iptables(*arguments, runner=runner).returncode != 0:
            raise FirewallError("wireless firewall removal failed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage one fixed wireless XT16 firewall boundary.")
    parser.add_argument("action", choices=("install", "status", "remove"))
    options = parser.parse_args(argv)
    try:
        {"install": install, "status": status, "remove": remove}[options.action]()
    except FirewallError as exc:
        print(f"[Robot Scope wireless firewall] {exc}", file=sys.stderr)
        return 1
    print(f"[Robot Scope wireless firewall] {options.action} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
