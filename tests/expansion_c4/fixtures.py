"""Fixed contract doubles, not D2/D3 algorithm implementations."""
from copy import deepcopy
from dataclasses import replace
import struct
from types import SimpleNamespace as NS

from robot_dashboard.obstacle_runtime_adapter.messages import Identity


def identity(**kwargs):
    return replace(Identity("lidar", "epoch-1", 1, "1000000000", "fixture_ros", "review_lidar",
                            1_000_000_000, "host-fixture", "tf-1"), **kwargs)


def header(stamp="1000000000", frame="review_lidar"):
    sec, ns = divmod(int(stamp), 1_000_000_000)
    return NS(stamp=NS(sec=sec, nanosec=ns), frame_id=frame)


def cloud(*, big=False, double=False, stamp="1000000000", frame="review_lidar", invalid=False):
    """Two rows with nonstandard field order, intensity and row padding."""
    size, fmt, dtype = (8, "d", 8) if double else (4, "f", 7)
    step, row = size*3 + 4, size*3 + 12
    data = bytearray(row*2)
    for i, p in enumerate(((1., 2., 3.), (4., 5., float("nan") if invalid else 6.))):
        for name, offset, value in (("y", 0, p[1]), ("x", size, p[0]), ("z", size*2+4, p[2])):
            struct.pack_into((">" if big else "<")+fmt, data, i*row+offset, value)
        struct.pack_into((">" if big else "<")+"I", data, i*row+size*2, 17+i)
    return NS(header=header(stamp, frame), width=1, height=2, point_step=step, row_step=row,
        is_bigendian=big, data=bytes(data), fields=[
            NS(name=n, offset=o, datatype=d, count=1) for n, o, d in
            (("y", 0, dtype), ("x", size, dtype), ("intensity", size*2, 6), ("z", size*2+4, dtype))])


def image(*, big=False, encoding="16UC1", values=(0, 1000, 65000), frame="review_lidar"):
    fmt, size = ("H", 2) if encoding == "16UC1" else ("f", 4)
    data = struct.pack((">" if big else "<")+fmt*len(values), *values) + b"pad!"
    return NS(header=header(frame=frame), width=len(values), height=1, step=len(data),
              is_bigendian=big, encoding=encoding, data=data)


def camera():
    return NS(header=header(), width=3, height=1, distortion_model="plumb_bob", d=[0.]*5,
        k=[100., 0., 1., 0., 100., 0., 0., 0., 1.], r=[1., 0., 0., 0., 1., 0., 0., 0., 1.],
        p=[100., 0., 1., 0., 0., 100., 0., 0., 0., 0., 1., 0.], binning_x=0, binning_y=0,
        roi=NS(x_offset=0, y_offset=0, width=0, height=0, do_rectify=False))


def pose_message(stamp="1000000000", frame="review_lidar", x=0.):
    return NS(header=header(stamp, frame), pose=NS(position=NS(x=x, y=0., z=.2),
                          orientation=NS(x=0., y=0., z=0., w=1.)))


class D2Fixture:
    """Pass a fixed fixture object plus unmodified input identity. No perception."""
    def __init__(self):
        self.calls = 0

    def process(self, sample):
        self.calls += 1
        return {"schema_version": "robot-scope.obstacle-frame.v1", **sample.identity.packet(),
            "calibration_id": None, "input_sources": [sample.identity.source_id],
            "obstacles": [], "health": {"fixture_only": True}, "dropped_counts": {},
            "provenance": {"source_identity": sample.identity.packet(), "kind": sample.kind}}


class C1Fixture:
    def __init__(self):
        self.latest = None
        self.count = 0

    def ingest(self, packet):
        self.latest = deepcopy(packet)
        self.count += 1

    def snapshot(self):
        return deepcopy(self.latest)


def fixture_validator(frame):
    # Bootstrap fixture assertion, deliberately not a shared schema validator.
    assert frame["schema_version"] == "robot-scope.obstacle-frame.v1"


def occupancy(stamp="1000000001", frame="map", data=(0, 100, -1, 0)):
    return NS(header=header(stamp, frame), info=NS(width=2, height=2, resolution=.05,
        origin=pose_message().pose), data=list(data))


def path(stamp="1000000002", x=0.):
    return NS(header=header(stamp, "map"), poses=[pose_message(stamp, "map", x=x)])
