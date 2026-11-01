"""Real localhost HTTP smoke using temporary SYNTHETIC data only."""

from pathlib import Path
import socket
import tempfile
import threading
import time

import httpx
import uvicorn

from robot_dashboard.expansion_contracts import MapSourceDescriptor
from robot_dashboard.expansion_contracts.fixtures import request
from .host import create_test_host


def main():
    with tempfile.TemporaryDirectory(prefix="c1-smoke-") as root:
        app = create_test_host(Path(root), "public-c1-synthetic-smoke-bearer")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            address = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(
                uvicorn.Config(app, log_level="error", lifespan="on")
            )
            worker = threading.Thread(
                target=server.run, kwargs={"sockets": [listener]}, daemon=True
            )
            worker.start()
            try:
                deadline = time.monotonic() + 5
                while (
                    not server.started
                    and worker.is_alive()
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                assert server.started, "localhost fixture host failed to start"
                prefix = "/api/v1/extensions"
                with httpx.Client(
                    base_url=address, trust_env=False, timeout=5
                ) as client:
                    assert client.get(prefix + "/multimap/sources").status_code == 401
                    headers = {
                        "Authorization": "Bearer public-c1-synthetic-smoke-bearer",
                        "Origin": address,
                    }
                    descriptors = [
                        MapSourceDescriptor.from_dict(d)
                        for d in client.get(
                            prefix + "/multimap/sources", headers=headers
                        ).json()["sources"]
                    ]
                    job = client.post(
                        prefix + "/multimap/jobs",
                        headers=headers,
                        json=request(descriptors).to_dict(),
                    ).json()
                    for _ in range(200):
                        job = client.get(
                            prefix + "/multimap/jobs/" + job["job_id"], headers=headers
                        ).json()
                        if job["state"] not in {"QUEUED", "RUNNING"}:
                            break
                        time.sleep(0.01)
                    assert job["state"] == "SOLVED_CANDIDATE", job
                    base = prefix + "/multimap/jobs/" + job["job_id"]
                    review = client.post(
                        base + "/review",
                        headers=headers,
                        json={
                            "expected_proposal_revision": 1,
                            "accepted": True,
                            "manual_selection": None,
                        },
                    )
                    assert review.status_code == 200, review.text
                    export = client.post(
                        base + "/exports",
                        headers=headers,
                        json={"name": "smoke", "expected_proposal_revision": 2},
                    )
                    assert export.status_code == 201, export.text
                    saved = client.get(
                        prefix + "/multimap/exports/" + export.json()["id"],
                        headers=headers,
                    )
                    assert saved.status_code == 200 and saved.json()["point_count"] == 6
                    assert saved.json()["operational_installed"] is False
                    assert (
                        client.get(
                            prefix + "/scene/snapshot", headers=headers
                        ).status_code
                        == 200
                    )
                    print(
                        "PASS SYNTHETIC localhost auth/enqueue/status/review/export/reload/scene; DEVICE_NOT_RUN"
                    )
            finally:
                server.should_exit = True
                worker.join(5)
                app.state.c1[0].close()
                assert not worker.is_alive(), "fixture host did not stop"


if __name__ == "__main__":
    main()
