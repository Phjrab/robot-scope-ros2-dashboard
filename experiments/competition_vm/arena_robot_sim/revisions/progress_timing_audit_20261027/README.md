# D0 retained progress/timing audit

Offline arithmetic only: no ROS imports, native execution, parameter changes,
controller replacement, live observation or physical qualification.

Run against the privately extracted C3 artifact12638597871:

```sh
python3 audit.py /path/to/extracted --output /tmp/progress-result.json
D0_R8_ARTIFACT=/path/to/extracted python3 -m unittest discover -s . -v
```

Retained-data tests explicitly skip if no artifact is available; eight arithmetic
checks remain. Publication validation ran all thirteen with the actual retained
artifact, including source/file hashes and exact result reproduction. Original
archive/trace/log/commands are not published. result.json contains derived summaries
only, not a command replay, controller configuration or runtime input.

Source, clocks, causal limits, full checks and next step: D0 ROUND8.md. No current
controller timing warning is promoted to an isolated compute benchmark. Existing
D0 collision evidence is not recomputed or modified.
