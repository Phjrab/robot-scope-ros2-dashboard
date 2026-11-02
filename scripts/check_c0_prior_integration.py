#!/usr/bin/env python3
"""Run the existing synthetic C0 probes on Linux; no installs or device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile


PORT = 4397
HARNESS = Path("tests/fixtures/planar_prior_integration")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_files(repo):
    names = subprocess.check_output([
        "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ], cwd=repo).split(b"\0")
    files = {}
    for raw in sorted(set(names) - {b""}):
        relative = raw.decode("utf-8")
        path = (repo / relative).resolve(strict=True)
        if not path.is_relative_to(repo) or not path.is_file():
            raise RuntimeError(f"Invalid source path: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def verify_source(repo, manifest):
    if source_files(repo) != manifest["files"]:
        raise RuntimeError("Complete source snapshot changed during validation")


def port_preflight():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", PORT))


def run_logged(command, directory, name, repo, env, timeout):
    with (directory / f"{name}.stdout").open("wb") as stdout, \
            (directory / f"{name}.stderr").open("wb") as stderr:
        result = subprocess.run(command, cwd=repo, env=env, stdout=stdout,
                                stderr=stderr, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}; see captured logs")


def wait_ready(server, snapshot_id):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"Owned fixture exited during startup: {server.returncode}")
        try:
            with opener.open(f"http://127.0.0.1:{PORT}/__fixture/source", timeout=1) as response:
                context = json.load(response)
            if context.get("snapshot_id") != snapshot_id or context.get("synthetic") is not True:
                raise RuntimeError("Unexpected listener identity; refusing to use it")
            if server.poll() is not None:
                raise RuntimeError("Owned fixture exited before readiness confirmation")
            return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError("Owned loopback fixture startup timed out")


def run_probe(repo, output, mode, probe, env, manifest):
    directory = output / mode
    directory.mkdir()
    env = {**env, "PRIOR_RUN_LABEL": mode, "PRIOR_OUTPUT_DIR": str(directory)}
    write_json(directory / "environment.json", {key: env[key] for key in env if key.startswith("PRIOR_")})
    with zipfile.ZipFile(directory / "harness.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in manifest["files"]:
            if name.startswith(str(HARNESS) + "/") or name in {
                "tests/e2e/dashboard_backend.mjs", "tests/e2e/fixture_socket_lifecycle.mjs"
            }:
                archive.write(repo / name, name)
    verify_source(repo, manifest)
    port_preflight()  # Never reuse or terminate a listener belonging to another run.
    errors, server = [], None
    receipt = {"mode": mode, "state": "FAIL", "snapshot_id": manifest["snapshot_id"]}
    with (directory / "server.stdout").open("wb") as stdout, \
            (directory / "server.stderr").open("wb") as stderr:
        try:
            server = subprocess.Popen([sys.executable, str(HARNESS / "fixture_server.py")],
                                      cwd=repo, env=env, stdout=stdout, stderr=stderr)
            receipt["owned_server_pid"] = server.pid
            wait_ready(server, manifest["snapshot_id"])
            run_logged(["node", str(HARNESS / probe)], directory, "probe", repo, env, 600)
            if server.poll() is not None:
                raise RuntimeError("Owned fixture exited during the probe")
        except Exception as error:
            errors.append(f"{type(error).__name__}: {error}")
        finally:
            if server is not None:
                try:
                    receipt["sent_sigterm"] = server.poll() is None
                    if receipt["sent_sigterm"]:
                        server.terminate()
                    try:
                        receipt["server_exit_code"] = server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        errors.append("Owned fixture did not stop after SIGTERM")
                        server.kill()
                        receipt["server_exit_code"] = server.wait(timeout=5)
                    accepted = {0, -signal.SIGTERM} if receipt["sent_sigterm"] else {0}
                    if receipt.get("server_exit_code") not in accepted:
                        errors.append(f"Owned fixture cleanup exit: {receipt.get('server_exit_code')}")
                except Exception as error:
                    errors.append(f"Owned fixture cleanup failed: {error}")
            try:
                verify_source(repo, manifest)
                receipt["source_unchanged"] = True
            except Exception as error:
                errors.append(str(error))
            receipt.update(state="FAIL" if errors else "PASS", errors=errors)
            write_json(directory / "receipt.json", receipt)
    if errors:
        raise RuntimeError(f"{mode}: " + "; ".join(errors))
    print(f"PASS: {mode}; source unchanged; owned server stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory outside the Git checkout")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Linux is required by the existing /proc process-identity contracts")
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
    output = args.output.resolve()
    if output == repo or output.is_relative_to(repo):
        parser.error("--output must be outside the Git checkout")
    output.mkdir(parents=True, exist_ok=False)  # Preserve all previous outcomes.
    summary = {"state": "FAIL", "device": "NOT_RUN", "python": sys.version}
    try:
        if shutil.which("node") is None:
            raise RuntimeError("Existing Node installation is required")
        browser = json.loads(subprocess.check_output([
            "node", "-e", "console.log(JSON.stringify({node:process.version,"
            "playwright:require('playwright/package.json').version,"
            "chromium:require('playwright').chromium.executablePath()}))"
        ], cwd=repo, text=True))
        summary.update(browser)
        chromium = browser["chromium"]
        if not Path(chromium).is_file():
            raise RuntimeError("Existing Playwright Chromium installation is required")
        manifest = {"snapshot_id": "c0-main-" + uuid.uuid4().hex,
                    "complete_source_snapshot": True, "files": source_files(repo)}
        manifest_path = output / "source-manifest.json"
        write_json(manifest_path, manifest)
        summary.update(snapshot_id=manifest["snapshot_id"], source_files=len(manifest["files"]),
                       manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("PRIOR_") and key not in {"PYTHONPATH", "PYTHONPYCACHEPREFIX"}}
        adapter = repo / HARNESS / "retention_adapter.py"
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PRIOR_SOURCE_ROOT=str(repo),
                   PRIOR_HASH_MANIFEST=str(manifest_path), PRIOR_RETENTION_ADAPTER=str(adapter),
                   PRIOR_RETENTION_ADAPTER_SHA256=hashlib.sha256(adapter.read_bytes()).hexdigest(),
                   PRIOR_NODE_ROOT=str(repo), PRIOR_CHROMIUM=chromium, PRIOR_REQUIRE_GROUPING="1")
        verify_source(repo, manifest)
        try:
            run_logged(["node", "--test", str(HARNESS / "test_contract_assertions.mjs")],
                       output, "helper", repo, env, 120)
        finally:
            verify_source(repo, manifest)
        for mode, probe in [("component", "browser_probe.mjs"), ("full-app", "full_app_probe.mjs")]:
            run_probe(repo, output, mode, probe, env, manifest)
        summary["state"] = "PASS"
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_json(output / "summary.json", summary)


if __name__ == "__main__":
    main()
