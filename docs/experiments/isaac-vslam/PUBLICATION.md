# Publication and handoff

Repository: https://github.com/Phjrab/robot-scope-ros2-dashboard
Branch: `experiment/isaac-vslam-onboard`.
Base SHA: `093600fc002006fba3ba520c7c58f2f202c85111`.

- VSLAM experiment implementation/evidence: `3118e5576961139d8a5aea6746f226ba1b86f9b7`.
- Resource monitor implementation: `0bdb7f2a728467b0a3eae046c8838b66319b85a6`.
- Follow-up implementation adds the multi-thread executor, recorded-bag reuse diagnosis, namespaced static TF inspection and read-only SDK motion/options probe. The final branch tip is written in remote runtime `evidence/publication-followup-20261014.json`; use `git rev-parse HEAD` for the exact local tip.

The VSLAM commit can be reviewed independently of the dashboard monitor. No main/UI/migration branch was changed, merged, reset or deployed. No source or data was pushed to NVIDIA upstream.

Read [RESULTS.md](RESULTS.md) for install/input/VO/SLAM pass criteria, IMU and map reuse failures, camera service restoration, resources, clock limitations and motion NOT_RUN. Read [execution README](../../../experiments/isaac_vslam/README.md) for exact rerun/owned cleanup. Dashboard monitor integration and deployment scope are in [COMPUTE_MONITOR.md](../../COMPUTE_MONITOR.md).

Validation: 1663 Python unittest cases (2 optional skips), 342 JavaScript cases, 2 resource-panel browser cases. All completed without failures. Full test logs and browser fixture screenshots are in `/private/tmp/isaac-vslam-evidence-20261013` on the Mac; raw hardware measurements, bags and maps remain on the Jetson runtime. The monitor backend was sampled read-only on the real Jetson, while browser verification used a fixture. Operational dashboard deployment remains NOT_RUN.

Follow-up 2026-10-14: full Python unittest 1664 cases (2 optional skips) and JavaScript 342 cases passed. No dashboard code changed in this follow-up. Live T3 and restoration evidence are recorded in RESULTS.md and evidence/followup-*.json. Movement was explicitly excluded.
