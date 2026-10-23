"""Synthetic temporary-directory fixtures only; no ROS, HTTP, robot or map dataset."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from robot_dashboard.pcd_editing.geometry import PcdEditError
from robot_dashboard.pcd_editing.pcd import filter_pcd
from robot_dashboard.pcd_editing import store as store_module
from robot_dashboard.pcd_editing.store import (
    MANIFEST_SCHEMA, PcdEditConflict, PcdEditStore, REQUEST_SCHEMA,
    SourceAsset, read_manifest, validate_request,
)


def cloud_bytes():
    """Eight full records, unlike the one-point preview used in the browser."""
    coordinates = [(0, 0, 0), (.5, .5, .5), (1, 1, 0), (2, 2, 0),
                   (4, 4, 0), (10, 10, 0), (float("nan"), 0, 0), (0, 0, 5)]
    header = ("# Synthetic fixture\nVERSION .7\nFIELDS x y z intensity ring\n"
              "SIZE 4 4 4 2 1\nTYPE F F F U U\nCOUNT 1 1 1 1 1\n"
              "WIDTH 8\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS 8\nDATA binary\n")
    return header.encode("ascii") + b"".join(
        struct.pack("<fffHB", x, y, z, 100 + index, index)
        for index, (x, y, z) in enumerate(coordinates)
    )


def records(data):
    return list(struct.iter_unpack("<fffHB", data.split(b"DATA binary\n", 1)[1]))


def region(kind="visibility", lower=-.1, upper=1.1):
    return {"kind": kind, "selection": "inside", "polygon": [
        [lower, lower], [upper, lower], [upper, upper], [lower, upper]], "z_min": -1, "z_max": 1}


class PcdEditingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-pcd-edit-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source_path = self.directory / "synthetic-original.pcd"
        self.original = cloud_bytes()
        self.source_path.write_bytes(self.original)
        self.original_id = "a" * 24
        self.asset = SourceAsset(self.original_id, hashlib.sha256(b"synthetic revision").hexdigest(),
                                 self.source_path, "camera_init")
        self.assets = {self.original_id: self.asset}

        def resolve(map_id):
            if map_id in self.assets:
                return self.assets[map_id]
            metadata = self.store.get(map_id)
            return SourceAsset(map_id, metadata["revision"], self.store.root / map_id / "map.pcd",
                               metadata["frame_id"], origin=metadata["origin"],
                               edit_history=tuple(metadata["edit_history"]))

        self.resolve = resolve
        self.store = PcdEditStore(self.directory / "derived", resolve, chunk_points=2)

    def request(self, map_id=None, purpose="visibility"):
        source = self.store.descriptor(map_id or self.original_id)
        return {"schema": REQUEST_SCHEMA, "name": "synthetic_copy", "purpose": purpose,
                "source": source, "annotation": {
                    "schema": "robot-dashboard.map-editor3d", "schema_version": 1,
                    "version_id": "edit-synthetic-test", "runtime_installed": False,
                    "source": {key: source[key] for key in ("map_id", "revision", "frame_id")},
                    "regions": [region(), region("localization", 3.9, 4.1), region("keepout", 9.9, 10.1)],
                }}

    def assert_unregistered(self):
        self.assertEqual(self.store.list(), [])
        self.assertEqual(list(self.store.root.glob(".stage-*")), [])
        if self.store.root.exists():
            self.assertEqual([path for path in self.store.root.iterdir() if not path.name.startswith(".")], [])

    def test_descriptor_explicitly_identifies_complete_source_without_preview_count_or_path(self):
        descriptor = self.store.descriptor(self.original_id)
        self.assertEqual(set(descriptor), {"map_id", "revision", "sha256", "frame_id", "units", "asset_role"})
        self.assertEqual(descriptor["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(descriptor["revision"], self.asset.revision)
        self.assertNotEqual(descriptor["revision"], descriptor["sha256"])
        self.assertEqual(descriptor["frame_id"], "camera_init")
        self.assertEqual(descriptor["units"], "m")
        self.assertEqual(descriptor["asset_role"], "full_source")
        self.assertNotIn(str(self.directory), json.dumps(descriptor))
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assertFalse(self.store.root.exists(), "GET descriptor must not create the registry")
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(FileNotFoundError):
            self.store.get("b" * 24)
        self.assertFalse(self.store.root.exists())

    def test_invalid_save_on_absent_registry_does_not_create_files(self):
        request = self.request()
        request["source"]["sha256"] = "b" * 64
        with self.assertRaises(PcdEditConflict):
            self.store.save(request)
        self.assertFalse(self.store.root.exists())
        self.assertEqual(self.source_path.read_bytes(), self.original)
        request = self.request()
        request["annotation"]["regions"][0]["polygon"] = [[0, 0]]
        with self.assertRaises(PcdEditError):
            self.store.save(request)
        self.assertFalse(self.store.root.exists())

    def test_save_processes_all_original_records_and_records_manifest_and_provenance(self):
        request = self.request()
        request_before = deepcopy(request)
        metadata = self.store.save(request)
        output = self.store.root / metadata["id"]
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assertEqual(request, request_before)
        self.assertRegex(metadata["id"], r"^[0-9a-f]{24}$")
        self.assertNotEqual(metadata["id"], self.original_id)
        self.assertRegex(metadata["revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(metadata["schema"], MANIFEST_SCHEMA)
        self.assertEqual(metadata["sha256"], hashlib.sha256((output / "map.pcd").read_bytes()).hexdigest())
        self.assertNotEqual(metadata["sha256"], request["source"]["sha256"])
        self.assertEqual(metadata["source"], request["source"])
        self.assertEqual(metadata["origin"], request["source"])
        self.assertEqual(metadata["frame_id"], "camera_init")
        self.assertEqual(metadata["units"], "m")
        self.assertEqual(metadata["point_count"], 5)
        self.assertIs(metadata["runtime_installed"], False)
        self.assertIs(metadata["manageable"], False)
        self.assertEqual(metadata["asset_role"], "full_source")
        history = metadata["edit_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["annotation"], request["annotation"])
        self.assertEqual(history[0]["purpose"], "visibility")
        self.assertEqual(history[0]["source_sha256"], request["source"]["sha256"])
        self.assertEqual(history[0]["input_points"], 8)
        self.assertEqual(history[0]["output_points"], 5)
        self.assertEqual(history[0]["removed_points"], 3)
        self.assertEqual(history[0]["nonfinite_points_preserved"], 1)
        self.assertEqual(history[0]["applied_at"], metadata["created_at"])
        # First three records are removed, including two absent from a one-point preview.
        self.assertEqual([record[3] for record in records((output / "map.pcd").read_bytes())], [103, 104, 105, 106, 107])
        self.assertEqual(set(path.name for path in output.iterdir()), {"map.pcd", "manifest.json"})
        self.assertEqual(self.store.get(metadata["id"]), metadata)
        self.assertEqual(self.store.list(), [metadata])
        self.assertNotIn(str(self.directory), json.dumps(metadata))
        metadata["edit_history"][0]["annotation"]["regions"].clear()
        self.assertEqual(len(self.store.get(metadata["id"])["edit_history"][0]["annotation"]["regions"]), 3)

    def test_localization_copy_filters_only_localization_and_does_not_install_runtime(self):
        metadata = self.store.save(self.request(purpose="localization"))
        self.assertEqual(metadata["point_count"], 7)
        self.assertEqual(metadata["edit_history"][0]["removed_points"], 1)
        output_records = records((self.store.root / metadata["id"] / "map.pcd").read_bytes())
        self.assertEqual([record[3] for record in output_records], [100, 101, 102, 103, 105, 106, 107])
        self.assertIs(metadata["runtime_installed"], False)
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_unknown_fields_points_paths_and_preview_hints_are_rejected(self):
        for path in ((), ("source",), ("annotation",), ("annotation", "source"), ("annotation", "regions", 0)):
            for field, value in (("points", [0, 0, 0]), ("path", "/private/synthetic.pcd"), ("preview_count", 1)):
                with self.subTest(path=path, field=field):
                    request = self.request()
                    target = request
                    for component in path:
                        target = target[component]
                    target[field] = value
                    with self.assertRaises(PcdEditError):
                        self.store.save(request)
                    self.assert_unregistered()

    def test_stale_revision_hash_and_frame_are_rejected_against_trusted_resolver(self):
        for field, value in (("revision", "b" * 64), ("sha256", "b" * 64), ("frame_id", "other_frame")):
            with self.subTest(field=field):
                request = self.request()
                request["source"][field] = value
                if field in request["annotation"]["source"]:
                    request["annotation"]["source"][field] = value
                with self.assertRaises(PcdEditConflict):
                    self.store.save(request)
                self.assert_unregistered()
                self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_annotation_source_mismatch_is_rejected_before_reading_source(self):
        for field, value in (("map_id", "b" * 24), ("revision", "b" * 64), ("frame_id", "other_frame")):
            request = self.request()
            request["annotation"]["source"][field] = value
            with self.subTest(field=field), patch.object(self.store, "source_resolver") as resolver:
                with self.assertRaises(PcdEditConflict):
                    self.store.save(request)
                resolver.assert_not_called()
            self.assert_unregistered()

    def test_invalid_source_schema_roles_units_names_and_runtime_requests_are_rejected(self):
        mutations = [
            lambda v: v["source"].update(units="cm"),
            lambda v: v["source"].update(asset_role="sampled_preview"),
            lambda v: v["source"].update(map_id="../private"),
            lambda v: v["source"].update(revision=3),
            lambda v: v["source"].update(sha256="f" * 63),
            lambda v: v["source"].update(frame_id=""),
            lambda v: v.update(name="name with spaces"),
            lambda v: v.update(name="x" * 65),
            lambda v: v.update(purpose="keepout"),
            lambda v: v.update(schema="unsupported"),
            lambda v: v["annotation"].update(runtime_installed=True),
            lambda v: v["annotation"].update(schema_version=True),
            lambda v: v["annotation"].update(version_id=""),
            lambda v: v["annotation"]["regions"][0].update(z_min=float("nan")),
            lambda v: v["annotation"]["regions"][0].update(selection="all"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                request = self.request()
                mutate(request)
                with self.assertRaises(PcdEditError):
                    self.store.save(request)
                self.assert_unregistered()

    def test_trusted_resolver_cannot_relabel_a_preview_as_the_full_source(self):
        for changes in ({"units": "cm"}, {"asset_role": "sampled_preview"}, {"map_id": "b" * 24}):
            with self.subTest(changes=changes):
                self.assets[self.original_id] = replace(self.asset, **changes)
                with self.assertRaises(PcdEditError):
                    self.store.descriptor(self.original_id)
        self.assets[self.original_id] = self.asset
        with patch.object(self.store, "source_resolver", return_value={"path": self.source_path}):
            with self.assertRaises(PcdEditError):
                self.store.descriptor(self.original_id)

    def test_descriptor_rejects_source_identity_changed_by_resolver_callback(self):
        with patch.object(self.store, "source_resolver", side_effect=[self.asset, replace(self.asset, revision="b" * 64)]):
            with self.assertRaises(PcdEditConflict):
                self.store.descriptor(self.original_id)

    def test_original_changed_after_loading_descriptor_is_not_saved(self):
        request = self.request()
        self.source_path.write_bytes(self.original + b"changed")
        with self.assertRaises(PcdEditConflict):
            self.store.save(request)
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original + b"changed")

    def test_source_bytes_changed_during_codec_callback_roll_back_registration(self):
        request = self.request()

        def change_source(*args, **kwargs):
            result = filter_pcd(*args, **kwargs)
            self.source_path.write_bytes(self.original + b"changed-during-codec")
            return result

        with patch.object(store_module, "filter_pcd", side_effect=change_source):
            with self.assertRaises(PcdEditConflict):
                self.store.save(request)
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original + b"changed-during-codec")

    def test_same_bytes_with_changed_file_identity_do_not_publish(self):
        request = self.request()

        def change_source_metadata(*args, **kwargs):
            result = filter_pcd(*args, **kwargs)
            current = self.source_path.stat()
            os.utime(self.source_path, ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000))
            return result

        with patch.object(store_module, "filter_pcd", side_effect=change_source_metadata):
            with self.assertRaises(PcdEditConflict):
                self.store.save(request)
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_source_identity_changed_during_codec_callback_rolls_back_registration(self):
        request = self.request()

        def change_identity(*args, **kwargs):
            result = filter_pcd(*args, **kwargs)
            self.assets[self.original_id] = replace(self.asset, revision="b" * 64)
            return result

        with patch.object(store_module, "filter_pcd", side_effect=change_identity):
            with self.assertRaises(PcdEditConflict):
                self.store.save(request)
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_codec_partial_write_and_unexpected_exception_remove_entire_stage(self):
        for exception in (PcdEditError("unsupported fixture"), OSError("synthetic disk failure"), RuntimeError("synthetic callback failure")):
            with self.subTest(exception=type(exception).__name__):
                def fail_codec(_source, target, *_args, **_kwargs):
                    target.write_bytes(b"partial output")
                    raise exception

                with patch.object(store_module, "filter_pcd", side_effect=fail_codec):
                    with self.assertRaises(type(exception)):
                        self.store.save(self.request())
                self.assert_unregistered()
                self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_fsync_failure_at_each_commit_phase_leaves_no_registered_copy(self):
        real_fsync = store_module.os.fsync
        # Codec output, manifest, output recheck, stage directory, registry directory.
        for fail_at in range(1, 6):
            calls = 0

            def fail_sync(fd):
                nonlocal calls
                calls += 1
                if calls == fail_at:
                    raise OSError("synthetic fsync failure")
                return real_fsync(fd)

            with self.subTest(fail_at=fail_at), patch.object(store_module.os, "fsync", side_effect=fail_sync):
                with self.assertRaises((OSError, PcdEditError)):
                    self.store.save(self.request())
                self.assertEqual(calls, fail_at)
            self.assert_unregistered()
            self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_rename_failure_rolls_back_staged_output(self):
        with patch.object(store_module.os, "rename", side_effect=OSError("synthetic rename failure")):
            with self.assertRaises(OSError):
                self.store.save(self.request())
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_reader_cannot_observe_registration_that_fails_final_directory_fsync(self):
        request = self.request()
        pending_id = "e" * 24
        renamed = threading.Event()
        release_fsync = threading.Event()
        reader_started = threading.Event()
        reader_done = threading.Event()
        writer_errors, reader_results = [], []
        real_sync = store_module._sync_directory

        def hold_then_fail(path):
            if path != self.store.root:
                return real_sync(path)
            renamed.set()
            if not release_fsync.wait(timeout=5):
                raise AssertionError("test did not release directory fsync")
            raise OSError("synthetic final fsync failure")

        def write_copy():
            try:
                self.store.save(request)
            except BaseException as error:
                writer_errors.append(error)

        def read_copy():
            reader_started.set()
            try:
                reader_results.append(self.store.get(pending_id))
            except BaseException as error:
                reader_results.append(error)
            finally:
                reader_done.set()

        writer = threading.Thread(target=write_copy, daemon=True)
        reader = threading.Thread(target=read_copy, daemon=True)
        with patch.object(store_module, "_sync_directory", side_effect=hold_then_fail), \
             patch.object(store_module.uuid, "uuid4", return_value=SimpleNamespace(hex=pending_id + "0" * 8)):
            writer.start()
            try:
                self.assertTrue(renamed.wait(timeout=3), "writer never reached final directory fsync")
                self.assertTrue((self.store.root / pending_id / "manifest.json").is_file())
                reader.start()
                self.assertTrue(reader_started.wait(timeout=3))
                self.assertFalse(reader_done.wait(timeout=.1), "reader observed an uncommitted registration")
            finally:
                release_fsync.set()
                writer.join(timeout=3)
                if reader.ident is not None:
                    reader.join(timeout=3)
        self.assertFalse(writer.is_alive(), "writer did not finish rollback")
        self.assertFalse(reader.is_alive(), "reader remained blocked after rollback")
        self.assertEqual(len(writer_errors), 1)
        self.assertIsInstance(writer_errors[0], OSError)
        self.assertEqual(len(reader_results), 1)
        self.assertIsInstance(reader_results[0], FileNotFoundError)
        self.assert_unregistered()
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_collision_never_replaces_existing_directory_or_symlink(self):
        collision_id = "c" * 24
        self.store.root.mkdir()
        collision = self.store.root / collision_id
        collision.mkdir()
        sentinel = collision / "sentinel"
        sentinel.write_bytes(b"existing immutable data")
        with patch.object(store_module.uuid, "uuid4", return_value=SimpleNamespace(hex=collision_id + "0" * 8)):
            with self.assertRaises(PcdEditConflict):
                self.store.save(self.request())
        self.assertEqual(sentinel.read_bytes(), b"existing immutable data")
        sentinel.unlink()
        collision.rmdir()
        collision.symlink_to(self.source_path)
        with patch.object(store_module.uuid, "uuid4", return_value=SimpleNamespace(hex=collision_id + "0" * 8)):
            with self.assertRaises(PcdEditConflict):
                self.store.save(self.request())
        self.assertTrue(collision.is_symlink())
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assertEqual(list(self.store.root.glob(".stage-*")), [])

    def test_concurrent_saves_register_distinct_complete_immutable_outputs(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: self.store.save(deepcopy(request)), range(6)))
        self.assertEqual(len({item["id"] for item in results}), 6)
        self.assertEqual(len(self.store.list()), 6)
        self.assertEqual(len({item["sha256"] for item in results}), 1)
        for item in results:
            self.assertEqual(self.store.get(item["id"]), item)
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assertEqual(list(self.store.root.glob(".stage-*")), [])

    def test_concurrent_id_collision_has_exactly_one_winner(self):
        request = self.request()
        collision_id = "c" * 24
        barrier = threading.Barrier(2)

        def wait_for_both(*args, **kwargs):
            result = filter_pcd(*args, **kwargs)
            barrier.wait(timeout=10)
            return result

        def save_one(_):
            try:
                return self.store.save(deepcopy(request))
            except PcdEditConflict:
                return None

        with patch.object(store_module, "filter_pcd", side_effect=wait_for_both), \
             patch.object(store_module.uuid, "uuid4", return_value=SimpleNamespace(hex=collision_id + "0" * 8)):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(save_one, range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.store.list(), [next(item for item in results if item is not None)])
        self.assertEqual(self.store.get(collision_id)["point_count"], 5)
        self.assertEqual(list(self.store.root.glob(".stage-*")), [])
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_symlink_source_ancestor_root_and_lock_are_rejected_without_writing_targets(self):
        request = self.request()
        source_link = self.directory / "source-link.pcd"
        source_link.symlink_to(self.source_path)
        self.assets[self.original_id] = replace(self.asset, path=source_link)
        with self.assertRaises(PcdEditError):
            self.store.descriptor(self.original_id)
        with self.assertRaises(PcdEditError):
            self.store.save(request)
        parent_link = self.directory / "parent-link"
        parent_link.symlink_to(self.directory, target_is_directory=True)
        self.assets[self.original_id] = replace(self.asset, path=parent_link / self.source_path.name)
        with self.assertRaises(PcdEditError):
            self.store.save(request)
        root_link = self.directory / "root-link"
        root_link.symlink_to(self.store.root, target_is_directory=True)
        with self.assertRaises(PcdEditError):
            PcdEditStore(root_link, self.resolve)
        self.assets[self.original_id] = self.asset
        lock_target = self.directory / "lock-target"
        lock_target.write_bytes(b"untouched lock target")
        self.store.root.mkdir()
        (self.store.root / ".store.lock").symlink_to(lock_target)
        with self.assertRaises(OSError):
            self.store.save(request)
        self.assertEqual(lock_target.read_bytes(), b"untouched lock target")
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assert_unregistered()

    def test_manifest_hash_changes_invalid_fields_and_invalid_json_are_not_catalogued(self):
        metadata = self.store.save(self.request())
        manifest = self.store.root / metadata["id"] / "manifest.json"
        original_manifest = manifest.read_bytes()
        mutations = [
            lambda v: v.update(points=[0, 0, 0]),
            lambda v: v.update(runtime_installed=True),
            lambda v: v.update(units="cm"),
            lambda v: v.update(frame_id="other_frame"),
            lambda v: v.update(point_count=True),
            lambda v: v.update(point_count=999),
            lambda v: v.update(revision="b" * 64),
            lambda v: v.update(sha256="b" * 64),
            lambda v: v.update(file_name="../other.pcd"),
            lambda v: v["edit_history"][0].update(removed_points=99),
            lambda v: v["edit_history"][0]["annotation"].update(runtime_installed=True),
            lambda v: v.update(edit_history=[]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = deepcopy(metadata)
                mutate(value)
                manifest.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(PcdEditError):
                    self.store.get(metadata["id"])
                self.assertEqual(self.store.list(), [])
        for raw in (b"{broken", b"\xff\xff", b"[]", b"null"):
            manifest.write_bytes(raw)
            with self.assertRaises(PcdEditError):
                self.store.get(metadata["id"])
            self.assertEqual(self.store.list(), [])
        manifest.write_bytes(original_manifest)
        pcd = manifest.parent / "map.pcd"
        pcd.write_bytes(pcd.read_bytes() + b"tampered")
        with self.assertRaises(PcdEditError):
            self.store.get(metadata["id"])
        self.assertEqual(self.store.list(), [])

    def test_registered_manifest_directory_identity_and_symlinks_are_checked(self):
        metadata = self.store.save(self.request())
        original_directory = self.store.root / metadata["id"]
        other_directory = self.store.root / ("d" * 24)
        original_directory.rename(other_directory)
        with self.assertRaises(PcdEditError):
            read_manifest(other_directory)
        self.assertEqual(self.store.list(), [])
        original_directory.symlink_to(other_directory, target_is_directory=True)
        with self.assertRaises(PcdEditError):
            self.store.get(metadata["id"])
        self.assertEqual(self.store.list(), [])

    def test_second_generation_preserves_original_ancestry_and_appends_history(self):
        first = self.store.save(self.request())
        first_pcd = (self.store.root / first["id"] / "map.pcd").read_bytes()
        second_request = self.request(first["id"], purpose="localization")
        second_request["name"] = "synthetic_second_copy"
        second = self.store.save(second_request)
        self.assertNotEqual(second["id"], first["id"])
        self.assertNotEqual(second["revision"], first["revision"])
        self.assertEqual(second["source"]["map_id"], first["id"])
        self.assertEqual(second["source"]["revision"], first["revision"])
        self.assertEqual(second["source"]["sha256"], first["sha256"])
        self.assertEqual(second["origin"], first["origin"])
        self.assertEqual(second["origin"]["map_id"], self.original_id)
        self.assertEqual(second["edit_history"][:-1], first["edit_history"])
        self.assertEqual(len(second["edit_history"]), 2)
        self.assertEqual(second["edit_history"][-1]["input_points"], 5)
        self.assertEqual(second["edit_history"][-1]["output_points"], 4)
        self.assertEqual(second["edit_history"][-1]["annotation"], second_request["annotation"])
        self.assertEqual(second["point_count"], 4)
        self.assertEqual(second["frame_id"], first["frame_id"])
        self.assertEqual(second["units"], first["units"])
        self.assertEqual((self.store.root / first["id"] / "map.pcd").read_bytes(), first_pcd)
        self.assertEqual(self.source_path.read_bytes(), self.original)
        self.assertEqual(self.store.get(first["id"]), first)
        self.assertEqual(self.store.get(second["id"]), second)
        self.assertEqual(self.store.descriptor(second["id"])["sha256"], second["sha256"])

    def test_inherited_origin_and_history_must_connect_to_the_actual_root_and_point_counts(self):
        first = self.store.save(self.request())
        parent = self.resolve(first["id"])
        changes = ["origin_hash", "origin_id", "origin_revision", "history_root", "history_hash", "count_continuity"]
        for change in changes:
            with self.subTest(change=change):
                origin, history = deepcopy(parent.origin), deepcopy(parent.edit_history)
                if change == "origin_hash":
                    origin["sha256"] = "b" * 64
                elif change == "origin_id":
                    origin["map_id"] = "b" * 24
                elif change == "origin_revision":
                    origin["revision"] = "b" * 64
                elif change == "history_root":
                    history[0]["annotation"]["source"]["map_id"] = "b" * 24
                elif change == "history_hash":
                    history[0]["source_sha256"] = "b" * 64
                else:
                    # Keep this entry internally consistent but break its link to the next generation.
                    history[0]["output_points"] += 1
                    history[0]["removed_points"] -= 1
                self.assets[first["id"]] = replace(parent, origin=origin, edit_history=history)
                request = self.request(first["id"], purpose="localization")
                with self.assertRaises(PcdEditError):
                    self.store.save(request)
                self.assertEqual(self.store.list(), [first])
                self.assertEqual(list(self.store.root.glob(".stage-*")), [])
                self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_resolver_can_read_same_registry_parent_without_deadlocking_save(self):
        first = self.store.save(self.request())
        request = self.request(first["id"], purpose="localization")
        # A child process can be terminated if a nested shared/exclusive lock regression hangs.
        context = multiprocessing.get_context("fork")
        receiver, sender = context.Pipe(duplex=False)

        def save_child():
            try:
                metadata = self.store.save(request)
                sender.send({"id": metadata["id"]})
            except BaseException as error:
                sender.send({"error": type(error).__name__})
            finally:
                sender.close()

        process = context.Process(target=save_child)
        process.start()
        sender.close()
        try:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
                self.fail("resolver reading this registry deadlocked the save")
            self.assertEqual(process.exitcode, 0)
            self.assertTrue(receiver.poll(timeout=1), "save child returned no result")
            result = receiver.recv()
            self.assertNotIn("error", result)
            self.assertEqual(self.store.get(result["id"])["source"]["map_id"], first["id"])
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
            receiver.close()
            process.close()
        self.assertEqual(len(self.store.list()), 2)

    def test_bounded_full_source_and_point_limit_fail_without_partial_registration(self):
        request = self.request()
        small_bytes = PcdEditStore(self.directory / "byte-limited", self.resolve, max_bytes=len(self.original) - 1)
        with self.assertRaises(PcdEditError):
            small_bytes.descriptor(self.original_id)
        with self.assertRaises(PcdEditError):
            small_bytes.save(request)
        small_points = PcdEditStore(self.directory / "point-limited", self.resolve, max_points=7)
        with self.assertRaises(PcdEditError):
            small_points.save(request)
        self.assertEqual(small_bytes.list(), [])
        self.assertEqual(small_points.list(), [])
        self.assertEqual(list(small_bytes.root.glob(".stage-*")), [])
        self.assertEqual(list(small_points.root.glob(".stage-*")), [])
        self.assertEqual(self.source_path.read_bytes(), self.original)

    def test_request_validator_returns_defensive_copy_and_handles_non_json_values(self):
        request = self.request()
        validated = validate_request(request)
        request["source"]["frame_id"] = "changed"
        request["annotation"]["regions"][0]["polygon"][0][0] = 99
        self.assertEqual(validated["source"]["frame_id"], "camera_init")
        self.assertEqual(validated["annotation"]["regions"][0]["polygon"][0][0], -.1)
        for value in (None, [], {"object": object()}):
            with self.assertRaises(PcdEditError):
                validate_request(value)


if __name__ == "__main__":
    unittest.main()
