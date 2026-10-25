# Independent first-failure geometry review

Scope: only the recorded `rpp-d0_feasible1-0` run; no native execution,
configuration change, search expansion, original-source edit, or publication.
The full ROUND4 role instruction was read. The analysis below uses separate
SAT and segment-distance implementations, not the frozen witness helper.

## Numerically reproduced

- Last pre-warning saved pose, sim 6.399999999999985:
  `(0.5167972571840633, 1.7462801514863986, 1.5282629698786039)`.
- Raw body's minimum geometric clearance: `0.18623516060791578 m`.
  Padded body's: `0.15498667680423917 m`. Both minima are against the
  route boundary. Cone-base clearances are respectively
  `0.207180383871008 m` and `0.17593190006733161 m`.
- Most recent recorded global path source sim `6.349999999`, point index 21
  (zero based): `(0.5158475760553571, 1.9545850698370089)`.
  The outgoing segment's yaw is `1.401993995443007 rad`. Independently
  applying this derived heading makes both raw and padded rectangles
  overlap the cone base by SAT. The recorded global OccupancyGrid center
  cell `[25,97]` is `0`, from source sim `6.149999999`.
- Heading sensitivity matters: the central chord through points 20 and 22
  gives `1.5667803695454525 rad`. At that heading the raw rectangle is
  clear of the cone by `0.009293731053616305 m`; the padded rectangle
  still overlaps. Thus the outgoing-segment raw-body counterexample is
  valid, but is neither heading-independent nor a measured RPP pose.
- Holding the last accepted `(v,w)=(0.18,-0.01558637696076498)` from the
  saved pose using exact constant-twist integration reaches padded contact
  at approximately `0.954799167946259 s`. This is a counterfactual,
  not the rejected candidate or native sampled prediction.

## Alignment and evidence labels

First error is native.log line 144 at wall `1792904808.540106401`.
The first subsequent zero command was published at
`1792904808.540151104`, received at monotonic `250.318854364` with
recorded source age `0.000547132 s`. The source-contract clock bridge
therefore places the error between the saved trace samples at sim 6.40
and 6.45. The latter pose is
`(0.5171834457111764,1.75527186179768,1.5274836510305656)`.
These are actual saved samples, not an invented exact controller TF pose.
Spin collision warning at wall `1792904810.449059220` is later recovery.

The recorder has no local costmap, Path orientations, carrot, rejected
candidate twist, or failed projected checker sample. Exact RPP causal
attribution remains unconfirmed. Current geometric contact is excluded
only for the saved pre-event pose, not for an unrecorded controller input.
The center-cell result must not be called a full footprint clearance test.

## Review disposition

No blocking discrepancy in the verified geometry or conservative evidence
labels. Explicitly identify the outgoing-segment tangent definition in
reports and figure labels. The heading sensitivity above is a useful
caveat, not a reason to tune the controller or weaken geometry.

Reproduction from repository root:

```sh
python experiments/competition_vm/arena_robot_sim/revisions/native_feasible1_audit_20261025/review/independent_geometry.py /path/to/verified/artifact/d0/rpp-d0_feasible1-0/run
```

`independent_geometry.json` is the generated numerical check. Ten local
assertions exercised SAT overlap/separation/contact, intersecting segments,
unit polygon distance, recorded clearance values, outgoing-tangent overlaps,
and the central-chord raw-body sensitivity. They passed; this is not a
substitute for the parent task's full repository regression suite.
