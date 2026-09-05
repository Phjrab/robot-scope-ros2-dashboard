from __future__ import annotations

import io
import json
import stat
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from robot_dashboard.diagnostics import (
    DIAGNOSTICS_MAX_ZIP_BYTES,
    DiagnosticsBundleService,
    DiagnosticsUnavailable,
)
from robot_dashboard.operator_events import (
    EVENT_EXPORT_MAX_ENTRIES,
    OperatorEventTimeline,
    classify_http_event,
    record_http_event,
)


FIXED_NOW = datetime(2026, 8, 23, 5, 45, 0, tzinfo=timezone.utc)


class OperatorEventTimelineTests(unittest.TestCase):
    def test_operator_catalog_is_fixed_and_covers_phase13_mutations(self) -> None:
        expected = {
            ("POST", "/api/v1/control/arm"): "control_arm",
            ("POST", "/api/v1/control/disarm"): "control_disarm",
            ("POST", "/api/v1/control/stop"): "estop_latch",
            ("POST", "/api/v1/control/estop/clear"): "estop_clear",
            ("POST", "/api/v1/mapping/start"): "mapping_start",
            ("POST", "/api/v1/mapping/stop"): "mapping_stop",
            ("POST", "/api/v1/mapping/save"): "mapping_save",
            ("POST", "/api/v1/navigation/start"): "navigation_start",
            ("POST", "/api/v1/navigation/stop"): "navigation_stop",
            ("POST", "/api/v1/navigation/initial-pose"): "initial_pose",
            ("POST", "/api/v1/navigation/goal"): "goal_send",
            ("POST", "/api/v1/navigation/goal/annotation"): "annotation_goal_send",
            ("POST", "/api/v1/navigation/cancel"): "goal_cancel",
            ("POST", "/api/v1/navigation/clear-costmaps"): "costmap_clear",
            ("POST", "/api/v1/missions"): "mission_create",
            ("POST", "/api/v1/datasets/capture/start"): "dataset_start",
            ("POST", "/api/v1/datasets/capture/stop"): "dataset_stop",
            ("POST", "/api/v1/system/service/restart"): "service_restart",
            ("POST", "/api/v1/system/service/stop"): "service_stop",
            ("POST", "/api/v1/control/bridge-service/start"): "bridge_service_start",
            ("POST", "/api/v1/control/bridge-service/stop"): "bridge_service_stop",
            ("POST", "/api/v1/system/diagnostics/export"): "diagnostics_export",
            ("POST", "/api/v1/route-planner/guidance/start"): "route_guidance_start",
            ("POST", "/api/v1/route-planner/guidance/stop"): "route_guidance_stop",
            ("POST", "/api/v1/route-planner/guidance/pickup"): "route_pickup_confirm",
            ("POST", "/api/v1/route-planner/guidance/dropoff"): "route_dropoff_confirm",
        }
        for (method, path), event_type in expected.items():
            with self.subTest(method=method, path=path):
                classified = classify_http_event(method, path)
                self.assertIsNotNone(classified)
                self.assertEqual(classified[0], event_type)
                self.assertEqual(classified[1], {})
        self.assertIsNone(classify_http_event("POST", "/api/v1/mission/start"))
        self.assertIsNone(classify_http_event("GET", "/api/v1/navigation"))
        mission_id = "1" * 32
        for action in ("start", "pause", "resume", "skip", "retry", "abort"):
            classified = classify_http_event("POST", f"/api/v1/missions/{mission_id}/{action}")
            self.assertEqual(classified, (f"mission_{action}", {"mission_id": mission_id}))
        classified = classify_http_event(
            "PATCH", "/api/v1/saved-maps/0123456789abcdef01234567/annotations"
        )
        self.assertEqual(
            classified,
            (
                "map_annotations_update",
                {"map_id": "0123456789abcdef01234567"},
            ),
        )

    def test_fixed_http_catalog_records_only_bounded_identity_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            timeline = OperatorEventTimeline(Path(temporary).resolve())
            recorded = record_http_event(
                timeline,
                method="PATCH",
                path="/api/v1/saved-maps/0123456789abcdef01234567",
                headers={
                    "x-robot-scope-browser-session": "browser_session_1234",
                    "x-robot-scope-request-sequence": "17",
                    "authorization": "Bearer do-not-store",
                },
                status_code=200,
            )
            self.assertEqual(recorded["event_type"], "map_rename")
            self.assertEqual(recorded["browser_session_id"], "browser_session_1234")
            self.assertEqual(recorded["request_sequence"], 17)
            self.assertEqual(
                recorded["targets"], {"map_id": "0123456789abcdef01234567"}
            )
            serialized = json.dumps(recorded)
            self.assertNotIn("Authorization", serialized)
            self.assertNotIn("do-not-store", serialized)
            failed = record_http_event(
                timeline,
                method="POST",
                path="/api/v1/navigation/start",
                headers={},
                status_code=503,
            )
            self.assertEqual(failed["result"], "error")
            self.assertEqual(failed["reason_code"], "http_503")
            self.assertIsNone(
                classify_http_event("POST", "/api/v1/robots/discover")
            )

    def test_invalid_browser_identity_fails_closed_without_storing_reason_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            timeline = OperatorEventTimeline(Path(temporary).resolve())
            event = timeline.append(
                "control_arm",
                browser_session_id="../../private/key",
                request_sequence=-1,
                targets={"bad": "/private/key", "map_id": "a" * 24},
                result="accepted",
                reason_code="http_200",
                now=FIXED_NOW,
            )
            self.assertEqual(event["browser_session_id"], "unknown")
            self.assertIsNone(event["request_sequence"])
            self.assertEqual(event["targets"], {"map_id": "a" * 24})
            self.assertEqual(event["timestamp"], "2026-08-23T05:45:00.000Z")

    def test_rotation_retention_permissions_and_recent_bound_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            timeline = OperatorEventTimeline(
                root,
                max_file_bytes=4_096,
                retention_files=2,
            )
            for index in range(200):
                timeline.append(
                    "mapping_start",
                    browser_session_id="browser_session_1234",
                    request_sequence=index + 1,
                    result="accepted",
                    reason_code="http_200",
                    now=FIXED_NOW,
                )
            self.assertTrue((root / "operator-events.jsonl").is_file())
            self.assertTrue((root / "operator-events.jsonl.1").is_file())
            self.assertFalse((root / "operator-events.jsonl.2").exists())
            self.assertEqual(
                stat.S_IMODE((root / "operator-events.jsonl").stat().st_mode),
                0o600,
            )
            recent = timeline.recent(EVENT_EXPORT_MAX_ENTRIES)
            self.assertLessEqual(len(recent), EVENT_EXPORT_MAX_ENTRIES)
            self.assertEqual(recent[-1]["request_sequence"], 200)

    def test_relative_root_filesystem_root_and_symlink_parent_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OperatorEventTimeline(Path("relative/events"))
        with self.assertRaises(ValueError):
            OperatorEventTimeline(Path("/"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            broad = root / "broad"
            broad.mkdir(mode=0o755)
            broad.chmod(0o755)
            with self.assertRaises(ValueError):
                OperatorEventTimeline(broad)
            self.assertEqual(stat.S_IMODE(broad.stat().st_mode), 0o755)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                OperatorEventTimeline(link / "events")

    def test_persisted_lines_are_reprojected_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            timeline = OperatorEventTimeline(Path(temporary).resolve())
            persisted = {
                "schema": "robot-scope.operator-event.v1",
                "event_id": 7,
                "timestamp": "2026-08-23T05:45:00.000Z",
                "browser_session_id": "../../private/key",
                "request_sequence": True,
                "event_type": "mapping_start",
                "targets": {"map_id": "a" * 24, "path": "/private/map"},
                "result": "accepted",
                "reason_code": "http_200",
                "secret": "password=hunter2",
            }
            timeline.path.write_text(json.dumps(persisted) + "\n", encoding="utf-8")
            entries = timeline.recent()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["browser_session_id"], "unknown")
            self.assertIsNone(entries[0]["request_sequence"])
            self.assertEqual(entries[0]["targets"], {"map_id": "a" * 24})
            self.assertNotIn("secret", entries[0])
            self.assertNotIn("hunter2", json.dumps(entries[0]))


class DiagnosticsBundleTests(unittest.TestCase):
    def build_service(
        self,
        project: Path,
        timeline: OperatorEventTimeline,
        *,
        ros_distro: str = "humble",
    ) -> DiagnosticsBundleService:
        return DiagnosticsBundleService(
            project_dir=project,
            profile_provider=lambda: {
                "name": "go2-nav",
                "robot_type": "go2",
                "bridge_key": "must-only-affect-the-hash",
            },
            health_provider=lambda: {
                "agent_ready": True,
                "robot_target_connected": True,
                "robot_online": True,
                "ros_interface_ready": True,
                "ros_offline_viewer": False,
                "robot_type": "go2",
                "robot_ip": "192.168.123.161",
                "hostname": "private-host",
                "ros_distro": ros_distro,
                "rmw": "rmw_cyclonedds_cpp",
                "topic_count": 2,
                "last_error": "password=hunter2 at /private/runtime/error.log",
                "ros_transport": {
                    "mode": "go2_interface",
                    "interface": "eno1",
                    "uri": "file:///private/cyclone.xml",
                },
            },
            topics_provider=lambda: [
                {
                    "name": "/velodyne_points",
                    "type": "sensor_msgs/msg/PointCloud2",
                    "category": "pointcloud",
                    "publishers": 1,
                    "subscribers": 2,
                    "selected": True,
                    "state": "ok",
                    "hz": 8.2,
                    "age_s": 0.1,
                }
            ],
            sources_provider=lambda: {
                "selected": {"pointcloud": "/velodyne_points"},
                "selected_descriptors": {
                    "pointcloud": {
                        "sensor_id": "xt16",
                        "pipeline_stage": "converted",
                        "state": "ok",
                        "hz": 8.2,
                        "age_s": 0.1,
                    }
                },
            },
            control_provider=lambda: {
                "bridge": {
                    "authenticated": True,
                    "ready": True,
                    "status_age_s": 0.1,
                    "bridge_key": "never-export",
                    "bridge_epoch": "never-export",
                }
            },
            mapping_provider=lambda: {
                "pipeline": {"state": "running", "pid": 999},
                "logs": [
                    {
                        "seq": 1,
                        "time": "2026-08-23T05:44:00Z",
                        "source": "pipeline",
                        "message": "password=hunter2 /private/runtime/map.log",
                    }
                ],
            },
            navigation_provider=lambda: {
                "pipeline": {"state": "idle", "pid": 888},
                "map": {"id": "a" * 24, "revision": "b" * 64},
            },
            navigation_events_provider=lambda: {
                "entries": [
                    {
                        "seq": 2,
                        "timestamp": "2026-08-23T05:44:30Z",
                        "phase": "runtime",
                        "message": "Authorization: Bearer secret /private/nav.log",
                    }
                ]
            },
            dataset_provider=lambda: {
                "state": "idle",
                "saved": 3,
                "dropped": 1,
                "free_bytes": 5_000,
                "minimum_free_bytes": 2_000,
                "output_path": "/private/datasets",
                "queue": {"depth": 0},
            },
            operator_events=timeline,
            disk_roots={"project_storage": project},
            clock=lambda: FIXED_NOW,
            identity_provider=lambda: {"commit": "1" * 40, "tag": "v0.4.0"},
            disk_usage_provider=lambda _path: SimpleNamespace(
                total=10_000,
                used=4_000,
                free=6_000,
            ),
        )

    def test_bundle_is_deterministic_fixed_order_and_size_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            timeline = OperatorEventTimeline(project / "events")
            timeline.append(
                "mapping_start",
                browser_session_id="browser_session_1234",
                request_sequence=1,
                result="accepted",
                reason_code="http_200",
                now=FIXED_NOW,
            )
            service = self.build_service(project, timeline)
            first = service.build()
            second = service.build()
            self.assertEqual(first.payload, second.payload)
            self.assertEqual(
                first.filename,
                "robot-scope-diagnostics-20260823T054500Z.zip",
            )
            self.assertLess(len(first.payload), DIAGNOSTICS_MAX_ZIP_BYTES)
            with zipfile.ZipFile(io.BytesIO(first.payload)) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "summary.json",
                        "versions.json",
                        "health.json",
                        "ros-graph-summary.json",
                        "network-summary.json",
                        "mapping-events.jsonl",
                        "navigation-events.jsonl",
                        "operator-events.jsonl",
                        "redaction-report.json",
                    ],
                )
                self.assertTrue(all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist()))
                summary = json.loads(archive.read("summary.json"))
                network = json.loads(archive.read("network-summary.json"))
                self.assertEqual(summary["active_map"], {"id": "a" * 24, "revision": "b" * 64})
                self.assertEqual(len(summary["profile"]["sha256"]), 64)
                self.assertEqual(
                    network["route"],
                    {"address": "withheld", "state": "reachable"},
                )
                self.assertEqual(network["transport_mode"], "go2_interface")

    def test_secret_paths_ips_raw_topics_and_private_process_fields_never_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            timeline = OperatorEventTimeline(project / "events")
            payload = self.build_service(project, timeline).build().payload
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                unpacked = b"\n".join(archive.read(name) for name in archive.namelist())
            for forbidden in (
                b"hunter2",
                b"never-export",
                b"192.168.123.161",
                b"private-host",
                b"/private/",
                b"velodyne_points",
                b"bridge_epoch",
                b'"pid"',
                b"file://",
            ):
                self.assertNotIn(forbidden, unpacked)
            self.assertIn(b"[redacted]", unpacked)
            self.assertIn(b"[path-or-topic]", unpacked)

    def test_profile_and_dependency_values_are_hash_or_fixed_revision_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            config = project / "config"
            config.mkdir()
            (config / "ros_dependencies_humble.json").write_text(
                json.dumps(
                    {
                        "repositories": {
                            "safe_repo": {
                                "commit": "2" * 40,
                                "license": "BSD-3-Clause",
                                "url": "https://user:password@example.invalid/private.git",
                                "target": "/private/workspace",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            timeline = OperatorEventTimeline(project / "events")
            payload = self.build_service(project, timeline).build().payload
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                versions = json.loads(archive.read("versions.json"))
                summary = json.loads(archive.read("summary.json"))
            self.assertEqual(
                versions["external_dependencies"],
                {"safe_repo": {"commit": "2" * 40, "license": "BSD-3-Clause"}},
            )
            self.assertNotIn("bridge_key", json.dumps(summary))
            self.assertEqual(len(summary["profile"]["sha256"]), 64)

            changed_secret_service = self.build_service(project, timeline)
            changed_secret_service._profile_provider = lambda: {
                "name": "go2-nav",
                "robot_type": "go2",
                "bridge_key": "a-different-secret-must-not-affect-the-hash",
            }
            changed_payload = changed_secret_service.build().payload
            with zipfile.ZipFile(io.BytesIO(changed_payload)) as archive:
                changed_summary = json.loads(archive.read("summary.json"))
            self.assertEqual(
                changed_summary["profile"]["sha256"],
                summary["profile"]["sha256"],
            )

    def test_dependency_manifest_follows_reported_ros_distro(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            config = project / "config"
            config.mkdir()
            (config / "ros_dependencies_jazzy.json").write_text(
                json.dumps(
                    {
                        "repositories": {
                            "jazzy_dependency": {
                                "commit": "3" * 40,
                                "license": "MIT",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            timeline = OperatorEventTimeline(project / "events")
            payload = self.build_service(
                project, timeline, ros_distro="jazzy"
            ).build().payload
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                versions = json.loads(archive.read("versions.json"))
            self.assertEqual(versions["ros_distro"], "jazzy")
            self.assertEqual(
                versions["external_dependencies"],
                {"jazzy_dependency": {"commit": "3" * 40, "license": "MIT"}},
            )

    def test_provider_failures_are_reported_with_one_fixed_public_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            timeline = OperatorEventTimeline(project / "events")
            service = self.build_service(project, timeline)

            def fail_with_private_detail():
                raise RuntimeError("password=hunter2 at /private/provider.log")

            service._health_provider = fail_with_private_detail
            with self.assertRaisesRegex(
                DiagnosticsUnavailable,
                r"^diagnostics snapshot unavailable$",
            ) as raised:
                service.build()
            self.assertNotIn("hunter2", str(raised.exception))
            self.assertNotIn("/private", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
