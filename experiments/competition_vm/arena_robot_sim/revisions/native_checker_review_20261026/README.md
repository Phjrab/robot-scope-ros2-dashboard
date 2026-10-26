# D0 bounded native-checker evidence review

Independent offline polygon-clipping oracle; no ROS, native library or actuator.
Run `python3 -m unittest discover -s THIS_DIRECTORY -v`. Nine self-contained checks
run; the tenth retained-artifact replay requires D0_R6_EVIDENCE (C3 d4bbee6b archive
root), D0_R6_RAW (artifact12630872211 extraction), and D0_R6_ZIP (original ZIP).

Reproduce result.json with `python3 review.py C3_SOURCE_ROOT ARTIFACT_ROOT ZIP OUTPUT`.
Source is read-only pinned C3; original raw artifact stays private. Inputs cannot be
used as runtime navigation routes or hidden obstacle priors. See D0 ROUND6 report
for exact provenance, native/reconstruction limits and frozen decision.
