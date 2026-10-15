# Native packages and compatibility

`slam_packages.MapPackageStore` owns private0700 roots,0600 metadata/artifacts,
opaque np_ UUIDs and expected revisions. Layout: packages/<id>/manifest.json,
native/, preview/; staging/ and scratch/ are not catalog entries.

Publication requires official native save completion, declared required files,
nonempty artifacts, write quiescence, finite bounded preview, relative path/
size/SHA256 inventory and atomic rename. Timeout/partial saves never appear as
successful maps. A timed-out writer is stopped and settled before staging is
discarded. Cleanup uncertainty retains ownership/private files. Preview is
approximate unless an authoritative common native snapshot ID is available.
Camera pixels are excluded from saved previews.

Display rename preserves ID/native bytes and changes metadata revision. Copy/
export/import verify original hashes. Native bytes are never parsed or edited.
Archives reject traversal, absolute/backslash/drive paths, links, special files,
duplicate entries, unsupported compression, too many/large files and excessive
compression ratios. Imported validation flags are reset to unknown. Active
references prevent mutation/deletion; active MS/MR/Nav context further blocks
mutations. Session native loads use a new scratch copy and retain original refs.

Compatibility requires matching engine/version/native format/calibration hash/
sensor config hash. Unknown or mismatched evidence is preview-only. Contract
content hashes identify configuration; they do not prove measured camera-body
calibration or accuracy. Native load is not successful localization. VSLAM sparse
maps are never occupancy/free-space/Nav2 maps. Existing LiDAR IDs, PCD/PGM/YAML,
annotations, lineage and catalog are preserved; the UI presents native packages
beside their existing catalog with engine filters.

No verified VSLAM↔navigation alignment exists. Same names/site IDs do not align
coordinate systems. Stage17 must verify transforms, units, revisions and actual
operational pose before any later navigation use.
