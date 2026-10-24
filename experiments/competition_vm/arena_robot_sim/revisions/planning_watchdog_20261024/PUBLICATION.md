# Frozen watchdog publication subset

Original source, tests, review probes, fixture, reports and checksums are copied
byte-for-byte. The original README/VALIDATION are historical experiment records;
this file records later local publication preparation. `PUBLICATION_SUBSET.json`
provides original/published byte counts and hashes. All 21 original non-cache
files are included, totaling 104500 bytes. No raw binary cProfile dumps were
part of this frozen revision or added. The small text profiles remain evidence.

The original `SHA256SUMS.txt` is retained. The publisher-owned
`PUBLICATION_FILES.txt` lists this subset, and `PUBLICATION_SHA256SUMS.txt` hashes
every listed file except itself. See sibling
`curved_progress_20261024/PUBLICATION.md` for portable replay and exact
unmodified dependencies. Its `publication_checks.py` runs the unchanged 15
tests and actual planner timeout in a fresh output directory, never overwriting
these frozen timing JSONs. Its separately labeled adapter reroots only the
frozen review probe's VM import path. The original profiling scripts are not
portable as-is and are not claimed rerun in this publication check.

The real-clock gate records zero during pending/expired/cancelled planning.
Late receive and concurrent cancellation cannot commit a revived result in
the tested cases. Pipe `recv` itself can still block; this is zero-output
eligibility evidence, NOT a bounded-response planner, hard realtime controller,
physical stop, integrated navigation, or hardware test. The actual frozen
planner exceeds the local 0.1 s test budget and a timeout is a safe failure
outcome, not successful navigation. The isolated exact-coordinate memoization
is not adopted and still exceeded both test budgets in the original profile.
No user operating cap or production TTL was changed.

No main/UI/hardware changes, Git commits or GitHub writes are part of this local
preparation. Local full-suite failures and checks not run are recorded in
sibling `curved_progress_20261024/publication_validation/`.
