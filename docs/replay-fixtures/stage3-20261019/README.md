# Stage 3: three stored LiDAR scans, offline replay

This packet contains one complete saved PCD map (25,666 XYZ points), three complete received `PointCloud2.data` payloads (16,000 points each), their lossless float64 XYZ conversions, the stationary capture manifest, and recorded global observation results with ambiguity opt-in OFF and ON. The numeric map and scans can reveal the indoor layout; publication was explicitly approved. No robot connection or ROS node is needed to inspect or replay them.

The three `.pointcloud2-data.bin` files are **message data fields**, with their original layout and header stamps in `capture/manifest.json`; they are not complete CDR messages. The XYZ files preserve all finite received XYZ rows in source order. The saved map has not been cropped, sampled, transformed, or rounded for scoring. The map PCD SHA-256 is `c347faea6fd7a2f353b39f1f69f93cab8f2c6243299f90f87e54b7d8172ce4b8`; its full float64 XYZ SHA-256 is `2e436c8cd41db44ac7130d81df8b23dd01e4875dd42ffcb1c1dbd18780da5852`. `PUBLIC_MANIFEST.json` lists the exact byte size, SHA-256, and origin of each copied file. Its `DESKTOP_*` entries are generated reports or a receipt-generated source pin, **not** upstream original files.

## Inspect and recheck stored scores

Requires Python 3.10 or later, NumPy, and SciPy. From this directory:

```sh
python3 replay_saved_scans.py verify
```

This verifies the listed files, fixed source hashes, full PCD and raw scan layouts, every raw-to-XYZ conversion, capture identity, and the selected ON candidate's recorded score against **all 16,000 scan points and all 25,666 map points** using a SciPy nearest-neighbor tree. The 0.75 m association radius is part of the original scoring method. This command checks an existing score; it does not run registration or choose a candidate.

## Run the pinned original backend again

The separately provided v0.3.1 `auto_localization` source and a Python environment with its dependencies (including Open3D) are deliberately **not included**. Supply absolute paths to that source, its interpreter, and `reference/runtime-pin.receipt-generated.json`. The committed Robot Scope dashboard checkout must contain `ExternalGlobalObservationRunner` from commit `629a085` or a later compatible commit. Example for one scan:

```sh
python3 replay_saved_scans.py replay \
  --dashboard-root /absolute/path/to/dashboard-checkout \
  --backend-python /absolute/path/to/backend-python \
  --backend-source /absolute/path/to/pinned-v031-source \
  --pin-file "$(pwd)/reference/runtime-pin.receipt-generated.json" \
  --output-dir /absolute/path/to/new-output-directory \
  --mode on --scan-index 0
```

Use `--mode off` for the original ambiguity gate; omit `--scan-index` for all three scans. The output directory must not exist and must be outside this packet. The script uses only committed dashboard runner code and the exact full arrays; it does not depend on local uncommitted offline or scan-timing helpers. The source pin enforces the complete reviewed backend file set and each source SHA-256. It also distinguishes the desktop-generated pin from the original source distribution. The same original backend is used with an explicit ambiguity flag; neither source files nor scans are patched.

Saved OFF results rejected all three selections with `AMBIGUOUS_ALTERNATIVES`. With explicit ON, the chosen observation-only candidate indices were 10, 8, and 0. Their original full-input RMSE values were 0.154952336, 0.157923874, and 0.254278264 m, with overlap 1.0, 1.0, and 0.934375. The original top and candidate ambiguity reasons remain in the ON result. ON uses the lowest eligible `rmse_m`, then the original candidate array index; this can differ from the backend's other rankings. The recorded scores exceed both the retained 5 cm and provisional 10 cm comparison thresholds. No threshold, input population, or original source was changed to claim an improvement.

## Interpretation limits

The map frame name `camera_init` and metre unit are product conventions, not independently validated map axes or scale. The scan frame is `hesai_lidar`. These are historical sensor candidates at the source header times; their clock domain and native session remain unverified. Receipt times and source times are separate. The capture contains odometry and TF observations for timing review, but this replay performs no clock-domain proof, scan deskew, timestamp interpolation, body extrinsic calibration, current-position propagation, or continuous tracking. The physical stillness of the robot, absolute position error, body pose, and navigation safety were not independently verified. `map_id` and `map_revision` in the recorded context refer to the original saved-map catalogue and depend on its original path/filesystem identity; copying the PCD changes a new catalogue's ID/revision. Replay keeps those values only as historical provenance and binds the actual map by its full content hash.
