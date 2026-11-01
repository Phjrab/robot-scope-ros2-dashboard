import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from robot_dashboard.multimap_core.exporter import (
    export,
    ExportError,
    source_key,
    provenance_roots,
)
from robot_dashboard.pcd_editing.pcd import _read_header


def make_pcd(path, points=9, extra=False, vector=False):
    fields = [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("normal_x", "<f4"),
        ("normal_y", "<f4"),
        ("normal_z", "<f4"),
        ("intensity", "<u8"),
        ("time", "<f8"),
    ]
    if extra:
        fields += [("ring", "<u2")]
    if vector:
        fields += [("velocity_x", "<f4")]
    dtype = np.dtype(fields)
    records = np.zeros(points, dtype=dtype)
    records["x"] = np.arange(points)
    records["z"] = 1
    records["normal_x"] = 1
    records["intensity"] = np.arange(points, dtype=np.uint64) + 2**60
    records["time"] = np.arange(points) * 0.01
    header = (
        "VERSION .7\nFIELDS "
        + " ".join(dtype.names)
        + "\nSIZE "
        + " ".join(str(dtype[n].itemsize) for n in dtype.names)
        + "\nTYPE "
        + " ".join("F" if dtype[n].kind == "f" else "U" for n in dtype.names)
        + "\nCOUNT "
        + " ".join("1" for n in dtype.names)
        + f"\nWIDTH {points}\nHEIGHT 1\nVIEWPOINT 1 2 3 1 0 0 0\nPOINTS {points}\nDATA binary\n"
    )
    path.write_bytes(header.encode() + records.tobytes())
    return records


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths, self.sources = {}, []
        for i in range(2):
            path = self.root / f"{i}.pcd"
            self.records = make_pcd(path)
            source = dict(
                map_id=str(i),
                revision="r1",
                frame_id="camera_init",
                units="m",
                asset_role="full_source",
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            self.sources.append(source)
            self.paths[str(i)] = path
        transform = np.array(
            [[0, -1, 0, 2], [1, 0, 0, 3], [0, 0, 1, 0], [0, 0, 0, 1.0]]
        )
        self.proposal = dict(
            status="SOLVED_CANDIDATE",
            proposal_revision=1,
            sources=self.sources,
            input_pins=self.sources,
            manual_history=[{"kind": "manual_seed"}],
            anchor_source_key=source_key(self.sources[0]),
            T_fused_source=[
                dict(source_key=source_key(s), T=t.tolist())
                for s, t in zip(self.sources, [np.eye(4), transform])
            ],
            occupancy_surface=dict(name="floor1", z_min=0.2, z_max=2, resolution=0.1),
        )

    def run_export(self, proposal=None):
        return export(
            proposal or self.proposal,
            1,
            lambda s: self.paths[s["map_id"]],
            self.root / "out",
            chunk_points=2,
        )

    def test_full_chunk_fields_normals_occupancy_immutable_idempotent(self):
        manifest = self.run_export()
        folder = self.root / "out" / manifest["revision"]
        with (folder / "merged.pcd").open("rb") as stream:
            lines, _, dtype, count, _ = _read_header(
                stream, (folder / "merged.pcd").stat().st_size, 100
            )
            output = np.frombuffer(stream.read(), dtype=dtype)
        self.assertEqual(count, 18)
        self.assertNotIn("VIEWPOINT", [key for key, _ in lines])
        np.testing.assert_array_equal(
            output["intensity"][:9], self.records["intensity"]
        )
        np.testing.assert_array_equal(
            output["intensity"][9:], self.records["intensity"]
        )
        np.testing.assert_allclose(output["x"][9:], 2)
        np.testing.assert_allclose(output["y"][9:], self.records["x"] + 3)
        np.testing.assert_allclose(output["normal_y"][9:], 1)
        np.testing.assert_allclose(output["normal_x"][9:], 0)
        occupancy = json.loads((folder / "occupancy.json").read_text())
        self.assertEqual(occupancy["background"], "UNKNOWN")
        self.assertEqual(occupancy["free_cells"], [])
        self.assertIn([20, 30], occupancy["occupied_cells"])
        self.assertFalse(manifest["operational_installed"])
        self.assertEqual(manifest["manual_history"], self.proposal["manual_history"])
        self.assertEqual(manifest["producer"], "multimap_core.exporter")
        self.assertIn("source_epoch", manifest)
        self.assertEqual(manifest, self.run_export())
        for source in self.sources:
            self.assertEqual(
                source["sha256"],
                hashlib.sha256(self.paths[source["map_id"]].read_bytes()).hexdigest(),
            )

    def test_stale_revision_and_hash(self):
        with self.assertRaisesRegex(ExportError, "revision"):
            export(
                self.proposal, 2, lambda s: self.paths[s["map_id"]], self.root / "out"
            )
        self.sources[0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ExportError, "hash"):
            self.run_export()
        self.assertEqual(list((self.root / "out").glob(".stage-*")), [])

    def test_schema_mismatch_and_unknown_vector_rejected(self):
        make_pcd(self.paths["1"], extra=True)
        self.sources[1]["sha256"] = hashlib.sha256(
            self.paths["1"].read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(ExportError, "schemas"):
            self.run_export()
        for s in self.sources:
            make_pcd(self.paths[s["map_id"]], vector=True)
            s["sha256"] = hashlib.sha256(
                self.paths[s["map_id"]].read_bytes()
            ).hexdigest()
        with self.assertRaisesRegex(ExportError, "vector"):
            self.run_export()

    def test_cancel_and_unselected_height_surface(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["status"] = "CANCELED"
        with self.assertRaises(ExportError):
            self.run_export(proposal)
        proposal = copy.deepcopy(self.proposal)
        proposal.pop("occupancy_surface")
        self.assertEqual(
            self.run_export(proposal)["occupancy"]["status"], "UNSUPPORTED"
        )

    def test_provenance_incremental_duplicate_cycle_depth(self):
        sources = copy.deepcopy(self.sources)
        sources[0]["provenance"] = {"id": "AB", "parents": [{"id": "A"}, {"id": "B"}]}
        sources[1]["provenance"] = {"id": "C"}
        self.assertEqual(provenance_roots(sources), ["A", "B", "C"])
        sources[1]["provenance"] = {"id": "BC", "parents": [{"id": "B"}, {"id": "C"}]}
        with self.assertRaisesRegex(ExportError, "Duplicate"):
            provenance_roots(sources)
        sources[0]["provenance"] = {"id": "A", "parents": [{"id": "A"}]}
        with self.assertRaisesRegex(ExportError, "cycle"):
            provenance_roots(sources)
        node = {"id": "leaf"}
        for i in range(35):
            node = {"id": str(i), "parents": [node]}
        sources[0]["provenance"] = node
        with self.assertRaisesRegex(ExportError, "bounds"):
            provenance_roots(sources)

    def test_pin_tamper_and_stale_idempotent_source(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["input_pins"] = copy.deepcopy(proposal["sources"])
        proposal["input_pins"][0]["revision"] = "stale"
        with self.assertRaisesRegex(ExportError, "pins"):
            self.run_export(proposal)
        self.run_export()
        self.paths["0"].write_bytes(b"changed")
        with self.assertRaisesRegex(ExportError, "idempotent"):
            self.run_export()

    def test_corrupt_idempotent_output_rejected(self):
        manifest = self.run_export()
        (self.root / "out" / manifest["revision"] / "merged.pcd").write_bytes(b"broken")
        with self.assertRaisesRegex(ExportError, "corrupt"):
            self.run_export()


if __name__ == "__main__":
    unittest.main()
