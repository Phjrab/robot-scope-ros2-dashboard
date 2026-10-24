# Go2 exact-trace visual replay

This renderer loads the existing `rulebook-20261015/arena.blend` unchanged, imports all 17 official Go2 links and 12 revolute joints from the repository's quantized asset, and renders recorded `results/cone_detour.json` poses and virtual LiDAR returns. Metres, Z-up, no geometric scale modification.

Standing joint positions come from the asset defaults (hip 0, thigh .75, calf -1.5 rad). Grounding root height .33407456 m is derived from transformed mesh vertices. Standing bounding box is recorded in `standing_bounds.json`. The chassis is kinematically replayed; legs hold a static stance. This is NOT validated walking, contact dynamics, balance, odometry, or VSLAM. Pose is SIM_GT. LiDAR points come directly from the simulation trace; no ray visualization is invented. Yellow path is executed historical pose, not a newly smoothed plan.

Cone base is a .26 m square, .04 m tall. Orange/white 32-sided cone has .12 m bottom radius at z=.04 and apex z=.32. White paint band lies on the identical cone surface, so it does not enlarge collision geometry. Fence meshes in the arena are virtual zero-thickness boundaries, not validated manufactured walls. Only the right corridor and parking extension are exercised; this does not establish full competition route compliance.

## Run from repository root

```
blender -b --python experiments/competition_vm/arena_robot_sim/rendering/render.py -- --preview
blender -b --python experiments/competition_vm/arena_robot_sim/rendering/render.py -- --frames 94 --view oblique
python experiments/competition_vm/arena_robot_sim/rendering/label_frames.py oblique
ffmpeg -framerate 5 -i experiments/competition_vm/arena_robot_sim/rendering/output/oblique/labeled/%04d.png -c:v libx264 -pix_fmt yuv420p go2_cone_detour.mp4
```

Workbench headless rendering was selected after verifying it works on this VM. Cycles OpenImageDenoise is not compiled into the installed Blender. Video sampled indices and original simulation timestamps are retained in `output/oblique/rendered_frame_indices.json`. Video display is 5 fps, approximately original simulation timing; timestamp captions remain authoritative.

Official Unitree mesh provenance and BSD-3-Clause license: `robot_dashboard/static/assets/go2/README.md`, `LICENSE.txt`; local license copy `UNITREE_BSD_LICENSE.txt`. Source commit f3772ce54c56ef2d34c6aee8100bc768896c7d19. This is a visual demonstration, not real robot validation.
