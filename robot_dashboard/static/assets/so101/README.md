# TheRobotStudio SO-101 official-derived web model

`so101-official-lite.json` is a lightweight browser derivative of the SO-101
new-calibration URDF published by the robot's original project. Hugging Face's
LeRobot documentation directs users to this SO-ARM100 `Simulation/SO101`
folder, and LeRobot's hosted robot-URDF collection carries the same model.

## Provenance

- Upstream project: [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100)
- Upstream commit: `7629d2ad9853d10fb903093a33ef6114099d97e5`
- Source path: `Simulation/SO101`
- Source URDF: `source/SO101/so101_new_calib.urdf`
- Visual meshes: all 13 referenced STL files under `source/SO101/assets/`
- Official LeRobot guide: [phone teleoperation](https://github.com/huggingface/lerobot/blob/main/docs/source/phone_teleop.mdx)
- LeRobot hosted assets: [robot-urdfs/so101](https://huggingface.co/buckets/lerobot/robot-urdfs/tree/so101)
- License: Apache-2.0; see [LICENSE.txt](LICENSE.txt)

The URDF and visual STL files are byte-for-byte copies from the pinned
TheRobotStudio commit. The generated JSON preserves the official link/joint
hierarchy, axes, limits, visual origins, and material colors while reusing
shared motor geometry between links.

## Dashboard derivative

The STL surfaces are simplified and quantized for low-latency Canvas
rendering. This derivative is intended only for dashboard visualization; use
the unchanged upstream files and supported robot tooling for kinematics,
planning, simulation, control, collision checking, or fabrication.

Rebuild deterministically from the committed sources:

```bash
python3 scripts/build_official_robot_models.py so-101
```
