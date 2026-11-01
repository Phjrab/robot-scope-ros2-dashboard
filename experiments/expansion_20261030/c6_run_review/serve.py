"""Standalone GET-only loopback host. Does not mount application API or expose input files."""

import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from robot_dashboard.run_review.dependencies import verify  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, deps, **kwargs):
        self.deps = deps
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            self.send_error(403)
            return
        path = unquote(urlsplit(self.path).path)
        if "\\" in path or ".." in path.split("/") or "\x00" in path:
            self.send_error(400)
            return
        roots = {
            "/c6/": REPO / "experiments/expansion_20261030/c6_run_review",
            "/robot_dashboard/static/features/run_review/": REPO
            / "robot_dashboard/static/features/run_review",
            "/c6-deps/obstacle_scene/": self.deps
            / "robot_dashboard/static/features/obstacle_scene",
        }
        target = None
        if path == "/":
            target = REPO / "experiments/expansion_20261030/c6_run_review/review.html"
        elif path == "/c6-deps/route_planner/spatial_editor.js":
            target = (
                REPO / "robot_dashboard/static/features/route_planner/spatial_editor.js"
            )
        elif path == "/robot_dashboard/static/scene3d.js":
            target = REPO / path.lstrip("/")
        else:
            for prefix, root in roots.items():
                if path.startswith(prefix):
                    candidate = root / path[len(prefix) :]
                    if candidate.resolve().is_relative_to(root.resolve()):
                        target = candidate
                    break
        if (
            target is None
            or target.is_symlink()
            or not target.is_file()
            or target.suffix not in (".html", ".js", ".css")
        ):
            self.send_error(404)
            return
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type", mimetypes.guess_type(str(target))[0] or "text/plain"
        )
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--deps", type=Path, required=True)
    p.add_argument("--port", type=int, default=8766)
    args = p.parse_args()
    deps = verify(args.deps, "C3")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, deps=deps))
    print(f"REPLAY loopback http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
