# Publication and handoff

Repository: https://github.com/Phjrab/robot-scope-ros2-dashboard
Branch: `experiment/isaac-vslam-onboard`.
Base SHA: `093600fc002006fba3ba520c7c58f2f202c85111`.

- VSLAM experiment implementation/evidence: `3118e5576961139d8a5aea6746f226ba1b86f9b7`.
- Resource monitor implementation: `0bdb7f2a728467b0a3eae046c8838b66319b85a6`.
- Final implementation revision is the resource-monitor commit above. A subsequent documentation-only commit records this handoff; use `git rev-parse HEAD` for the branch tip, also written in the remote runtime `evidence/publication.json` after publication.

The VSLAM commit can be reviewed independently of the dashboard monitor. No main/UI/migration branch was changed, merged, reset or deployed. No source or data was pushed to NVIDIA upstream.

Read [RESULTS.md](RESULTS.md) for install/input/VO/SLAM pass criteria, IMU and map reuse failures, camera service restoration, resources, clock limitations and motion NOT_RUN. Read [execution README](../../../experiments/isaac_vslam/README.md) for exact rerun/owned cleanup. Dashboard monitor integration and deployment scope are in [COMPUTE_MONITOR.md](../../COMPUTE_MONITOR.md).

Validation: 1663 Python unittest cases (2 optional skips), 342 JavaScript cases, 2 resource-panel browser cases. All completed without failures. Full test logs and browser fixture screenshots are in `/private/tmp/isaac-vslam-evidence-20261013` on the Mac; raw hardware measurements, bags and maps remain on the Jetson runtime. The monitor backend was sampled read-only on the real Jetson, while browser verification used a fixture. Operational dashboard deployment remains NOT_RUN.
