# Revision changes

- Kept all legacy asset files unchanged; recorded their SHA256 and baseline commit.
- Created separate text-primary8×6m design with5.018m slalom and two1.4m endpoint widths,2.4×1.018m bays and1.5m parkingheight.
- Preserved conflicting source dimensions and unbound constraints rather than uniformly scaling prior meshes.
- Added separate visual objects, virtual fences, closed terrain exports, semantic polygons, draft directed edges, finite full-footprint finish and both-feet checks.
- Added two provisional rectangular stop zones, two independently state-configurable signal IDs, separated100mm wall panels, synthetic debug overlays and seven scenario fixtures.
- Actual Blender CPU renders revealed connector gaps; regenerated corrected polygon corners and rerendered. Floor/terrain legacy alignment still requires source geometry resolution and is not navigation-qualified.
- First CPU render attempt failed because distro Blender has no OpenImageDenoise; explicitly disabled denoising and successfully rendered using CPU Cycles24samples. No GPU/physics/browser/realrobot PASS inferred.
