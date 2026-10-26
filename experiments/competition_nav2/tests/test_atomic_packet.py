"""Compile the opt-in recorder against a tiny map; this is not a Nav2 re-run."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

OVERLAY = Path(__file__).resolve().parents[1] / "overlay"


@unittest.skipUnless(
    shutil.which("g++") and Path("/usr/include/nlohmann/json.hpp").exists(),
    "C++/JSON headers unavailable",
)
class AtomicPacketTests(unittest.TestCase):
    def test_raw_snapshot_identity_mutation_detection_and_opt_in(self):
        code = r"""
#include "c3_atomic_packet.hpp"
struct XYZ {double x=0,y=0,z=0;};
struct Q {double x=0,y=0,z=0,w=1;};
struct Pose {XYZ position;Q orientation;};
struct Map {
 unsigned char values[4]={0,78,254,255};
 unsigned getSizeInCellsX(){return 2;} unsigned getSizeInCellsY(){return 2;}
 double getResolution(){return .02;} double getOriginX(){return -.1;} double getOriginY(){return 2.;}
 unsigned char* getCharMap(){return values;}
};
int main(int argc,char** argv){
 Map map;Pose p;std::vector<XYZ> body={{.435,.31,0},{-.435,.31,0},{-.435,-.31,0},{.435,-.31,0}};
 unsetenv("C3_ATOMIC_DIR");
 c3_atomic::Packet<Map> disabled(&map,body,p,p,10,"map",false);disabled.finish(true,20);
 setenv("C3_ATOMIC_DIR",argv[1],1);
 c3_atomic::Packet<Map> same(&map,body,p,p,123,"map",false);
 same.segment(97,body,1,2,3,4,5,6,false);same.finish(true,456);
 c3_atomic::Packet<Map> changed(&map,body,p,p,124,"map",false);
 map.values[2]=0;changed.finish(false,457);
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "probe.cpp").write_text(code)
            subprocess.run(
                [
                    "g++",
                    "-std=c++17",
                    "-O2",
                    "-Wall",
                    "-Werror",
                    "-I",
                    str(OVERLAY),
                    str(path / "probe.cpp"),
                    "-o",
                    str(path / "probe"),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [str(path / "probe"), str(path / "packets")],
                check=True,
                env={
                    **os.environ,
                    "C3_SOURCE_SHA": "test-source",
                    "C3_IMAGE_ID": "test-image",
                },
            )
            packets = sorted((path / "packets").glob("*.json"))
            self.assertEqual(len(packets), 2)
            first, second = [json.loads(p.read_text()) for p in packets]
            self.assertTrue(first["raw_unchanged_under_lock"])
            self.assertFalse(second["raw_unchanged_under_lock"])
            self.assertEqual(
                (path / "packets/plan-1.bin").read_bytes(), bytes([0, 78, 254, 255])
            )
            self.assertEqual(
                (path / "packets/plan-2.bin").read_bytes(), bytes([0, 78, 254, 255])
            )
            self.assertEqual(first["source_sha"], "test-source")
            self.assertEqual(first["lock_capture_ros_ns"], 123)
            self.assertIsNone(first["raw_costmap_update_stamp"])
            self.assertEqual(first["segments"][0]["index"], 97)
            self.assertFalse(
                first["segments"][0]["actual_supplemental_checker_collision"]
            )
            self.assertEqual(first["resolution"], 0.02)
            self.assertEqual(first["origin"], [-0.1, 2.0])
