# Phase 9 — Quality Tooling and Reproducibility

## Scope

Phase 9 adds a small, reproducible quality gate without changing runtime ROS,
mapping, navigation, control, filesystem, or web API behavior.  It is not a
formatter migration, a dependency upgrade, or a replacement for Jetson/ROS
acceptance testing.

## Tool boundaries

| Check | Scope | Reason |
|---|---|---|
| Ruff | `robot_dashboard` and `scripts` | Correctness-only rules (`E4`, `E7`, `E9`, `F`) catch undefined names, invalid imports, and unreachable import mistakes without mass style churn. |
| Mypy | Four typed, ROS-independent modules | An incremental strict baseline that avoids pretending untyped ROS 2 Humble system packages are pip-managed. |
| Coverage | Existing Python unit suite | Records branch-aware coverage in CI; no arbitrary coverage percentage gate is added before a hardware-aware baseline exists. |
| JavaScript syntax | Every `robot_dashboard/static/**/*.js` module | Keeps vanilla ES modules parseable, including feature modules outside the historical entrypoint list. |
| Secret scan | Tracked source-like files only | Dependency-free detection of high-confidence private keys and common service-token forms. It prints rule/file/line, never a matched value. |
| Dependency audit | `pip check` and `pip-audit -r requirements.txt` | Validates the resolved Python graph and known public advisories. |

`requirements-quality.txt` pins tool versions independently of runtime
requirements. It deliberately excludes `rclpy`, ROS messages, native driver
packages, external ROS workspaces, maps, bags, and generated data.

## Reproducibility decision

The supported runtime remains Ubuntu 22.04, Python 3.10, ROS 2 Humble and a
`--system-site-packages` virtualenv. A repository-wide Python lockfile would
not capture apt-provided ROS packages or reliably transfer arm64 and x86_64
native wheels. It would imply reproducibility that this repository cannot
truthfully provide.

Instead, each verified release records the source commit, requirements hash,
target architecture, Python/ROS/RMW version, installed package freeze and the
existing external ROS manifest pins. A future host-specific constraints file
must be generated from a verified target, reviewed with its release record,
and must not overwrite ROS system packages.

## CI order

1. Install runtime and exact quality tooling.
2. Run Ruff and the incremental Mypy scope.
3. Scan tracked source and audit Python dependencies.
4. Run the unchanged Python suite under branch coverage.
5. Run the existing Node test suite and syntax-check every dashboard module.

No check sends robot commands, starts a service, launches mapping/navigation,
or accesses runtime maps/datasets. Existing control bridge, lease, E-stop,
mapping command, navigation fencing, and filesystem boundaries are unchanged.

## Compatibility and follow-up

- Runtime `requirements.txt` continues to use compatibility ranges; only
  contributor/CI tool versions are exact-pinned.
- Existing Python and Node commands remain valid. The new all-module syntax
  command replaces the incomplete hand-maintained list of JavaScript entry
  files.
- The Mypy scope is intentionally limited to typed pure modules. Expand it
  only after adding ROS-aware stubs or isolated adapters with corresponding
  tests; do not suppress control/navigation diagnostics wholesale.
- Secret scanning is high-confidence and does not substitute for review,
  protected CI secrets, or external secret storage.
