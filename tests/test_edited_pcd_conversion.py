"""Actual immutable PCD -> occupancy publication and retained mutation guards."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot_dashboard.pcd_editing.store import _revision
from robot_dashboard.saved_maps import SavedMapCatalog, SavedMapConflict, SavedMapReadOnly
from tests.test_edited_map_global_reference import POINTS, edit_request
from tests.test_saved_maps import write_pcd


class EditedPcdConversionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.parent = self.root/'source.pcd'
        write_pcd(self.parent,[row[:3] for row in POINTS])
        self.catalog = SavedMapCatalog([self.root],managed_roots=[self.root])
        self.raw = self.catalog.list_snapshot()['maps'][0]
        descriptor = self.catalog.pcd_edit_source(self.raw['id'])
        self.edited = self.catalog.save_pcd_edited_copy(self.raw['id'],edit_request(descriptor))
        self.directory = self.root/'pcd-edits'/self.edited['id']
        self.parameters = dict(z_min=-.2,z_max=2.,resolution=.05,noise_radius=.1,min_neighbors=1)

    def test_conversion_pins_full_edited_population_and_keeps_source_immutable(self):
        before = {p:p.read_bytes() for p in [self.parent,self.directory/'map.pcd',self.directory/'manifest.json']}
        metadata = self.catalog.metadata(self.edited['id'])
        self.assertFalse(metadata['manageable'])
        validated = self.catalog.validate_pcd_conversion(self.edited['id'],'crop_2d',**self.parameters)
        self.assertEqual(validated['source']['revision'],self.edited['revision'])
        result = self.catalog.convert_pcd_to_2d(self.edited['id'],'crop_2d',
            expected_revision=self.edited['revision'],**self.parameters)
        self.assertEqual(result['details']['source_points'],3)
        self.assertEqual(result['details']['z_slice_points'],2)
        family = result['map']['map_family']
        self.assertEqual(family['source']['pcd_map_id'],self.edited['id'])
        self.assertEqual(family['source']['pcd_revision'],self.edited['revision'])
        self.assertNotEqual(family['source']['pcd_map_id'],self.raw['id'])
        self.assertEqual(family['frame_projection']['method'],'planar_xy_identity')
        self.assertTrue(result['map']['manageable'])
        for p,data in before.items():
            self.assertEqual(p.read_bytes(),data)
        self.assertFalse(self.catalog.metadata(self.edited['id'])['manageable'])
        for mutate in [lambda:self.catalog.rename(self.edited['id'],'replaced'),
                       lambda:self.catalog.delete(self.edited['id'])]:
            with self.assertRaises(SavedMapReadOnly):
                mutate()
        self.assertFalse((self.root/'.robot_scope_transactions').exists())

    def test_unmanaged_raw_source_is_still_read_only(self):
        readonly = SavedMapCatalog([self.root])
        raw = next(m for m in readonly.list_snapshot()['maps'] if m['file_name']=='source.pcd')
        with self.assertRaises(SavedMapReadOnly):
            readonly.validate_pcd_conversion(raw['id'],'unauthorized',**self.parameters)
        with self.assertRaises(SavedMapReadOnly):
            readonly.convert_pcd_to_2d(raw['id'],'unauthorized',**self.parameters)
        self.assertFalse((self.root/'unauthorized.yaml').exists())

    def test_semantic_revision_change_after_validation_is_rejected(self):
        self.catalog.validate_pcd_conversion(self.edited['id'],'stale_2d',**self.parameters)
        path = self.directory/'manifest.json'
        metadata = json.loads(path.read_text())
        metadata['name'] = 'new-semantic-revision'
        metadata['revision'] = _revision(metadata)
        path.write_text(json.dumps(metadata))
        with self.assertRaises(SavedMapConflict):
            self.catalog.convert_pcd_to_2d(self.edited['id'],'stale_2d',
                expected_revision=self.edited['revision'],**self.parameters)
        self.assertFalse((self.root/'stale_2d.yaml').exists())

    def test_manifest_only_race_during_projection_prevents_publication(self):
        project = self.catalog._project_xy_occupancy
        source_before = (self.directory/'map.pcd').read_bytes()
        def replace_manifest(*args):
            result = project(*args)
            path = self.directory/'manifest.json'
            metadata = json.loads(path.read_text())
            metadata['name'] = 'changed-during-projection'
            metadata['revision'] = _revision(metadata)
            path.write_text(json.dumps(metadata))
            return result
        with patch.object(self.catalog,'_project_xy_occupancy',side_effect=replace_manifest):
            with self.assertRaises(SavedMapConflict):
                self.catalog.convert_pcd_to_2d(self.edited['id'],'raced_2d',
                    expected_revision=self.edited['revision'],**self.parameters)
        self.assertEqual((self.directory/'map.pcd').read_bytes(),source_before)
        self.assertFalse(any(self.root.glob('raced_2d.*')))
        self.assertFalse((self.root/'.robot_scope_transactions').exists())


if __name__ == '__main__':
    unittest.main()
