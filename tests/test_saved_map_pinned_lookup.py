"""Request-scoped catalog admission retains fresh asset/content validation."""
import json
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.pcd_editing.store import REQUEST_SCHEMA
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapNotFound
from test_pcd_editing_store import cloud_bytes, region


class SavedMapPinnedLookupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root / 'first.json'
        self.path.write_text(json.dumps({'points': [1, 2, 3], 'frame_id': 'map'}))
        self.catalog = SavedMapCatalog([self.root], managed_roots=[self.root])
        self.item = self.catalog.list_snapshot()['maps'][0]

    def test_nested_scope_scans_once_and_does_not_cache_across_requests(self):
        with patch.object(self.catalog, '_scan', wraps=self.catalog._scan) as scan:
            with self.catalog.pinned_lookup():
                self.assertEqual(self.catalog.metadata(self.item['id']), self.item)
                with self.catalog.pinned_lookup():
                    self.assertEqual(self.catalog.metadata(self.item['id']), self.item)
                self.assertEqual(self.catalog.metadata(self.item['id']), self.item)
            self.assertEqual(scan.call_count, 1)
            self.assertIsNone(self.catalog._pinned_records)
            with self.catalog.pinned_lookup():
                self.catalog.metadata(self.item['id'])
            self.assertEqual(scan.call_count, 2)
            self.catalog.metadata(self.item['id'])
            self.assertEqual(scan.call_count, 3)

    def test_replacement_revalidates_contents_and_revision_within_scope(self):
        with self.catalog.pinned_lookup():
            replacement = self.root / 'replacement.tmp'
            replacement.write_text(json.dumps({'points': [4, 5, 6, 7, 8, 9], 'frame_id': 'changed'}))
            replacement.replace(self.path)
            current = self.catalog.metadata(self.item['id'])
            self.assertNotEqual(current['revision'], self.item['revision'])
            self.assertEqual(current['point_count'], 2)
            self.assertEqual(current['frame_id'], 'changed')
            self.path.write_text('invalid JSON')
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(self.item['id'])

    def test_deletion_rename_and_new_id_are_rejected_until_new_request(self):
        with self.catalog.pinned_lookup():
            renamed = self.root / 'renamed.json'
            self.path.rename(renamed)
            new = self.catalog._record_for(self.root, renamed)
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(self.item['id'])
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(new.map_id)
        with self.catalog.pinned_lookup():
            self.assertEqual(self.catalog.metadata(new.map_id)['name'], 'renamed')
            renamed.unlink()
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(new.map_id)

    def test_admission_keeps_max_files_limit(self):
        second = self.root / 'second.json'
        second.write_text(self.path.read_text())
        os.utime(self.path, ns=(1_000_000_000, 1_000_000_000))
        os.utime(second, ns=(2_000_000_000, 2_000_000_000))
        self.catalog.max_files = 1
        with self.catalog.pinned_lookup():
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(self.item['id'])
            admitted = self.catalog._record_for(self.root, second)
            self.assertEqual(self.catalog.metadata(admitted.map_id)['name'], 'second')

    def test_scope_cleanup_after_nested_and_admission_exceptions(self):
        with self.assertRaisesRegex(RuntimeError, 'nested failure'):
            with self.catalog.pinned_lookup():
                with self.catalog.pinned_lookup():
                    raise RuntimeError('nested failure')
        self.assertIsNone(self.catalog._pinned_records)
        with patch.object(self.catalog, '_scan', side_effect=RuntimeError('scan failure')):
            with self.assertRaisesRegex(RuntimeError, 'scan failure'):
                with self.catalog.pinned_lookup():
                    self.fail('admission must fail')
        self.assertIsNone(self.catalog._pinned_records)
        with self.catalog.pinned_lookup():
            self.assertEqual(self.catalog.metadata(self.item['id']), self.item)

    def test_retained_path_references_skip_discovery_but_reread_each_target(self):
        with self.catalog.pinned_lookup() as admitted:
            references = (admitted[self.item['id']],)
        self.path.write_text(json.dumps({'points': [7, 8, 9], 'frame_id': 'new-frame'}))
        with patch.object(self.catalog, '_scan', side_effect=AssertionError('must not rescan')):
            with self.catalog.pinned_lookup(references=references):
                self.assertEqual(self.catalog.metadata(self.item['id'])['frame_id'], 'new-frame')
                self.path.unlink()
                with self.assertRaises(SavedMapNotFound):
                    self.catalog.metadata(self.item['id'])
        self.assertIsNone(self.catalog._pinned_records)

    def test_reference_roots_paths_and_id_correspondence_are_checked(self):
        with self.catalog.pinned_lookup() as admitted:
            record = admitted[self.item['id']]
        for invalid in (replace(record, root=self.root.parent),
                        replace(record, path=self.root.parent / 'escaped.json'),
                        replace(record, path=self.root / '.hidden.json'),
                        replace(record, map_id='bad'), None):
            with self.subTest(reference=invalid), self.assertRaises(SavedMapNotFound):
                with self.catalog.pinned_lookup(references=(invalid,)):
                    self.fail('invalid reference admitted')
            self.assertIsNone(self.catalog._pinned_records)
        forged = replace(record, map_id='f' * 24)
        with self.catalog.pinned_lookup(references=(forged,)):
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(forged.map_id)

    def test_edited_manifest_full_hash_is_rechecked_even_with_same_size_and_mtime(self):
        source_path = self.root / 'source.pcd'
        source_path.write_bytes(cloud_bytes())
        original = next(item for item in self.catalog.list_snapshot()['maps'] if item['name'] == 'source')
        source = self.catalog.pcd_edit_source(original['id'])
        request = {'schema': REQUEST_SCHEMA, 'name': 'derived', 'purpose': 'visibility',
                   'source': source, 'annotation': {
                       'schema': 'robot-dashboard.map-editor3d', 'schema_version': 1,
                       'version_id': 'pinned-lookup-fixture', 'runtime_installed': False,
                       'source': {key: source[key] for key in ('map_id', 'revision', 'frame_id')},
                       'regions': [region()]}}
        edited = self.catalog.save_pcd_edited_copy(original['id'], request)
        path = self.root / 'pcd-edits' / edited['id'] / 'map.pcd'
        with self.catalog.pinned_lookup() as admitted:
            references = (admitted[edited['id']],)
        with self.catalog.pinned_lookup(references=references):
            self.catalog.metadata(edited['id'])
            before = path.stat()
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            with self.assertRaises(SavedMapNotFound):
                self.catalog.metadata(edited['id'])


if __name__ == '__main__':
    unittest.main()
