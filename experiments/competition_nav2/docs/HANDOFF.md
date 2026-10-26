# C3 handoff to reviewers, C1 and C2

Base: `7f2a7070a17975d2a5f123cbf6aab0f99f04bf8a`.
Branch: `review/20261024-c3-nav2-benchmark`.
Scope: new `experiments/competition_nav2/**` and C3's review document only.
User's later branch-submission instruction supersedes initial local-only/main-only
rules. No other branch is merged, no PR is created and no main update is authorized.

The first user attachment is an RGB/crosswalk dataset. It is not needed for Nav2
planar testing and was not used for metric geometry. C3's meaning was resolved from
the contemporaneous C2 role context and local parallel-role ZIP. Source identities
and hashes are in `input_manifest.json`; no private video/model/raw measurements are
included. No source files from another role's modifications were imported.

## Connection proposals (not applied)

- C1: optionally add a separate *hardware-free* job that runs
  `python -m unittest discover -s experiments/competition_nav2/tests -v` with the
  offline dependency file. Current repository test discovery does not discover this
  subtree. Do not represent existing green CI as C3 native coverage.
- C1: after explicit review approval, use an existing Linux container runner to build
  and retain the immutable image/package lock, execute the matrix and attach genuine
  logs. Container build and launch are currently untested.
- C2: candidate YAMLs are comparison inputs, not deployable profiles. Keep the single
  production command owner and final arbiter. Translate any future approved HOLD /
  RELEASE integration through existing versioned contracts, never import this plant
  as a live control owner. Command TTL .25 s is independent of the observation gap
  contract; this plant's sensor source/receipt freshness threshold .3 s is experimental.
- Do not modify `competition.v0.1`, `mission-action.v0.1` or
  `competition-evidence.v0.1` enums using report outcomes. Our result schema is local
  experiment metadata and is not a runtime API extension.
- Do not replace `config/nav2_params_go2_humble.yaml` or production profile allowlists.
  Only after installed-parameter acceptance and actual matched native trials could an
  integration owner propose a new profile. No controller recommendation exists yet.

No other role is a dependency of the pure tests or isolated harness. Cross-branch
compatibility, onboard binding, actual foot/posture evidence, perception and measured
braking remain NOT_RUN. Hardware deployment and whole-course gait qualification are
out of scope. Rollback is removal of this unreferenced experiment subtree and C3 review
document; production runtime is unaffected.

## Failure/absence policy

Offline tests may PASS. Native results remain NOT_RUN until image lock, isolation,
lifecycle, binary/plugin, native action and command evidence exist. A rejected action,
unsupported parameter, conflicting publisher, missing timestamp, stale input, process
crash, resource exhaustion or cleanup failure must remain in results. Do not move the
fixed goal/cones or loosen timeouts to obtain PASS. The native plan contains 144
scheduled, zero executed runs at delivery; this is a plan, not a benchmark result.
