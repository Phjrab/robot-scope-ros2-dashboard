"""Explicit offline cross-check against an exported current main source tree.

Use main's unchanged worker/ingress/D0 and this branch's C4 package. Neither
checkout is modified. No robot, camera, network client or command port is used.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import threading
import time
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("main-source", "model", "config", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--image")
    parser.add_argument("--image-kind", choices=("stored-rgb", "training-visualization"), default="stored-rgb")
    parser.add_argument("--require-signal-detection", action="store_true")
    parser.add_argument("--acknowledge-trusted-pickle", action="store_true")
    args = parser.parse_args()
    root = Path(args.main_source).resolve(strict=True)
    c4_root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root), str(root / "tests")]
    import robot_dashboard.competition_traffic as traffic
    traffic.__path__.insert(0, str(c4_root / "robot_dashboard/competition_traffic"))
    import cv2
    import numpy as np
    from robot_dashboard.competition_traffic.config import TrafficConfig, sha256_file
    from robot_dashboard.competition_traffic.frames import Frame
    from robot_dashboard.competition_traffic.model import OwnerModel
    from robot_dashboard.competition_traffic.pipeline import TrafficPipeline
    from robot_dashboard.competition_traffic.worker import TrafficWorker
    from robot_dashboard.mission_routes.competition_native.ingress import CompetitionIngress

    cfg = TrafficConfig.read(args.config)
    model = OwnerModel(args.model, cfg, acknowledge_trusted_pickle=args.acknowledge_trusted_pickle)
    image = cv2.imread(args.image) if args.image else np.zeros((720, 1280, 3), np.uint8)
    if image is None:
        raise ValueError("INPUT_IMAGE_DECODE_FAILED")
    caller_thread = threading.get_ident()
    executing_threads = []
    infer = model.infer
    def tracked_infer(bgr):
        executing_threads.append(threading.get_ident())
        return infer(bgr)
    model.infer = tracked_infer

    async def smoke():
        worker = TrafficWorker(TrafficPipeline(cfg, model, observation_mode="detection-only", measure_wall_latency=True))
        worker.start()
        received = time.monotonic()
        frame = Frame(image, "offline-static", "c1-model-check", 0, "0", "fixture", None,
                      received, False, "STATIC_DIAGNOSTIC_NO_SENSOR_CLOCK", "static-image",
                      cfg.document["association"]["binding_id"])
        try:
            assert worker.offer(frame)
            await asyncio.wait_for(worker.queue.join(), 30)
            assert worker.error is None, worker.error
            sample = worker.latest
            assert sample.frame is frame
            context = sample.observation.context
            if args.require_signal_detection:
                assert context["free_observations"], "EXPECTED_SMOKE_DETECTION_MISSING"
            for record in context["free_observations"]:
                assert record["class_id"] in (0, 1)
                assert record["class_name"] == model.names[str(record["class_id"])]
                assert record["color_consensus"]["model_state"] == record["model_state"]
            assert context["first_received_s"] == received
            assert context["processed_s"] >= sample.processing_started_s
            assert context["receiver_age_s"] == context["processed_s"] - received
            assert context["sequence"] == 0 and context["source_stamp_ns"] == "0"
            assert executing_threads and all(t != caller_thread for t in executing_threads)
            review = CompetitionIngress.review(sample, now=time.monotonic(),
                                               inference_settings_sha256=model.inference_settings_sha256)
            assert review["inference_binding_matches"]
            assert not review["departure_authorized"]
            assert review["projection_reasons"]  # offline detection-only cannot project live evidence
            wrong = CompetitionIngress.review(sample, now=time.monotonic(), inference_settings_sha256="0"*64)
            assert "C4_INFERENCE_SETTINGS_MISMATCH" in wrong["projection_reasons"]
            return {"status": "C1_ADAPTER_TESTED", "input_kind": args.image_kind if args.image else "synthetic_black",
                    "model_sha256": model.sha256, "config_hash": cfg.sha256,
                    "inference_settings_sha256": model.inference_settings_sha256,
                    "worker_sha256": sha256_file(root / "robot_dashboard/competition_traffic/worker.py"),
                    "ingress_sha256": sha256_file(root / "robot_dashboard/mission_routes/competition_native/ingress.py"),
                    "inference_off_owner_loop": True, "first_receipt_preserved": True,
                    "review": review, "observation": sample.observation.json_record()}
        finally:
            await worker.close()

    result = asyncio.run(smoke())
    # The main export has no .git directory. Read its pinned historical test
    # dependencies from the existing C4 checkout's objects, without fetching.
    from competition_native import dependency_overlay
    dependency_overlay.ROOT = c4_root
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for name in ("competition_integration", "competition_native"):
        suite.addTests(loader.discover(str(root / "tests" / name), top_level_dir=str(root / "tests")))
    run = unittest.TextTestRunner(verbosity=1).run(suite)
    result["main_regression"] = {"tests": run.testsRun, "failures": len(run.failures),
                                 "errors": len(run.errors), "skipped": len(run.skipped),
                                 "skip_reasons": [reason for _, reason in run.skipped]}
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    return 0 if run.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
