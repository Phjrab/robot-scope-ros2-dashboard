# Cockpit viewpoint persistence

Previously route deactivation destroyed the renderer without capturing the
camera. Reactivation applied only an orientation preset and auto-fitted the
first cloud. Panel layout reset also reset the scene.

Cockpit now defaults to robot follow, snaps to the first valid robot pose, and
does not auto-fit incoming clouds. Camera target, distance, yaw, pitch and mode
are stored per robot profile and map ID/revision. Storage errors fall back to
in-memory route-cycle restoration. Invalid records are ignored. Temporary map
telemetry absence does not clear camera scope; an actual map change restores
that map's preference or defaults to follow.

Manual pan releases follow in Cockpit only. Orbit/zoom retain the operator's
chosen follow mode. The scene reset button returns to robot-centered follow
at an 8m camera distance; this is not a robot motion setting. Resetting floating
panels no longer alters the camera. Explicit saved scene-layout application
still applies the requested preset; layout JSON schema is unchanged.

Verification: Python 1,460 tests OK (one skipped), JavaScript suite including
camera validation, corrupt/unavailable storage, map isolation, route cycles,
fresh-host restoration and real renderer follow/pan/reset behavior. Local
in-app browser using the actual renderer confirmed target [8,4,0] for a
synthetic pose [8,4,0], then exact preservation of distance 5.1936750134811795,
yaw -0.05460183660255161 and pitch 0.33595865315812856 across renderer
recreation and page reload. Test harness has no API/robot connection.

No Jetson deployment, service restart or robot commands were performed.
