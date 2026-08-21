# SO-101 Extraction Inventory

> Phase 1 product-boundary record. This document preserves the inventory of
> the SO-101 integration removed from the Robot Scope mobile-robot product.
> It is not a runtime support guide and does not reintroduce SO-101 support.

## Decision and scope

Robot Scope is a ROS 2 autonomous mobile-robot control panel. Its supported
reference and secondary mobile platforms are Unitree Go2, TurtleBot, and a
Generic ROS 2 mobile robot. SO-101 is a manipulator/controller-host product
and is intentionally outside that boundary.

The removed code was observation/display-only: it did not add a Go2 motion
transport, a manipulator driver, or a browser-controlled serial interface.
The extraction therefore removes the selectable product integration and bundled
assets without changing shared control, mapping, navigation, filesystem, or
ROS-executor behavior.

## Inventory at extraction

### Dedicated product integration

| Area | Removed responsibility |
| --- | --- |
| `config/so101.json` | Observation-only startup profile, with disabled control and camera/point-cloud topic preferences. |
| `robot_dashboard/discovery.py` | `so-101` catalog entry, aliases, name inference, controller-host wording, and discovery scoring. |
| `robot_dashboard/static/index.html` | SO-101 choice in the Settings robot-type selector. |
| `robot_dashboard/static/robot_profiles.js` | SO-101 fallback profile and model URLs used when the API catalog is unavailable. |
| `robot_dashboard/static/assets/robot-model-catalog.json` | SO-101 browser model catalog entry. |
| `scripts/run_generic.sh` | `ROBOT_SCOPE_PROFILE=so-101|so101` to `config/so101.json` mapping. |
| `scripts/build_official_robot_models.py` | SO-101-specific `ModelSpec`, source paths, mesh simplification targets, and output location. |

### Bundled model assets and provenance

The removed directory was `robot_dashboard/static/assets/so101/` (about
16 MiB in the Phase 1 baseline). It contained:

- `so101-official-lite.json`, the browser visualization derivative;
- `source/SO101/so101_new_calib.urdf` and 13 referenced STL visual meshes;
- `upstream-manifest.json`, including SHA-256 hashes for all bundled sources;
- `LICENSE.txt` (Apache License 2.0); and
- the model-specific provenance and modification notes.

The recorded source was TheRobotStudio `SO-ARM100`, `Simulation/SO101`, pinned
to commit `7629d2ad9853d10fb903093a33ef6114099d97e5`, under Apache-2.0. The
browser model described itself as an official-derived, deterministic compact
visualization. These assets are removed from the shipped product, so the
repository's third-party notices retain only licenses for assets still shipped.

### Configuration schema and profile example

The removed profile used the ordinary JSON startup-profile schema already used
by `config/generic.json` and `config/turtlebot.json`:

- identity: `name`, `robot_type`, `robot_ip`;
- explicit disabled `control.enabled`;
- bounded saved-map discovery settings; and
- allowlisted preferred camera, point-cloud, odometry, and occupancy topics.

For a future standalone SO-101 project, the former `config/so101.json` should
be recovered from repository history together with its tests and treated as a
starting example only. It must not be copied into a mobile-robot deployment
without a separate capability and safety review.

### Source, frontend, and test inventory

The following SO-101-specific tests were updated rather than deleted: they now
verify that only mobile profiles are supported and that an SO-101 request is
rejected by the same unknown-type boundary used for other unsupported types.

| Test file | Former SO-101 coverage | Retained coverage |
| --- | --- | --- |
| `tests/test_discovery.py` | Catalog, alias/name inference, profile file, and controller-host discovery. | Go2/TurtleBot catalog, bounded discovery, Generic profile, and rejection of unsupported types. |
| `tests/test_ros_agent_target.py` | Live observation target switch to SO-101. | Generic/TurtleBot observation switching, Go2 restart/control gating, and unsupported-target rejection. |
| `tests/test_robot_profiles.mjs` | Fallback catalog/model normalization for SO-101. | Go2/TurtleBot fallback catalog and rejection of unknown fallback types. |
| `tests/test_official_robot_assets.py` | SO-101 URDF/STL manifest, deterministic derivative, and size budget. | TurtleBot official asset provenance, deterministic build, and size budget. |

`README.md`, `THIRD_PARTY_NOTICES.md`, and
`robot_dashboard/static/assets/README.md` also contained product metadata or
license notices for the removed asset and are updated as part of this phase.

## Shared reusable implementation retained

The following components were used by SO-101 but are deliberately retained
because Go2, TurtleBot, Generic ROS 2, or the mobile-robot product still use
them:

- `LocalRobotDiscovery`, local-subnet validation, hostname sanitization,
  bounded scanning, caching, and public catalog serialization;
- `RosAgent.set_robot_target()`, which keeps target selection distinct from the
  startup ROS profile and preserves the existing Go2 fail-closed control
  revocation behavior;
- the generic JSON startup-profile loader and `infer_robot_type()` support for
  Go2, TurtleBot, and Generic profiles;
- `RobotProfiles` normalization, candidate validation, and connection-payload
  helpers;
- the `robot-scope.robot-model-lite` schema, Canvas model renderer, and the
  standard-library URDF/STL model-builder utilities; and
- existing Go2/TurtleBot model assets, their manifests, and their license
  notices.

No control, mapping, navigation, service lifecycle, map filesystem, dataset,
or ROS topic safety boundary is removed or weakened by this extraction.

## Current integration points removed

At the Phase 1 baseline, SO-101 was reachable through all of the following
paths: the Settings type selector, `GET /api/v1/robots/types`,
`POST /api/v1/robots/discover`, `POST /api/v1/robot`, fallback frontend
profiles, `ROBOT_SCOPE_PROFILE`, and the local static model catalog. After the
extraction, those paths accept and advertise only their remaining mobile robot
profiles; an SO-101 type or profile is rejected rather than silently mapped to
a different robot.

## Post-extraction residual search policy

After deletion, product/runtime source must contain no SO-101, SO101, or
LeRobot integration. Deliberate residual references are limited to this
extraction record, the immutable Phase 0 baseline (which describes the
pre-extraction state), and negative regression tests proving that unsupported
SO-101 input is rejected. They are historical or rejection evidence, not
shipped capability metadata, profile selection, asset URLs, or license notices.

## Future standalone-project candidates

If an independent manipulator product is created later, recover the deleted
SO-101-specific files from Git history and move them together as one inventory:

1. the profile and product metadata;
2. the SO-101 discovery/controller-host policy;
3. the model-builder `ModelSpec`, browser catalog entry, source URDF/STLs,
   manifest, derivative, and Apache-2.0 notice; and
4. the dedicated portions of the four test files listed above.

It should reuse shared utilities only through explicit interfaces and must add
its own manipulator transport, capability model, security policy, and safety
tests. In particular, Robot Scope's mobile mapping, navigation, and Go2 motion
paths are not a substitute for a manipulator control architecture.
