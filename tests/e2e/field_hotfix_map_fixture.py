"""Synthetic map files for the display/crop browser regression."""
import json
import math
from pathlib import Path
import sys

from robot_dashboard.saved_maps import SavedMapCatalog
from test_saved_maps import write_pcd

root = Path(sys.argv[1]).resolve()
catalog = SavedMapCatalog([root], managed_roots=[root], preview_points=10)
command = sys.argv[2]
if command == "init":
    write_pcd(root / "hall.pcd", [(x * .5, y * .5, .2) for x in range(12) for y in range(8)])
    for name, width, height, origin in (("arena", 12, 8, [1., 2., math.pi / 2]), ("other", 8, 6, [-2., -3., 0.])):
        cells = bytes([0, 255, 205] * ((width * height) // 3))
        (root / (name + ".pgm")).write_bytes(("P5\n" + str(width) + " " + str(height) + "\n255\n").encode() + cells)
        (root / (name + ".yaml")).write_text(
            "image: " + name + ".pgm\nresolution: 0.5\norigin: " + json.dumps(origin) +
            "\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n"
        )
    source = next(item for item in catalog.list_snapshot()["maps"] if item["kind"] == "pointcloud3d")
    catalog.convert_pcd_to_2d(source["id"], "projection", z_min=-.2, z_max=.8, resolution=.05, min_neighbors=1)
    value = catalog.list_snapshot()
elif command == "list":
    value = catalog.list_snapshot()
elif command == "data":
    value = catalog.data(sys.argv[3])
elif command == "family":
    value = catalog.map_family(sys.argv[3])
elif command == "crop":
    body = json.loads(sys.argv[4])
    value = {"map": catalog.save_cropped_copy(sys.argv[3], body["name"], body["source_revision"], body["crop"])}
else:
    raise ValueError(command)
print(json.dumps(value))
