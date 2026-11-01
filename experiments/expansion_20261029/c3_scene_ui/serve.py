"""Static fixture server bound to loopback only; no application/ROS imports."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4183)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(SimpleHTTPRequestHandler, directory=str(root)))
    print(f"C3 fixture: http://127.0.0.1:{args.port}/experiments/expansion_20261029/c3_scene_ui/fixture.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
