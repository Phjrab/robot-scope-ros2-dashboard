# ADR: competition odometry-rate readiness hysteresis

Date: 2026-09-02

## Status

Accepted for the opt-in `go2-xt16-wireless-competition-fastlio` profile only.

## Context and audit

The blocked Track C4 attempt observed continuous nominal-10 Hz controller
odometry at `9.984`, `9.999`, `9.997` and `10.013 Hz`. Every non-rate safety
condition could be healthy while localization health alternated between
`READY` and `DEGRADED` at the exact 10.0 Hz boundary.

The pre-change implementation had these properties:

1. `BoundedRateWindow` retained at most 32 arrival timestamps, calculated each
   positive monotonic interval, divided one by the arithmetic mean period, and
   rounded the result to three decimal places in the same snapshot.
2. The stateless classifier consumed that rounded compatibility value.
3. No session-owned health state or rate dwell existed.
4. Runtime process restart implicitly cleared the producer's sample window,
   but the dashboard had no explicit readiness-generation reset.
5. `config/go2.json` provided one robot-wide `navigation_health` block; changing
   `odometry_min_hz` there would affect every navigation profile.
6. The C4 checker separately retained exact map/revision, parameter, corridor,
   lifecycle, topic publisher/freshness, TF, Bridge cardinality, lease,
   deadman and exact-zero gates.

The smallest isolated change is therefore a server-owned policy selected by
the already immutable navigation profile name. It does not add an HTTP
threshold mutation surface and does not alter `config/go2.json`.

## Decision

For `go2-xt16-wireless-competition-fastlio` only, use:

- nominal rate: 10.0 Hz;
- READY enter rate: 9.5 Hz;
- READY exit rate: 9.0 Hz;
- READY enter dwell: 10.0 seconds;
- READY exit dwell: 2.0 seconds;
- maximum READY inter-arrival gap: 0.25 seconds.

All other profiles keep their existing instantaneous comparison against
`navigation_health.odometry_min_hz`, including the prior rounded compatibility
metric. This avoids a silent global relaxation.

The runtime rate window now computes an unrounded frequency, arithmetic mean
period, median period, nearest-rank p95 period, maximum gap, window duration,
sample count, interval count and latest age. The gateway validates the raw
finite values and uses the unrounded frequency internally. Public raw-derived
metrics are rounded to at most six decimal places; the existing three-decimal
`odometry_frequency_hz` remains as the display compatibility field.

`LocalizationReadinessStabilizer` is owned by one
`NavigationRosGateway`. The fixed 10 Hz runtime-health callback advances its
monotonic timers; API polling cannot create READY. Normal/localization-only
session start and stop, initial-pose publication, map-bound session generation
and runtime process-generation changes reset the stabilizer. READY state is
never restored across an application restart.

The first observation of a changed runtime process generation is exposed as
an immediate fail-closed hard fault. Only a subsequent observation may begin
the new 10-second READY enter dwell.

Before READY, every otherwise-healthy sample at or above 9.5 Hz contributes to
the 10-second enter dwell. Once READY, 9.0-9.5 Hz is the hold band. A rate below
9.0 Hz must persist for two seconds before rate-only degradation. Recovery
then requires a new 10-second enter dwell.

## Immediate hard faults

The rate-only dwell never delays or masks stale cloud/runtime/odometry/TF,
frame mismatch, discontinuity/jump, calibration mismatch, non-finite metric,
source/publisher conflict, process generation change, maximum gap above
0.25 seconds, jitter violation, cloud-rate violation, insufficient accepted
points or existing controller stall/progress conditions. A maximum gap above
0.25 seconds is `DEGRADED` while freshness remains within 0.50 seconds; normal
stale classification wins after 0.50 seconds.

The controller source stamp, strictly increasing timestamp, finite
pose/twist/covariance, frame identity, publisher cardinality, 0.50-second
odometry freshness, 0.50-second TF freshness, 500 ms/100 ms strict wireless
guard, watchdog, lease and command gates are unchanged.

## C4 checker consequence

The checker still requires `localization_health.state == READY`. It additionally
requires the exact profile policy, `hard_fault == false`, at least 10 seconds
of stable READY evidence and observed maximum gap at or below 0.25 seconds.
It reports raw/display rate, p95 period, maximum gap, stable duration and rate
band. It remains read-only and cannot send a goal.

## Rationale for 9.5/9.0

The observed nominal-rate minimum was 9.984 Hz, only about 0.16% below 10 Hz.
The 9.5 Hz enter level provides a bounded 5% scheduling margin, while the
9.0 Hz exit level prevents a single normal scheduler fluctuation from
flapping READY. The independent 0.25-second maximum gap and unchanged
0.50-second stale threshold prevent averages from hiding missing updates.

## Rollback

Revert the focused implementation commit. Because the policy is selected only
by the competition profile and no persisted readiness state or configuration
migration exists, rollback restores the previous stateless 10.0 Hz comparison.
Do not roll back by hot-patching thresholds on a running session.

## Motion boundary

This decision authorizes only stationary, no-goal health validation. A real
C4B route still requires a fresh map/pose/corridor preview, physical safety
confirmation and one explicit goal approval. C4A approval is never a motion
approval.
